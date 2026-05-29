"""Quick Session wizard — guided 4-step setup that starts an acquisition.

Pages:
    1. Connect — auto-discover + connect to mount and camera
    2. Target  — pick a target by name, by Stellarium selection, or by RA/Dec
    3. Plan    — choose an acquisition profile, see duration + disk estimate
    4. Acquire — START the run, watch progress, save session.json at the end

The wizard does not own hardware logic; it drives the existing CapturePanel
through public methods (``start_discovery``, ``connect_devices``,
``start_quick_session``) so all the workers, signals, and FITS save plumbing
already in the main panel are reused as-is.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QWizard,
    QWizardPage,
)

from seercontrol.core.config import Config
from seercontrol.core.imaging.session import Session, write_session_json
from seercontrol.core.profiles import Profile, load_profiles
from seercontrol.core.stellarium.remote_pull import (
    StellariumTarget,
    pull_selected_object,
)
from seercontrol.core.targets.horizon import VisibilitySummary, visibility_tonight
from seercontrol.core.targets.resolver import Target, resolve_name
from seercontrol.ui import theme

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Workers (off-thread network / astropy calls)                                  #
# --------------------------------------------------------------------------- #

class _RunnerSignals(QObject):
    target      = pyqtSignal(object)   # Target / VisibilitySummary / StellariumTarget
    failed      = pyqtSignal(str)


class _ResolveRunner(QRunnable):
    def __init__(self, name: str) -> None:
        super().__init__()
        self._name = name
        self.signals = _RunnerSignals()

    def run(self) -> None:
        target = resolve_name(self._name)
        if target is None:
            self.signals.failed.emit(f"Unknown target “{self._name}”")
        else:
            self.signals.target.emit(target)


class _VisibilityRunner(QRunnable):
    def __init__(
        self,
        ra_hours: float,
        dec_degrees: float,
        site_lat: float,
        site_lon: float,
        site_elev: float,
    ) -> None:
        super().__init__()
        self._ra = ra_hours
        self._dec = dec_degrees
        self._lat = site_lat
        self._lon = site_lon
        self._elev = site_elev
        self.signals = _RunnerSignals()

    def run(self) -> None:
        try:
            summary = visibility_tonight(
                self._ra, self._dec, self._lat, self._lon, self._elev,
                sample_minutes=15,
            )
        except Exception as exc:
            self.signals.failed.emit(str(exc))
            return
        self.signals.target.emit(summary)


class _PullRunner(QRunnable):
    """Used by the Target page's "Pull from Stellarium" button."""

    def __init__(self, host: str, port: int) -> None:
        super().__init__()
        self._host, self._port = host, port
        self.signals = _RunnerSignals()

    def run(self) -> None:
        result = pull_selected_object(host=self._host, port=self._port)
        if result is None:
            self.signals.failed.emit("Stellarium pull failed (plugin off, no selection?)")
        else:
            self.signals.target.emit(result)


# --------------------------------------------------------------------------- #
# Page 1: Connect                                                              #
# --------------------------------------------------------------------------- #

