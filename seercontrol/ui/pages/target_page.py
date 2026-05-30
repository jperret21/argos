"""Target mode — choose a target, pick a profile, then slew and start.

This page is R4 of the redesign sprint. It replaces the ``SessionWizard``
modal (``Cmd+N``) with a persistent mode the user can return to at any time.

Flow
----
1. User types a target name and clicks **Resolve** (or **⇣ Stellarium**)
   → off-thread Simbad query (cached) + visibility calculation
2. Resolved info panel shows name / type / magnitude / visibility summary
3. User picks a profile from the combo; override fields fill from the profile
4. User clicks **▶ Slew + Start** → page emits ``slew_and_start_requested``
   and the Shell switches to Imaging mode + triggers ImagingPage.slew_and_start()

The page emits one upward signal:
    slew_and_start_requested(ra_hours: float, dec_degrees: float, profile: Profile)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from PyQt6.QtCore import QObject, QRunnable, QThreadPool, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from seercontrol.core.config import Config
from seercontrol.core.profiles import Profile, load_profiles
from seercontrol.core.targets.resolver import Target, resolve_name
from seercontrol.ui import design, theme

logger = logging.getLogger(__name__)

_DEFAULT_STELLARIUM_HOST = "localhost"
_DEFAULT_STELLARIUM_PORT = 8090


# --------------------------------------------------------------------------- #
# Off-thread runners                                                           #
# --------------------------------------------------------------------------- #

class _ResolveSignals(QObject):
    resolved = pyqtSignal(object, object)   # target: Target, vis: VisibilitySummary|None
    failed   = pyqtSignal(str)


class _ResolveRunner(QRunnable):
    """Off-thread: Simbad resolve + optional visibility check."""

    def __init__(
        self,
        name: str,
        site_lat: float | None,
        site_lon: float | None,
        site_elev: float,
    ) -> None:
        super().__init__()
        self._name      = name
        self._site_lat  = site_lat
        self._site_lon  = site_lon
        self._site_elev = site_elev
        self.signals    = _ResolveSignals()

    def run(self) -> None:
        try:
            target = resolve_name(self._name)
        except Exception as exc:
            self.signals.failed.emit(str(exc))
            return
        if target is None:
            self.signals.failed.emit(f"'{self._name}' not found in Simbad")
            return

        vis = None
        if self._site_lat is not None and self._site_lon is not None:
            try:
                from seercontrol.core.targets.horizon import visibility_tonight
                vis = visibility_tonight(
                    target.ra_hours,
                    target.dec_degrees,
                    self._site_lat,
                    self._site_lon,
                    self._site_elev,
                    when_utc=datetime.now(tz=timezone.utc),
                )
            except Exception as exc:
                logger.debug("visibility_tonight failed: %s", exc)

        self.signals.resolved.emit(target, vis)


class _PullSignals(QObject):
    target = pyqtSignal(str, float, float)  # name, ra_hours, dec_degrees
    failed = pyqtSignal(str)


class _PullRunner(QRunnable):
    """Off-thread: HTTP pull from Stellarium Remote Control plugin."""

    def __init__(self, host: str, port: int) -> None:
        super().__init__()
        self._host = host
        self._port = port
        self.signals = _PullSignals()

    def run(self) -> None:
        try:
            from seercontrol.core.stellarium.remote_pull import pull_selected_object
            target = pull_selected_object(host=self._host, port=self._port)
        except Exception as exc:
            self.signals.failed.emit(str(exc))
            return
        if target is None:
            self.signals.failed.emit("No selection or Stellarium plugin not running")
            return
        self.signals.target.emit(target.name, target.ra_hours, target.dec_degrees)


# --------------------------------------------------------------------------- #
# TargetPage                                                                   #
# --------------------------------------------------------------------------- #

class TargetPage(QWidget):
    """R4 — full target picking + profile selection + slew-and-start."""

    slew_and_start_requested = pyqtSignal(float, float, object, str)  # ra_h, dec_d, Profile, object_name

    def __init__(self, config: Config, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._config = config
        self._resolved: Target | None = None
        self._profiles: list[Profile] = load_profiles()
        self._current_ra:  float | None = None
        self._current_dec: float | None = None
        # Keep strong refs to in-flight runners so they're not GC'd mid-run.
        self._resolve_runner: _ResolveRunner | None = None
        self._pull_runner:    _PullRunner    | None = None
        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        root.addWidget(scroll)

        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(design.SPACING_XL, design.SPACING_XL,
                                  design.SPACING_XL, design.SPACING_XL)
        layout.setSpacing(design.SPACING_LG)

        layout.addWidget(design.HeadingLabel("Target"))
        layout.addWidget(self._build_target_card())
        layout.addWidget(self._build_profile_card())
        layout.addWidget(self._build_override_card())
        self._on_profile_changed(0)  # fill overrides from first profile

        self._start_btn = design.SuccessButton("▶  Slew + Start acquisition")
        self._start_btn.setMinimumHeight(48)
        self._start_btn.setEnabled(False)
        self._start_btn.clicked.connect(self._on_slew_and_start)
        layout.addWidget(self._start_btn)

        layout.addStretch()
        scroll.setWidget(inner)

    def _build_target_card(self) -> design.Card:
        card = design.Card("1. Pick a target")
        outer = design.card_layout(card)

        # Name + Resolve
        name_row = QHBoxLayout()
        name_row.setSpacing(design.SPACING_SM)
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("e.g. T CrB, M42, NGC 224…")
        self._name_edit.setMinimumHeight(design.INPUT_HEIGHT)
        self._name_edit.returnPressed.connect(self._on_resolve)
        name_row.addWidget(self._name_edit, 1)
        self._resolve_btn = design.PrimaryButton("Resolve")
        self._resolve_btn.setMaximumWidth(100)
        self._resolve_btn.clicked.connect(self._on_resolve)
        name_row.addWidget(self._resolve_btn)
        outer.addLayout(name_row)

        # Stellarium pull row
        stell_row = QHBoxLayout()
        stell_row.setSpacing(design.SPACING_SM)
        stell_form = QFormLayout()
        stell_form.setHorizontalSpacing(design.SPACING_SM)
        self._stell_host = QLineEdit(_DEFAULT_STELLARIUM_HOST)
        self._stell_host.setFixedWidth(120)
        self._stell_host.setMinimumHeight(design.INPUT_HEIGHT)
        self._stell_port = QSpinBox()
        self._stell_port.setRange(1, 65535)
        self._stell_port.setValue(_DEFAULT_STELLARIUM_PORT)
        self._stell_port.setMinimumHeight(design.INPUT_HEIGHT)
        stell_form.addRow(design.MutedLabel("Stellarium"), self._stell_host)
        stell_row.addLayout(stell_form)
        stell_row.addWidget(self._stell_port)
        self._stell_btn = design.SecondaryButton("⇣  Pull selection")
        self._stell_btn.setToolTip(
            "Import the currently selected object from Stellarium\n"
            "(requires the RemoteControl plugin running)"
        )
        self._stell_btn.clicked.connect(self._on_pull_stellarium)
        stell_row.addWidget(self._stell_btn)
        outer.addLayout(stell_row)

        outer.addWidget(design.horizontal_divider())

        # Manual RA / Dec (always editable)
        coord_form = QFormLayout()
        coord_form.setHorizontalSpacing(design.SPACING_MD)
        coord_form.setVerticalSpacing(design.SPACING_SM)
        self._ra_spin = QDoubleSpinBox()
        self._ra_spin.setRange(0.0, 23.9999)
        self._ra_spin.setDecimals(4)
        self._ra_spin.setSuffix("  h")
        self._ra_spin.setMinimumHeight(design.INPUT_HEIGHT)
        self._dec_spin = QDoubleSpinBox()
        self._dec_spin.setRange(-90.0, 90.0)
        self._dec_spin.setDecimals(4)
        self._dec_spin.setSuffix("  °")
        self._dec_spin.setMinimumHeight(design.INPUT_HEIGHT)
        coord_form.addRow(design.MutedLabel("RA"), self._ra_spin)
        coord_form.addRow(design.MutedLabel("Dec"), self._dec_spin)
        outer.addLayout(coord_form)
        use_manual_btn = design.SecondaryButton("Use these coords")
        use_manual_btn.setToolTip("Treat the manual RA/Dec above as the current target")
        use_manual_btn.clicked.connect(self._on_use_manual)
        outer.addLayout(design.button_row(use_manual_btn))

        outer.addWidget(design.horizontal_divider())

        # Resolved info panel
        self._info_lbl = QLabel("")
        self._info_lbl.setWordWrap(True)
        self._info_lbl.setTextFormat(Qt.TextFormat.RichText)
        self._info_lbl.setStyleSheet(f"background:transparent; color:{theme.FG};")
        self._info_lbl.hide()
        outer.addWidget(self._info_lbl)

        # Resolve spinner (busy indicator)
        self._resolving_lbl = QLabel("Resolving…")
        self._resolving_lbl.setStyleSheet(
            f"color:{theme.FG_MUTED}; font-size:11px; background:transparent;"
        )
        self._resolving_lbl.hide()
        outer.addWidget(self._resolving_lbl)

        return card

    def _build_profile_card(self) -> design.Card:
        card = design.Card("2. Acquisition profile")
        outer = design.card_layout(card)

        self._profile_combo = QComboBox()
        self._profile_combo.setMinimumHeight(design.INPUT_HEIGHT)
        for p in self._profiles:
            self._profile_combo.addItem(p.name)
        self._profile_combo.currentIndexChanged.connect(self._on_profile_changed)
        outer.addWidget(self._profile_combo)

        self._profile_summary = QLabel("")
        self._profile_summary.setWordWrap(True)
        self._profile_summary.setStyleSheet(
            f"color:{theme.FG_MUTED}; font-size:11px; background:transparent;"
            f" padding-top:4px;"
        )
        outer.addWidget(self._profile_summary)
        return card

    def _build_override_card(self) -> design.Card:
        card = design.Card("3. Override (optional)")
        outer = design.card_layout(card)

        form = QFormLayout()
        form.setHorizontalSpacing(design.SPACING_MD)
        form.setVerticalSpacing(design.SPACING_SM)

        self._ov_object = QLineEdit()
        self._ov_object.setPlaceholderText("auto-filled from name")
        self._ov_object.setMinimumHeight(design.INPUT_HEIGHT)
        form.addRow(design.MutedLabel("Object"), self._ov_object)

        self._ov_frames = QSpinBox()
        self._ov_frames.setRange(1, 9999)
        self._ov_frames.setMinimumHeight(design.INPUT_HEIGHT)
        form.addRow(design.MutedLabel("Frames"), self._ov_frames)

        self._ov_exp = QDoubleSpinBox()
        self._ov_exp.setRange(0.001, 600.0)
        self._ov_exp.setDecimals(1)
        self._ov_exp.setSuffix(" s")
        self._ov_exp.setMinimumHeight(design.INPUT_HEIGHT)
        form.addRow(design.MutedLabel("Exposure"), self._ov_exp)

        self._ov_gain = QSpinBox()
        self._ov_gain.setRange(0, 600)
        self._ov_gain.setMinimumHeight(design.INPUT_HEIGHT)
        form.addRow(design.MutedLabel("Gain"), self._ov_gain)

        self._ov_filter = QComboBox()
        self._ov_filter.setMinimumHeight(design.INPUT_HEIGHT)
        for f in ("LP", "IR-cut", "Ha", "OIII", "SII", "LRGB", "Dark"):
            self._ov_filter.addItem(f)
        form.addRow(design.MutedLabel("Filter"), self._ov_filter)

        outer.addLayout(form)
        return card

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _current_profile(self) -> Profile | None:
        idx = self._profile_combo.currentIndex()
        if 0 <= idx < len(self._profiles):
            return self._profiles[idx]
        return None

    def _build_override_profile(self) -> Profile | None:
        """Build a Profile from the override fields, or None if no base profile."""
        base = self._current_profile()
        if base is None:
            return None
        obj_name = self._ov_object.text().strip()
        return Profile(
            name=base.name,
            description=base.description,
            frame_type=base.frame_type,
            exposure_s=self._ov_exp.value(),
            gain=self._ov_gain.value(),
            filter_name=self._ov_filter.currentText(),
            frames=self._ov_frames.value(),
            continuous=base.continuous,
            tags=base.tags,
        ), obj_name  # type: ignore[return-value]

    def _update_info(self, target: Target, vis) -> None:
        """Render the resolved target info panel."""
        mag_str = f"  ·  V≈{target.magnitude:.1f}" if target.magnitude is not None else ""
        otype = target.object_type or "—"
        ra_str  = f"{target.ra_hours:.4f} h"
        dec_str = f"{target.dec_degrees:+.4f}°"

        html = (
            f"<b style='color:{theme.ACCENT}'>{target.name}</b>"
            f"<span style='color:{theme.FG_MUTED}'> · {otype}{mag_str}</span><br>"
            f"<span style='color:{theme.FG_MUTED}'>RA </span>"
            f"<span style='color:{theme.FG}'>{ra_str}</span>"
            f"<span style='color:{theme.FG_MUTED}'>  Dec </span>"
            f"<span style='color:{theme.FG}'>{dec_str}</span>"
        )
        if vis is not None:
            if vis.is_visible and vis.peak_altitude_deg is not None:
                peak_t = ""
                if vis.peak_time_utc:
                    peak_t = vis.peak_time_utc.strftime(" at %H:%M UTC")
                html += (
                    f"<br><span style='color:{theme.SUCCESS}'>✓ Peak "
                    f"{vis.peak_altitude_deg:.1f}°{peak_t}</span>"
                )
            elif vis.peak_altitude_deg is not None:
                html += (
                    f"<br><span style='color:{theme.WARNING}'>⚠ Low peak "
                    f"{vis.peak_altitude_deg:.1f}° — may be hard to image</span>"
                )
            else:
                html += f"<br><span style='color:{theme.FG_MUTED}'>Visibility unknown</span>"

        self._info_lbl.setText(html)
        self._info_lbl.show()

    def _set_coords(self, ra_h: float, dec_d: float) -> None:
        self._ra_spin.setValue(ra_h)
        self._dec_spin.setValue(dec_d)
        self._current_ra  = ra_h
        self._current_dec = dec_d
        self._start_btn.setEnabled(True)

    # ------------------------------------------------------------------
    # Public API (called by Shell)
    # ------------------------------------------------------------------

    def set_target(self, name: str, ra_hours: float, dec_degrees: float) -> None:
        """Pre-fill from an external source (Stellarium push, deep-link).

        Fills the name, coords, and override fields without hitting the network.
        The user can still click Resolve to get visibility info.
        """
        self._name_edit.setText(name)
        self._ov_object.setText(name)
        self._set_coords(ra_hours, dec_degrees)
        self._info_lbl.setText(
            f"<span style='color:{theme.FG_MUTED}'>"
            f"RA {ra_hours:.4f} h  Dec {dec_degrees:+.4f}°</span>"
        )
        self._info_lbl.show()

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_resolve(self) -> None:
        name = self._name_edit.text().strip()
        if not name:
            return
        self._resolving_lbl.show()
        self._info_lbl.hide()
        self._resolve_btn.setEnabled(False)

        site_lat  = self._config.get("site.latitude")
        site_lon  = self._config.get("site.longitude")
        site_elev = float(self._config.get("site.elevation") or 0)

        runner = _ResolveRunner(
            name=name,
            site_lat=float(site_lat)  if site_lat  is not None else None,
            site_lon=float(site_lon)  if site_lon  is not None else None,
            site_elev=site_elev,
        )
        runner.signals.resolved.connect(self._on_resolved)
        runner.signals.failed.connect(self._on_resolve_failed)
        # Hold a strong reference until the runner emits its result.
        runner.signals.resolved.connect(lambda *_: setattr(self, "_resolve_runner", None))
        runner.signals.failed.connect(lambda *_: setattr(self, "_resolve_runner", None))
        self._resolve_runner = runner
        QThreadPool.globalInstance().start(runner)

    def _on_resolved(self, target: Target, vis) -> None:
        self._resolving_lbl.hide()
        self._resolve_btn.setEnabled(True)
        self._resolved = target
        self._ov_object.setText(target.name)
        self._set_coords(target.ra_hours, target.dec_degrees)
        self._update_info(target, vis)
        logger.info(
            "Resolved '%s' → %s  RA %.4f h  Dec %+.4f°",
            target.queried_name, target.name, target.ra_hours, target.dec_degrees,
        )

    def _on_resolve_failed(self, message: str) -> None:
        self._resolving_lbl.hide()
        self._resolve_btn.setEnabled(True)
        self._info_lbl.setText(
            f"<span style='color:{theme.DANGER}'>✗ {message}</span>"
        )
        self._info_lbl.show()
        logger.warning("Resolve failed: %s", message)

    def _on_pull_stellarium(self) -> None:
        host = self._stell_host.text().strip() or _DEFAULT_STELLARIUM_HOST
        port = int(self._stell_port.value())
        self._stell_btn.setEnabled(False)
        runner = _PullRunner(host=host, port=port)
        runner.signals.target.connect(self._on_stellarium_target)
        runner.signals.failed.connect(self._on_stellarium_failed)
        runner.signals.target.connect(lambda *_: setattr(self, "_pull_runner", None))
        runner.signals.failed.connect(lambda *_: setattr(self, "_pull_runner", None))
        self._pull_runner = runner
        QThreadPool.globalInstance().start(runner)

    def _on_stellarium_target(self, name: str, ra_hours: float, dec_degrees: float) -> None:
        self._stell_btn.setEnabled(True)
        self._name_edit.setText(name)
        self._ov_object.setText(name)
        self._set_coords(ra_hours, dec_degrees)
        self._info_lbl.setText(
            f"<span style='color:{theme.SUCCESS}'>⇣ Imported from Stellarium: "
            f"<b>{name}</b></span>"
        )
        self._info_lbl.show()
        logger.info("Stellarium pull: %s  RA %.4f  Dec %+.4f", name, ra_hours, dec_degrees)

    def _on_stellarium_failed(self, message: str) -> None:
        self._stell_btn.setEnabled(True)
        self._info_lbl.setText(
            f"<span style='color:{theme.WARNING}'>⚠ Stellarium: {message}</span>"
        )
        self._info_lbl.show()

    def _on_use_manual(self) -> None:
        ra  = self._ra_spin.value()
        dec = self._dec_spin.value()
        self._set_coords(ra, dec)
        if not self._ov_object.text().strip():
            self._ov_object.setText("Manual target")
        self._info_lbl.setText(
            f"<span style='color:{theme.FG_MUTED}'>"
            f"Manual coords: RA {ra:.4f} h  Dec {dec:+.4f}°</span>"
        )
        self._info_lbl.show()

    def _on_profile_changed(self, _index: int) -> None:
        profile = self._current_profile()
        if profile is None:
            self._profile_summary.setText("")
            return
        mins = int(profile.total_duration_s / 60)
        mb   = int(profile.estimated_size_mb)
        self._profile_summary.setText(
            f"{profile.frames} × {profile.exposure_s:.0f} s  ·  "
            f"gain {profile.gain}  ·  {profile.filter_name}  ·  "
            f"~{mins} min  ·  {mb} MB"
        )
        # Pre-fill overrides with profile defaults
        self._ov_frames.setValue(profile.frames)
        self._ov_exp.setValue(profile.exposure_s)
        self._ov_gain.setValue(profile.gain)
        idx = self._ov_filter.findText(profile.filter_name)
        if idx >= 0:
            self._ov_filter.setCurrentIndex(idx)

    def _on_slew_and_start(self) -> None:
        if self._current_ra is None or self._current_dec is None:
            return
        result = self._build_override_profile()
        if result is None:
            return
        profile, obj_name = result
        self.slew_and_start_requested.emit(
            float(self._current_ra),
            float(self._current_dec),
            profile,
            obj_name,
        )
