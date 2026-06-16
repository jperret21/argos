"""Photometry Setup Window — the "mission control" for a photometry session.

Opens a reference frame from a sequence (last frame by default), plate-solves it,
lets the user select variable stars (VSX catalog), assign comparison stars (VSP),
configure photometry parameters, and save/load target sets. A "Run Photometry"
button processes all frames in the sequence and sends light curves to the
``PhotometryWindow``.

Layout::

    ┌────────────────────────────────────────────────────────────┐
    │  Photometry Setup — [object name]                          │
    ├────────────────────────────────┬───────────────────────────┤
    │                                │  Reference frame          │
    │     FITS Viewer                 │  ────────────────────    │
    │     (clickable)                 │  last_seq_frame_001.fits │
    │                                │  [Browse…]                │
    │                                │                           │
    │                                │  ── Astrometry ──         │
    │                                │  [Solve]  ✓ solved        │
    │                                │  RA 5.5858h ...           │
    │                                │                           │
    │                                │  ── Variables (VSX) ──  │
    │                                │  Mag limit [15.0]         │
    │                                │  ☑ suspected              │
    │                                │  [Fetch]                  │
    │                                │  ┌─ V1234  RRCr  12.3 ─┐ │
    │                                │  │  V5678  EA    11.5     │ │
    │                                │  └─ V9012  M    14.1  ─┘ │
    │                                │                           │
    │                                │  ── Targets ──           │
    │                                │  Target:  V1234   [×]    │
    │                                │  Comp:    C5678   [×]    │
    │                                │  Check:   C9012   [×]    │
    │                                │  [Assign selected star]   │
    │                                │                           │
    │                                │  ── Photometry ──        │
    │                                │  Aperture [8.0] px        │
    │                                │  Annulus  12 / 16 px     │
    │                                │  Band      [V]            │
    │                                │                           │
    │                                │  [Save targets] [Load]    │
    │                                │  [▶ Run Photometry]      │
    └────────────────────────────────┴───────────────────────────┘
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from seercontrol.core.catalog.targets import (
    ROLE_CHECK,
    ROLE_COMPARISON,
    ROLE_TARGET,
    TargetSet,
    TargetStar,
)
from seercontrol.core.imaging.astrometry_session import (
    build_solve_settings,
    field_geometry,
    full_res_scale,
    overlay_for,
    project_points,
    wcs_from_result,
)
from seercontrol.core.imaging.debayer import VIEW_G, VIEW_RAW, extract_plane
from seercontrol.core.imaging.metrics import (
    ARCSEC_PER_GREEN_PX,
    DEFAULT_STAR_RADIUS,
    TRACK_SNAP_SEARCH,
    measure_star_at,
)
from seercontrol.ui import theme
from seercontrol.ui.analysis_window import read_fits_2d, read_fits_meta  # shared FITS read helpers
from seercontrol.ui.widgets.fits_viewer import FitsViewer
from seercontrol.workers.catalog_worker import CatalogRequest, CatalogWorker
from seercontrol.workers.preview_processor import build_processed_frame
from seercontrol.workers.solve_worker import SolveWorker

logger = logging.getLogger(__name__)


class PhotometrySetupWindow(QWidget):
    """Floating window — configure targets and photometry for a sequence."""

    def __init__(self, config=None, sequence_dir: str | Path | None = None, parent=None):
        super().__init__(parent)
        self._config = config
        self._sequence_dir = Path(sequence_dir) if sequence_dir else None
        self.setWindowFlag(Qt.WindowType.Window, True)
        self.setWindowTitle("Photometry Setup")
        self.resize(1200, 720)

        # ── State ──────────────────────────────────────────────
        self._raw: np.ndarray | None = None
        self._channel = VIEW_RAW
        self._radius = DEFAULT_STAR_RADIUS
        self._green_shape: tuple[int, int] | None = None
        self._disp_shape: tuple[int, int] | None = None
        self._selected_green: tuple[float, float] | None = None
        self._wcs = None  # FrameWCS once solved
        self._solver: SolveWorker | None = None
        self._catalog_worker: CatalogWorker | None = None
        self._variables: list = []  # VSX variables
        self._var_green: list = []  # parallel green-px positions (None = off-frame)
        self._comparisons: list = []  # VSP comparisons
        self._comp_green: list = []  # parallel green-px
        self._object_name: str = ""
        self._target_set: TargetSet | None = None
        self._catalog_centre: tuple[float, float] | None = None

        self._build_ui()
        self._wire()
        self._load_default_frame()

    # ══════════════════════════════════════════════════════════
    # UI
    # ══════════════════════════════════════════════════════════

    def _build_ui(self) -> None:
        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Left: Viewer ──────────────────────────────────────
        self._viewer = FitsViewer()
        root.addWidget(self._viewer, 1)

        # ── Right: Setup panel ────────────────────────────────
        right = QWidget()
        right.setMinimumWidth(380)
        right.setMaximumWidth(480)
        col = QVBoxLayout(right)
        col.setContentsMargins(8, 8, 8, 8)
        col.setSpacing(8)

        # Reference frame
        ref_group = QGroupBox("Reference frame")
        ref_layout = QVBoxLayout(ref_group)
        self._frame_label = QLabel("No frame loaded")
        self._frame_label.setWordWrap(True)
        self._frame_label.setStyleSheet(f"color:{theme.FG_MUTED}; font-size:11px;")
        ref_layout.addWidget(self._frame_label)
        self._browse_btn = QPushButton("Browse…")
        ref_layout.addWidget(self._browse_btn)
        col.addWidget(ref_group)

        # Astrometry group
        astro_group = QGroupBox("Astrometry")
        astro_layout = QVBoxLayout(astro_group)
        self._solve_btn = QPushButton("Solve (ASTAP)")
        self._solve_btn.clicked.connect(self._on_solve)
        astro_layout.addWidget(self._solve_btn)
        self._solve_lbl = QLabel("Not solved")
        self._solve_lbl.setStyleSheet(
            f"color:{theme.FG_MUTED}; font-family:{theme.FONT_MONO}; font-size:11px;"
        )
        astro_layout.addWidget(self._solve_lbl)
        col.addWidget(astro_group)

        # Catalog / Variables
        cat_group = QGroupBox("Variables (VSX)")
        cat_layout = QVBoxLayout(cat_group)

        cat_top = QHBoxLayout()
        cat_top.addWidget(QLabel("Mag limit:"))
        self._mag_spin = QSpinBox()
        self._mag_spin.setRange(5, 25)
        self._mag_spin.setValue(15)
        cat_top.addWidget(self._mag_spin)
        self._suspected_chk = QCheckBox("Suspected")
        self._suspected_chk.setChecked(True)
        cat_top.addWidget(self._suspected_chk)
        cat_layout.addLayout(cat_top)

        self._fetch_btn = QPushButton("Fetch VSX")
        self._fetch_btn.clicked.connect(self._on_fetch)
        cat_layout.addWidget(self._fetch_btn)

        self._var_list = QListWidget()
        self._var_list.setAlternatingRowColors(True)
        self._var_list.setMinimumHeight(120)
        self._var_list.itemClicked.connect(self._on_var_clicked)
        cat_layout.addWidget(self._var_list)
        col.addWidget(cat_group)

        # Targets
        tgt_group = QGroupBox("Targets")
        tgt_layout = QVBoxLayout(tgt_group)

        self._target_list = QListWidget()
        self._target_list.setMinimumHeight(80)
        tgt_layout.addWidget(self._target_list)

        tgt_btns = QHBoxLayout()
        self._target_btn = QPushButton("Mark as Target")
        self._target_btn.clicked.connect(lambda: self._assign_role(ROLE_TARGET))
        tgt_btns.addWidget(self._target_btn)
        self._comp_btn = QPushButton("Mark as Comp")
        self._comp_btn.clicked.connect(lambda: self._assign_role(ROLE_COMPARISON))
        tgt_btns.addWidget(self._comp_btn)
        self._check_btn = QPushButton("Mark as Check")
        self._check_btn.clicked.connect(lambda: self._assign_role(ROLE_CHECK))
        tgt_btns.addWidget(self._check_btn)
        self._remove_btn = QPushButton("✕")
        self._remove_btn.setToolTip("Remove selected target")
        self._remove_btn.clicked.connect(self._on_remove_target)
        tgt_btns.addWidget(self._remove_btn)
        tgt_layout.addLayout(tgt_btns)
        col.addWidget(tgt_group)

        # Photometry settings
        phot_group = QGroupBox("Photometry")
        phot_layout = QFormLayout(phot_group)
        self._aperture_spin = QSpinBox()
        self._aperture_spin.setRange(2, 60)
        self._aperture_spin.setValue(8)
        self._aperture_spin.setSuffix(" px")
        phot_layout.addRow("Aperture radius:", self._aperture_spin)
        self._annulus_in = QSpinBox()
        self._annulus_in.setRange(4, 100)
        self._annulus_in.setValue(12)
        self._annulus_in.setSuffix(" px")
        phot_layout.addRow("Annulus inner:", self._annulus_in)
        self._annulus_out = QSpinBox()
        self._annulus_out.setRange(6, 120)
        self._annulus_out.setValue(16)
        self._annulus_out.setSuffix(" px")
        phot_layout.addRow("Annulus outer:", self._annulus_out)
        self._band_combo = QComboBox()
        self._band_combo.addItems(["V", "B", "R", "I", "g'", "r'", "i'", "Clear"])
        phot_layout.addRow("Photometric band:", self._band_combo)
        col.addWidget(phot_group)

        # Action buttons
        actions = QHBoxLayout()
        self._save_btn = QPushButton("Save targets")
        self._save_btn.clicked.connect(self._on_save)
        actions.addWidget(self._save_btn)
        self._load_btn = QPushButton("Load")
        self._load_btn.clicked.connect(self._on_load)
        actions.addWidget(self._load_btn)
        col.addLayout(actions)

        self._run_btn = QPushButton("▶ Run Photometry")
        self._run_btn.setStyleSheet(
            f"background:{theme.SUCCESS}; color:#000; font-weight:700; padding:8px;"
        )
        self._run_btn.clicked.connect(self._on_run)
        col.addWidget(self._run_btn)

        col.addStretch()

        # Wrap right panel in a scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidget(right)

        split = QSplitter(Qt.Orientation.Horizontal)
        split.setChildrenCollapsible(False)
        split.addWidget(self._viewer)
        split.addWidget(scroll)
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 0)
        split.setSizes([800, 420])
        root.addWidget(split, 1)

        self.setLayout(root)

    def _wire(self) -> None:
        self._viewer.star_clicked.connect(self._on_star_clicked)
        self._browse_btn.clicked.connect(self._on_browse)

    # ══════════════════════════════════════════════════════════
    # Frame loading
    # ══════════════════════════════════════════════════════════

    def _load_default_frame(self) -> None:
        """Open the last saved frame from the sequence directory, if any."""
        if self._sequence_dir is None or not self._sequence_dir.exists():
            self._frame_label.setText("No sequence frames found.\nClick Browse to load one.")
            return
        # Find the most recent .fits file in the sequence directory.
        fits_files = sorted(self._sequence_dir.glob("*.fits"), key=lambda p: p.stat().st_mtime)
        if not fits_files:
            fits_files = sorted(self._sequence_dir.rglob("*.fits"), key=lambda p: p.stat().st_mtime)
        if not fits_files:
            self._frame_label.setText("No FITS files in sequence folder.")
            return
        self.load_frame(str(fits_files[-1]))

    def load_frame(self, path: str) -> None:
        """Load a FITS file as the reference frame."""
        try:
            arr = read_fits_2d(path)
        except Exception as exc:
            QMessageBox.warning(self, "Load error", f"Could not read {path}\n{exc}")
            return
        if arr is None:
            QMessageBox.warning(self, "Load error", f"Invalid FITS: {path}")
            return
        self._raw = arr
        meta = read_fits_meta(path)
        self._object_name = meta.get("OBJECT", Path(path).stem)
        self._frame_label.setText(Path(path).name)
        self._wcs = None
        self._variables = []
        self._var_green = []
        self._comparisons = []
        self._comp_green = []
        self._catalog_centre = None
        self._var_list.clear()
        self._target_list.clear()
        self._target_set = None
        self._solve_lbl.setText("Not solved")
        self._solve_lbl.setStyleSheet(
            f"color:{theme.FG_MUTED}; font-family:{theme.FONT_MONO}; font-size:11px;"
        )
        self._viewer.set_astrometry_overlay(None)
        self._selected_green = None
        self._viewer.clear_selection()
        self.setWindowTitle(f"Photometry Setup — {self._object_name}")
        self._reprocess()
        # Load the existing target set for this object, if any.
        self._target_set = self._load_target_set()
        self._refresh_target_list()

    def _reprocess(self) -> None:
        if self._raw is None:
            return
        pf = build_processed_frame(self._raw, self._channel, self._radius)
        self._green_shape = pf.green_shape
        self._disp_shape = pf.display.shape[:2]
        self._viewer.set_stars(pf.stars, pf.green_shape)
        self._viewer.display(pf.display)
        self._remeasure_selection()

    def _on_browse(self) -> None:
        start = str(Path.home() / "Downloads")
        path, _ = QFileDialog.getOpenFileName(
            self, "Select reference frame", start, "FITS (*.fits *.fit *.fts);;All files (*)"
        )
        if path:
            self.load_frame(path)

    # ══════════════════════════════════════════════════════════
    # Plate-solving
    # ══════════════════════════════════════════════════════════

    def _cfg(self, key: str, default):
        if self._config is None:
            return default
        value = self._config.get(key, default)
        return default if value is None else value

    def _on_solve(self) -> None:
        if self._raw is None or (self._solver is not None and self._solver.isRunning()):
            return
        green = extract_plane(self._raw, VIEW_G)
        settings = build_solve_settings(self._cfg, self._green_shape, live=False)
        self._solve_btn.setEnabled(False)
        self._solve_lbl.setText("Solving… (ASTAP)")
        self._solve_lbl.setStyleSheet(
            f"color:{theme.WARNING}; font-family:{theme.FONT_MONO}; font-size:11px;"
        )
        self._solver = SolveWorker(green, settings, parent=self)
        self._solver.solved.connect(self._on_solved)
        self._solver.start()

    def _on_solved(self, result) -> None:
        self._solve_btn.setEnabled(True)
        if not result.solved:
            self._solve_lbl.setText(f"Failed — {result.message}")
            self._solve_lbl.setStyleSheet(
                f"color:{theme.DANGER}; font-family:{theme.FONT_MONO}; font-size:11px;"
            )
            return
        bits = [f"RA {result.ra_hours:.4f}h", f"Dec {result.dec_deg:+.4f}°"]
        scale = full_res_scale(result)
        if scale is not None:
            bits.append(f"{scale:.2f}″/px")
        self._solve_lbl.setText("Solved — " + "   ".join(bits))
        self._solve_lbl.setStyleSheet(
            f"color:{theme.SUCCESS}; font-family:{theme.FONT_MONO}; font-size:11px;"
        )
        self._wcs = wcs_from_result(result, self._green_shape)
        if self._wcs is not None:
            overlay = overlay_for(self._wcs, self._green_shape, self._cfg)
            self._viewer.set_astrometry_overlay(overlay, self._green_shape)
            self._remeasure_selection()

    # ══════════════════════════════════════════════════════════
    # VSX catalog
    # ══════════════════════════════════════════════════════════

    def _on_fetch(self) -> None:
        if self._wcs is None or self._green_shape is None:
            QMessageBox.information(
                self, "Need a solve", "Plate-solve the frame before fetching the catalog."
            )
            return
        if self._catalog_worker is not None and self._catalog_worker.isRunning():
            return
        geom = field_geometry(self._wcs, self._green_shape)
        if geom is None:
            return
        ra_deg, dec_deg, radius_deg, fov_arcmin = geom
        self._catalog_centre = (ra_deg, dec_deg)
        req = CatalogRequest(
            ra_deg=ra_deg,
            dec_deg=dec_deg,
            radius_deg=radius_deg,
            fov_arcmin=fov_arcmin,
            mag_limit=float(self._mag_spin.value()),
            max_results=int(self._cfg("catalog.max_results", 250)),
            include_suspected=self._suspected_chk.isChecked(),
        )
        self._fetch_btn.setEnabled(False)
        self._fetch_btn.setText("Fetching…")
        self._catalog_worker = CatalogWorker(req, parent=self)
        self._catalog_worker.fetched.connect(self._on_catalog)
        self._catalog_worker.start()

    def _on_catalog(self, result) -> None:
        self._fetch_btn.setEnabled(True)
        self._fetch_btn.setText("Fetch VSX")
        if not result.ok:
            QMessageBox.warning(self, "Catalog error", result.error)
            return
        self._variables = list(result.variables)
        self._comparisons = list(result.comparisons)
        self._project_variables()
        self._populate_var_list()

    def _populate_var_list(self) -> None:
        self._var_list.clear()
        for v in self._variables:
            mag = v.max_mag or "—"
            text = f"{v.name}  [{v.var_type or '?'}]  {mag}"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, v)
            # Check if this star already has a role.
            if self._target_set is not None:
                existing = self._target_set.by_auid(v.auid)
                if existing:
                    item.setToolTip(f"Role: {existing.role}")
            self._var_list.addItem(item)

    def _project_variables(self) -> None:
        if self._wcs is None:
            return
        self._var_green = project_points(
            self._wcs, self._green_shape, ((v.ra_deg, v.dec_deg) for v in self._variables)
        )
        points = [
            (pos[0], pos[1], v.is_suspected)
            for pos, v in zip(self._var_green, self._variables)
            if pos is not None
        ]
        self._viewer.set_catalog_markers(points, self._green_shape)
        self._viewer.set_catalog_enabled(bool(points))

    def _on_var_clicked(self, item: QListWidgetItem) -> None:
        """A variable was clicked in the list — highlight it and show comps."""
        v = item.data(Qt.ItemDataRole.UserRole)
        if v is None:
            return
        # Highlight on the viewer
        pos = None
        for gp, var in zip(self._var_green, self._variables):
            if var is v and gp is not None:
                pos = gp
                break
        if pos is not None:
            dp = self._green_to_disp(pos[0], pos[1])
            if dp is not None:
                self._viewer.mark_selection(dp[0], dp[1], v.name)
                self._pending_variable = v
                self._pending_green = pos

    # ══════════════════════════════════════════════════════════
    # Target assignment
    # ══════════════════════════════════════════════════════════

    def _assign_role(self, role: str) -> None:
        """Assign the clicked star or selected VSX variable to a role."""
        target_set = self._ensure_target_set()
        ra_deg, dec_deg, auid, name, mags = self._resolve_pending()
        if ra_deg is None:
            QMessageBox.information(self, "No star selected", "Click a star or variable first.")
            return
        star = TargetStar(
            role=role,
            ra_deg=ra_deg,
            dec_deg=dec_deg,
            auid=auid,
            name=name,
            source=self._resolve_source(auid),
            mags=mags,
        )
        target_set.set_role(star)
        self._save_target_set(target_set)
        self._refresh_target_list()
        self._project_targets()

    def _resolve_pending(self) -> tuple:
        """Return ``(ra_deg, dec_deg, auid, name, mags)`` for the pending star."""
        # First check if a VSX variable was clicked in the list.
        v = getattr(self, "_pending_variable", None)
        if v is not None:
            return (v.ra_deg, v.dec_deg, v.auid, v.name, {})
        # Otherwise, use the measured star if we have a WCS.
        if self._selected_green is not None and self._wcs is not None:
            ra_h, dec_d = self._wcs.pixel_to_radec(self._selected_green[0], self._selected_green[1])
            return (ra_h * 15.0, dec_d, None, None, {})
        return (None, None, None, None, {})

    @staticmethod
    def _resolve_source(auid):
        return "vsx" if auid else "manual"

    def _refresh_target_list(self) -> None:
        self._target_list.clear()
        tset = self._target_set
        if tset is None:
            return
        for s in tset.stars:
            emoji = {"target": "★", "comparison": "C", "check": "✓"}.get(s.role, "·")
            mags = ""
            if s.mags:
                mags = "  " + "  ".join(f"{b}={m:.2f}" for b, m in s.mags.items())
            name = s.display_name or s.auid or "Unnamed"
            label = f"{emoji} [{s.role}]  {name}{mags}"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, s)
            self._target_list.addItem(item)

    def _on_remove_target(self) -> None:
        item = self._target_list.currentItem()
        if item is None:
            return
        star = item.data(Qt.ItemDataRole.UserRole)
        if star is None or self._target_set is None:
            return
        self._target_set.remove(star.auid or star.name)
        self._save_target_set(self._target_set)
        self._refresh_target_list()
        self._project_targets()

    def _project_targets(self) -> None:
        if self._wcs is None or self._target_set is None:
            self._viewer.set_target_markers((), self._green_shape)
            return
        tset = self._target_set
        pts = []
        for s in tset.stars:
            gp = project_points(self._wcs, self._green_shape, [(s.ra_deg, s.dec_deg)])
            if gp and gp[0] is not None:
                pts.append((gp[0][0], gp[0][1], s.display_name))
        self._viewer.set_target_markers(pts, self._green_shape)

    # ══════════════════════════════════════════════════════════
    # Target set persistence
    # ══════════════════════════════════════════════════════════

    def _sessions_base(self) -> Path:
        try:
            return self._config.sessions_path.parent
        except Exception:
            return Path.home() / "SeerControl"

    def _target_path(self) -> Path:
        safe = "".join(
            c if c.isalnum() or c in "-_" else "_" for c in (self._object_name or "untitled")
        )
        return self._sessions_base() / "targets" / f"{safe or 'untitled'}.json"

    def _ensure_target_set(self) -> TargetSet:
        obj = self._object_name or "untitled"
        if self._target_set is None or self._target_set.object_name != obj:
            self._target_set = TargetSet.load(self._target_path())
            self._target_set.object_name = obj
        return self._target_set

    def _load_target_set(self) -> TargetSet | None:
        path = self._target_path()
        if path.exists():
            ts = TargetSet.load(path)
            if ts.object_name != self._object_name:
                ts.object_name = self._object_name
            return ts
        return None

    def _save_target_set(self, tset: TargetSet | None = None) -> None:
        ts = tset or self._target_set
        if ts is None:
            return
        try:
            ts.save(self._target_path())
        except OSError as exc:
            QMessageBox.warning(self, "Save error", str(exc))

    def _on_save(self) -> None:
        self._save_target_set()
        QMessageBox.information(self, "Saved", f"Saved to {self._target_path()}")

    def _on_load(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Load targets", str(self._target_path()), "JSON (*.json);;All files (*)"
        )
        if path:
            try:
                ts = TargetSet.load(Path(path))
                self._target_set = ts
                self._object_name = ts.object_name or self._object_name
                self.setWindowTitle(f"Photometry Setup — {self._object_name}")
                self._refresh_target_list()
                self._project_targets()
            except Exception as exc:
                QMessageBox.warning(self, "Load error", str(exc))

    # ══════════════════════════════════════════════════════════
    # Run photometry
    # ══════════════════════════════════════════════════════════

    def _on_run(self) -> None:
        """Run differential photometry on all frames in the sequence directory."""
        if self._wcs is None:
            QMessageBox.information(self, "Need a solve", "Plate-solve the reference frame first.")
            return
        tset = self._ensure_target_set()
        if not tset.by_role(ROLE_TARGET):
            QMessageBox.information(self, "No targets", "Add at least one target star first.")
            return
        seq_dir = self._sequence_dir
        if seq_dir is None or not seq_dir.exists():
            seq_dir = Path(self._frame_label.text()).parent
        fits_files = sorted(seq_dir.glob("*.fits"), key=lambda p: p.stat().st_mtime)
        if not fits_files:
            QMessageBox.information(self, "No frames", f"No FITS files in {seq_dir}")
            return
        # We'll measure all frames and open the light curve window.
        from seercontrol.core.imaging.green import green_plane
        from seercontrol.core.photometry.session import measure_targets
        from seercontrol.core.photometry.lightcurve import LightCurve, LcPoint
        from seercontrol.core.photometry.airmass import bjd_tdb, julian_date
        from seercontrol.ui.panels.photometry_window import PhotometryWindow

        aperture = float(self._aperture_spin.value())
        ann_in = float(self._annulus_in.value())
        ann_out = float(self._annulus_out.value())
        band = self._band_combo.currentText()

        lightcurves: dict[str, LightCurve] = {}
        # Get egain setting
        egain = self._cfg("camera.egain_table", None) or {}
        egain_val = float(egain.get("100", 1.0)) if isinstance(egain, dict) else 1.0
        read_noise = float(self._cfg("photometry.read_noise_e", 1.5))
        sat_adu = float(self._cfg("camera.linearity_max_adu", 50000))
        lat = self._cfg("site.latitude", None)
        lon = self._cfg("site.longitude", None)
        elev = self._cfg("site.elevation", 0.0) or 0.0

        from astropy.io import fits

        completed = 0
        for fpath in fits_files:
            try:
                with fits.open(fpath) as hdul:
                    arr = hdul[0].data
                jd = None
                try:
                    date_str = hdul[0].header.get("DATE-OBS", "")
                    if date_str:
                        from datetime import datetime

                        dt = datetime.fromisoformat(str(date_str).replace("Z", "+00:00"))
                        jd = julian_date(dt)
                except Exception:
                    pass
            except Exception:
                continue
            green = green_plane(np.nan_to_num(np.asarray(arr, dtype=np.float32)))
            results = measure_targets(
                green,
                self._wcs,
                tset,
                r_ap=aperture,
                r_in=max(ann_in, aperture + 1),
                r_out=max(ann_out, ann_in + 2),
                egain=egain_val,
                read_noise_e=read_noise,
                sat_adu=sat_adu,
                band=band,
                min_comps=int(self._cfg("photometry.min_comparisons", 2)),
            )
            for res in results:
                if res.diff is None or res.diff.mag is None:
                    continue
                bjd = (
                    bjd_tdb(
                        jd, res.star.ra_deg, res.star.dec_deg, float(lat), float(lon), float(elev)
                    )
                    if jd is not None and lat is not None and lon is not None
                    else None
                )
                point = LcPoint(
                    jd_utc=jd or 0.0,
                    mag=res.diff.mag,
                    mag_err=res.diff.mag_err or 0.0,
                    bjd_tdb=bjd,
                    airmass=None,
                    fwhm=None,
                    sky_adu=res.phot.sky_adu if res.phot else None,
                    comps_used=res.diff.comps_used,
                    saturated=bool(res.phot and res.phot.saturated),
                )
                key = res.star.auid or res.star.display_name
                lc = lightcurves.setdefault(
                    key, LightCurve(auid=res.star.auid or "", name=res.star.display_name)
                )
                lc.append(point)
            completed += 1

        if not lightcurves:
            QMessageBox.information(self, "No results", "No photometry could be measured.")
            return

        # Open the light curve window and feed it.
        win = PhotometryWindow()
        win.lightcurves = lightcurves
        win.obscode = str(self._cfg("observer.obscode", "XXX") or "XXX")
        # Feed points to the light curve panel.
        for key, lc in lightcurves.items():
            for pt in lc.points:
                win.lightcurve.add_point(
                    lc.name,
                    pt.jd_utc,
                    pt.mag,
                    pt.mag_err,
                    saturated=pt.saturated,
                )
        win.show()
        win.raise_()
        QMessageBox.information(
            self,
            "Photometry done",
            f"Processed {completed} frame(s), {len(lightcurves)} target(s).",
        )

    # ══════════════════════════════════════════════════════════
    # Click-to-measure on the viewer
    # ══════════════════════════════════════════════════════════

    def _on_star_clicked(self, x_disp: float, y_disp: float) -> None:
        gp = self._disp_to_green(x_disp, y_disp)
        if gp is None or self._raw is None:
            return
        # Check if a VSX variable is at this position first.
        vi = self._nearest_variable(gp[0], gp[1])
        if vi is not None:
            v = self._variables[vi]
            self._pending_variable = v
            self._pending_green = self._var_green[vi]
            dp = self._green_to_disp(self._var_green[vi][0], self._var_green[vi][1])
            if dp is not None:
                self._viewer.mark_selection(dp[0], dp[1], v.name)
            return
        self._pending_variable = None
        meas = measure_star_at(self._raw, gp[0], gp[1], self._radius)
        if meas is None:
            self._viewer.clear_selection()
            self._selected_green = None
            return
        self._selected_green = (meas.x, meas.y)
        self._show_selection(meas)

    def _remeasure_selection(self) -> None:
        if self._selected_green is None or self._raw is None:
            return
        meas = measure_star_at(
            self._raw,
            self._selected_green[0],
            self._selected_green[1],
            self._radius,
            search=TRACK_SNAP_SEARCH,
        )
        if meas is not None:
            self._selected_green = (meas.x, meas.y)
            self._show_selection(meas)

    def _show_selection(self, meas) -> None:
        dp = self._green_to_disp(meas.x, meas.y)
        if dp is None:
            return
        radius_disp = self._green_len_to_disp(meas.radius)
        text_parts = [f"SNR {meas.snr:.0f}"]
        if meas.fwhm is not None:
            text_parts.append(f"FWHM {meas.fwhm * ARCSEC_PER_GREEN_PX:.1f}″")
        text = "   ".join(text_parts)
        self._viewer.mark_selection(dp[0], dp[1], text, radius_disp)

    def _nearest_variable(self, gx: float, gy: float) -> int | None:
        if not self._var_green:
            return None
        tol = 10.0
        if self._green_shape and self._disp_shape:
            _gh, gw = self._green_shape
            _dh, dw = self._disp_shape
            if dw > 0:
                tol = max(6.0, 14.0 * gw / dw)
        best_i, best_d = None, tol
        for i, pos in enumerate(self._var_green):
            if pos is None:
                continue
            d = ((pos[0] - gx) ** 2 + (pos[1] - gy) ** 2) ** 0.5
            if d <= best_d:
                best_i, best_d = i, d
        return best_i

    # ══════════════════════════════════════════════════════════
    # Coordinate helpers
    # ══════════════════════════════════════════════════════════

    def _disp_to_green(self, x: float, y: float) -> tuple[float, float] | None:
        if self._green_shape is None or self._disp_shape is None:
            return None
        gh, gw = self._green_shape
        dh, dw = self._disp_shape
        if dw <= 0 or dh <= 0:
            return None
        return x * gw / dw, y * gh / dh

    def _green_to_disp(self, x: float, y: float) -> tuple[float, float] | None:
        if self._green_shape is None or self._disp_shape is None:
            return None
        gh, gw = self._green_shape
        dh, dw = self._disp_shape
        if gw <= 0 or gh <= 0:
            return None
        return x * dw / gw, y * dh / gh

    def _green_len_to_disp(self, length: float) -> float | None:
        if self._green_shape is None or self._disp_shape is None:
            return None
        gw = self._green_shape[1]
        dw = self._disp_shape[1]
        return length * dw / gw if gw > 0 else None

    def closeEvent(self, event) -> None:
        if self._solver is not None and self._solver.isRunning():
            self._solver.wait(2000)
        if self._catalog_worker is not None and self._catalog_worker.isRunning():
            self._catalog_worker.wait(2000)
        super().closeEvent(event)