class _ConnectPage(QWizardPage):
    """Show connection state and trigger discovery/connection on the panel."""

    def __init__(self, wizard: "SessionWizard") -> None:
        super().__init__()
        self._wizard = wizard
        self.setTitle("Connect")
        self.setSubTitle("Connect to the Seestar before configuring the session.")
        self._mount_ok = False
        self._camera_ok = False
        self._build_ui()
        # Listen to the panel's connection signals — the panel handles the real work.
        wizard.capture_panel.mount_conn_changed.connect(self._on_mount_changed)
        wizard.capture_panel.camera_conn_changed.connect(self._on_camera_changed)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(12)

        form = QFormLayout()
        self._host_edit = QLineEdit()
        self._host_edit.setPlaceholderText("192.168.x.x")
        self._port_spin = QSpinBox()
        self._port_spin.setRange(1, 65535)
        self._port_spin.setValue(32323)
        form.addRow("Host:", self._host_edit)
        form.addRow("Port:", self._port_spin)
        root.addLayout(form)

        btn_row = QHBoxLayout()
        self._discover_btn = QPushButton("⚡  Auto-discover")
        self._discover_btn.clicked.connect(self._on_discover)
        self._connect_btn = QPushButton("↗  Connect mount + camera")
        self._connect_btn.setProperty("class", "primary")
        self._connect_btn.clicked.connect(self._on_connect)
        btn_row.addWidget(self._discover_btn)
        btn_row.addWidget(self._connect_btn)
        root.addLayout(btn_row)

        status_grid = QGridLayout()
        status_grid.setSpacing(6)
        self._mount_lbl = _status_label("○ Mount")
        self._camera_lbl = _status_label("○ Camera")
        status_grid.addWidget(QLabel("Status:"), 0, 0)
        status_grid.addWidget(self._mount_lbl, 0, 1)
        status_grid.addWidget(self._camera_lbl, 0, 2)
        root.addLayout(status_grid)
        root.addStretch()

    def initializePage(self) -> None:
        cfg = self._wizard.config
        self._host_edit.setText(cfg.alpaca_host or "")
        self._port_spin.setValue(cfg.alpaca_port or 32323)
        # Reflect current connection state — the panel may already be connected.
        panel = self._wizard.capture_panel
        self._on_mount_changed(panel.telescope is not None)
        self._on_camera_changed(panel.camera is not None)

    def isComplete(self) -> bool:
        return self._mount_ok and self._camera_ok

    def _on_discover(self) -> None:
        self._wizard.capture_panel.start_discovery()

    def _on_connect(self) -> None:
        host = self._host_edit.text().strip()
        port = self._port_spin.value()
        if not host:
            return
        # Sync the panel's own fields so its public connect methods read them.
        self._wizard.capture_panel.set_host_port(host, port)
        self._wizard.capture_panel.connect_mount()
        self._wizard.capture_panel.connect_camera()

    def _on_mount_changed(self, connected: bool) -> None:
        self._mount_ok = connected
        self._mount_lbl.setText(("● Mount" if connected else "○ Mount"))
        self._mount_lbl.setStyleSheet(
            f"color:{theme.SUCCESS if connected else theme.FG_MUTED}; "
            f"font-size:12px; background:transparent;"
        )
        self.completeChanged.emit()

    def _on_camera_changed(self, connected: bool) -> None:
        self._camera_ok = connected
        self._camera_lbl.setText(("● Camera" if connected else "○ Camera"))
        self._camera_lbl.setStyleSheet(
            f"color:{theme.SUCCESS if connected else theme.FG_MUTED}; "
            f"font-size:12px; background:transparent;"
        )
        self.completeChanged.emit()


# --------------------------------------------------------------------------- #
# Page 2: Target                                                               #
# --------------------------------------------------------------------------- #

class _TargetPage(QWizardPage):
    """Resolve a target by name, by Stellarium selection, or by manual RA/Dec."""

    def __init__(self, wizard: "SessionWizard") -> None:
        super().__init__()
        self._wizard = wizard
        self.setTitle("Target")
        self.setSubTitle("Pick what you want to image and check its altitude tonight.")
        self._target: Optional[Target] = None
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(10)

        # Name resolution row
        name_row = QHBoxLayout()
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("e.g. M42, T CrB, WASP-12, NGC 224")
        self._name_edit.returnPressed.connect(self._on_resolve)
        resolve_btn = QPushButton("Resolve")
        resolve_btn.clicked.connect(self._on_resolve)
        pull_btn = QPushButton("⇣  Stellarium")
        pull_btn.setToolTip("Pull the currently selected object from Stellarium")
        pull_btn.clicked.connect(self._on_pull)
        name_row.addWidget(QLabel("Name:"))
        name_row.addWidget(self._name_edit, 1)
        name_row.addWidget(resolve_btn)
        name_row.addWidget(pull_btn)
        root.addLayout(name_row)

        # Manual RA/Dec row
        coords_row = QHBoxLayout()
        self._ra_spin = QDoubleSpinBox()
        self._ra_spin.setRange(0.0, 23.9999)
        self._ra_spin.setDecimals(4)
        self._ra_spin.setSuffix("  h")
        self._dec_spin = QDoubleSpinBox()
        self._dec_spin.setRange(-90.0, 90.0)
        self._dec_spin.setDecimals(4)
        self._dec_spin.setSuffix("  °")
        manual_btn = QPushButton("Use manual coords")
        manual_btn.clicked.connect(self._on_manual)
        coords_row.addWidget(QLabel("RA"))
        coords_row.addWidget(self._ra_spin)
        coords_row.addWidget(QLabel("Dec"))
        coords_row.addWidget(self._dec_spin)
        coords_row.addWidget(manual_btn)
        root.addLayout(coords_row)

        # Resolved target summary
        self._summary_lbl = QLabel("—")
        self._summary_lbl.setWordWrap(True)
        self._summary_lbl.setStyleSheet(
            f"color:{theme.FG}; font-size:12px; padding:8px;"
            f"border:1px solid {theme.BORDER}; background:{theme.BG2};"
        )
        root.addWidget(self._summary_lbl)

        # Visibility summary
        self._vis_lbl = QLabel("Altitude tonight: —")
        self._vis_lbl.setStyleSheet(
            f"color:{theme.FG_MUTED}; font-size:11px; background:transparent;"
        )
        root.addWidget(self._vis_lbl)
        root.addStretch()

    def isComplete(self) -> bool:
        return self._target is not None

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _on_resolve(self) -> None:
        name = self._name_edit.text().strip()
        if not name:
            return
        self._summary_lbl.setText(f"Resolving “{name}”…")
        runner = _ResolveRunner(name)
        runner.signals.target.connect(self._apply_target)
        runner.signals.failed.connect(self._on_resolution_failed)
        QThreadPool.globalInstance().start(runner)

    def _on_pull(self) -> None:
        # Use the same Stellarium HTTP port as the Stellarium card on the panel.
        host, port = self._wizard.stellarium_http_settings()
        self._summary_lbl.setText("Asking Stellarium for the selected object…")
        runner = _PullRunner(host, port)
        runner.signals.target.connect(self._apply_stellarium_pull)
        runner.signals.failed.connect(self._on_resolution_failed)
        QThreadPool.globalInstance().start(runner)

    def _on_manual(self) -> None:
        ra, dec = self._ra_spin.value(), self._dec_spin.value()
        self._apply_target(Target(
            name=f"RA {ra:.4f}h, Dec {dec:+.4f}°",
            queried_name="manual",
            ra_hours=ra, dec_degrees=dec,
        ))

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _apply_target(self, target: Target) -> None:
        self._target = target
        mag_str = f" · V≈{target.magnitude:.2f}" if target.magnitude is not None else ""
        self._summary_lbl.setText(
            f"<b>{target.name}</b>{mag_str}<br>"
            f"RA {target.ra_hours:.4f} h · Dec {target.dec_degrees:+.4f}°"
            f"{f' · {target.object_type}' if target.object_type else ''}"
        )
        self._ra_spin.setValue(target.ra_hours)
        self._dec_spin.setValue(target.dec_degrees)
        self._start_visibility(target.ra_hours, target.dec_degrees)
        self.completeChanged.emit()

    def _apply_stellarium_pull(self, pulled: StellariumTarget) -> None:
        # Convert to a Target (cache miss is fine — manual entry uses the queried name).
        self._apply_target(Target(
            name=pulled.name, queried_name=pulled.name,
            ra_hours=pulled.ra_hours, dec_degrees=pulled.dec_degrees,
            magnitude=pulled.magnitude,
        ))

    def _on_resolution_failed(self, message: str) -> None:
        self._summary_lbl.setText(
            f"<span style='color:{theme.DANGER}'>{message}</span>"
        )

    def _start_visibility(self, ra_h: float, dec_d: float) -> None:
        cfg = self._wizard.config
        lat = cfg.get("site.latitude")
        lon = cfg.get("site.longitude")
        elev = cfg.get("site.elevation") or 0.0
        if lat is None or lon is None:
            self._vis_lbl.setText("Site latitude/longitude not set in Preferences — altitude check skipped.")
            return
        self._vis_lbl.setText("Altitude tonight: computing…")
        runner = _VisibilityRunner(ra_h, dec_d, float(lat), float(lon), float(elev))
        runner.signals.target.connect(self._apply_visibility)
        runner.signals.failed.connect(
            lambda msg: self._vis_lbl.setText(f"Altitude tonight: ✗ ({msg})")
        )
        QThreadPool.globalInstance().start(runner)

    def _apply_visibility(self, summary: VisibilitySummary) -> None:
        parts = []
        if summary.altitude_now_deg is not None:
            parts.append(f"now {summary.altitude_now_deg:.1f}°")
        if summary.peak_altitude_deg is not None:
            t = summary.peak_time_utc.strftime("%H:%M UTC") if summary.peak_time_utc else ""
            parts.append(f"peak {summary.peak_altitude_deg:.1f}° at {t}")
        text = "Altitude tonight: " + (", ".join(parts) if parts else "unknown")
        color = theme.SUCCESS if summary.is_visible else theme.WARNING
        self._vis_lbl.setText(text)
        self._vis_lbl.setStyleSheet(
            f"color:{color}; font-size:11px; background:transparent;"
        )

    def selected_target(self) -> Optional[Target]:
        return self._target


# --------------------------------------------------------------------------- #
# Page 3: Plan                                                                 #
# --------------------------------------------------------------------------- #

class _PlanPage(QWizardPage):
    """Pick a profile; show duration + size estimate."""

    def __init__(self, wizard: "SessionWizard") -> None:
        super().__init__()
        self._wizard = wizard
        self.setTitle("Plan")
        self.setSubTitle("Pick an acquisition profile.")
        self._profiles: list[Profile] = load_profiles()
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(10)

        self._combo = QComboBox()
        for p in self._profiles:
            self._combo.addItem(p.name)
        self._combo.currentIndexChanged.connect(self._on_profile_changed)
        root.addWidget(self._combo)

        self._desc_lbl = QLabel("")
        self._desc_lbl.setWordWrap(True)
        self._desc_lbl.setStyleSheet(
            f"color:{theme.FG_MUTED}; font-size:11px; padding:4px 0;"
        )
        root.addWidget(self._desc_lbl)

        grid = QGridLayout()
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)
        self._frames_lbl  = _value_label("—")
        self._exptime_lbl = _value_label("—")
        self._gain_lbl    = _value_label("—")
        self._filter_lbl  = _value_label("—")
        self._total_lbl   = _value_label("—")
        self._size_lbl    = _value_label("—")
        grid.addWidget(QLabel("Frames"),   0, 0)
        grid.addWidget(self._frames_lbl,   0, 1)
        grid.addWidget(QLabel("Exposure"), 0, 2)
        grid.addWidget(self._exptime_lbl,  0, 3)
        grid.addWidget(QLabel("Gain"),     1, 0)
        grid.addWidget(self._gain_lbl,     1, 1)
        grid.addWidget(QLabel("Filter"),   1, 2)
        grid.addWidget(self._filter_lbl,   1, 3)
        grid.addWidget(QLabel("Duration"), 2, 0)
        grid.addWidget(self._total_lbl,    2, 1)
        grid.addWidget(QLabel("Disk"),     2, 2)
        grid.addWidget(self._size_lbl,     2, 3)
        root.addLayout(grid)
        root.addStretch()
        self._on_profile_changed(0)

    def _on_profile_changed(self, idx: int) -> None:
        if not (0 <= idx < len(self._profiles)):
            return
        p = self._profiles[idx]
        self._desc_lbl.setText(p.description)
        self._frames_lbl.setText(str(p.frames))
        self._exptime_lbl.setText(f"{p.exposure_s:.0f} s")
        self._gain_lbl.setText(str(p.gain))
        self._filter_lbl.setText(p.filter_name)
        self._total_lbl.setText(_fmt_duration(p.total_duration_s))
        self._size_lbl.setText(_fmt_size(p.estimated_size_mb))

    def selected_profile(self) -> Profile:
        return self._profiles[self._combo.currentIndex()]


# --------------------------------------------------------------------------- #
# Page 4: Acquire                                                              #
# --------------------------------------------------------------------------- #

class _AcquirePage(QWizardPage):
    """Final page: START → progress → session.json."""

    def __init__(self, wizard: "SessionWizard") -> None:
        super().__init__()
        self._wizard = wizard
        self.setTitle("Acquire")
        self.setSubTitle("Final review, then start the run.")
        self._session: Optional[Session] = None
        self._build_ui()
        wizard.capture_panel.log_message.connect(self._on_log)
        wizard.capture_panel.frame_display.connect(self._on_frame)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(10)

        self._review_lbl = QLabel("")
        self._review_lbl.setWordWrap(True)
        self._review_lbl.setStyleSheet(
            f"color:{theme.FG}; font-size:12px; padding:8px;"
            f"border:1px solid {theme.BORDER}; background:{theme.BG2};"
        )
        root.addWidget(self._review_lbl)

        self._start_btn = QPushButton("▶  START")
        self._start_btn.setProperty("class", "primary")
        self._start_btn.clicked.connect(self._on_start)
        root.addWidget(self._start_btn)

        self._progress = QProgressBar()
        self._progress.setRange(0, 1)
        root.addWidget(self._progress)

        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumHeight(120)
        root.addWidget(self._log)
        root.addStretch()

    def initializePage(self) -> None:
        target = self._wizard.target_page.selected_target()
        profile = self._wizard.plan_page.selected_profile()
        if target is None:
            return
        self._review_lbl.setText(
            f"<b>{target.name}</b>"
            f"<br>RA {target.ra_hours:.4f} h · Dec {target.dec_degrees:+.4f}°"
            f"<br>{profile.frames} × {profile.exposure_s:.0f} s · gain {profile.gain} · "
            f"filter {profile.filter_name}"
            f"<br>Estimated wall-clock: {_fmt_duration(profile.total_duration_s)}"
        )
        self._progress.setRange(0, profile.frames)
        self._progress.setValue(0)

    def isComplete(self) -> bool:
        # Allow Finish only after a session was actually started and completed.
        return self._session is not None and self._session.finished_at_utc is not None

    # ------------------------------------------------------------------
    # Actions / slots
    # ------------------------------------------------------------------

    def _on_start(self) -> None:
        target = self._wizard.target_page.selected_target()
        profile = self._wizard.plan_page.selected_profile()
        if target is None:
            return
        cfg = self._wizard.config
        self._session = Session.from_target(
            target=target,
            profile_name=profile.name,
            profile_summary=profile.description,
            frames_planned=profile.frames,
            observer=cfg.get("observer.name") or "",
            site_lat=cfg.get("site.latitude"),
            site_lon=cfg.get("site.longitude"),
            site_elev=cfg.get("site.elevation"),
        )
        self._start_btn.setEnabled(False)
        self._wizard.capture_panel.start_quick_session(
            target_ra=target.ra_hours,
            target_dec=target.dec_degrees,
            target_name=target.name,
            profile=profile,
        )

    def _on_log(self, level: str, message: str) -> None:
        if level not in {"OK", "INFO", "WARN", "ERROR"}:
            return
        self._log.append(f"[{level}] {message}")
        if self._session is None:
            return
        # "Saved X.fits" lines are the cue that a frame landed on disk.
        if level == "OK" and message.startswith("Saved "):
            self._session.record_frame(Path(message.removeprefix("Saved ").strip()))
            self._progress.setValue(self._session.frames_acquired)
            if self._session.frames_acquired >= self._session.frames_planned:
                self._finalize_session()

    def _on_frame(self, _arr) -> None:
        # Placeholder hook — could show a thumbnail here later.
        pass

    def _finalize_session(self) -> None:
        if self._session is None:
            return
        self._session.finish()
        # Write session.json into the same folder as the first frame.
        if self._session.frames_paths:
            folder = Path(self._session.frames_paths[0]).parent
            try:
                written = write_session_json(folder, self._session)
                self._log.append(f"[OK] session.json → {written}")
            except OSError as exc:
                self._log.append(f"[WARN] Could not write session.json: {exc}")
        self.completeChanged.emit()


# --------------------------------------------------------------------------- #
# Wizard shell                                                                 #
# --------------------------------------------------------------------------- #

class SessionWizard(QWizard):
    """4-step wizard. Drives the CapturePanel; never controls hardware directly."""

    def __init__(self, capture_panel, config: Config, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.capture_panel = capture_panel
        self.config = config
        self.setWindowTitle("Quick Session")
        self.setOption(QWizard.WizardOption.NoBackButtonOnStartPage, True)
        self.setOption(QWizard.WizardOption.NoCancelButtonOnLastPage, True)
        self.setMinimumSize(680, 540)

        self.connect_page = _ConnectPage(self)
        self.target_page  = _TargetPage(self)
        self.plan_page    = _PlanPage(self)
        self.acquire_page = _AcquirePage(self)
        for page in (self.connect_page, self.target_page, self.plan_page, self.acquire_page):
            self.addPage(page)

    def stellarium_http_settings(self) -> tuple[str, int]:
        # Mirror the panel's Stellarium card defaults.
        return "127.0.0.1", 8090


# --------------------------------------------------------------------------- #
# Tiny UI helpers                                                              #
# --------------------------------------------------------------------------- #

def _status_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(
        f"color:{theme.FG_MUTED}; font-size:12px; background:transparent;"
    )
    return lbl


def _value_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(
        f"color:{theme.ACCENT}; font-size:12px; font-family:{theme.FONT_MONO};"
        f" background:transparent;"
    )
    return lbl


def _fmt_duration(seconds: float) -> str:
    m = int(seconds // 60)
    s = int(seconds % 60)
    if m >= 60:
        h, m = divmod(m, 60)
        return f"{h} h {m:02d} m"
    return f"{m} m {s:02d} s"


def _fmt_size(mb: float) -> str:
    if mb >= 1024:
        return f"{mb / 1024:.1f} GB"
    return f"{mb:.0f} MB"
