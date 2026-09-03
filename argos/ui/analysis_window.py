"""Analysis window — standalone viewer for inspecting a single FITS frame.

Opened via the "Open FITS" button or from a Review curve point.  It uses the
same solved-field identification layers as Observe (Gaia, VSX, VSP, SIMBAD,
NASA and the bundled deep-sky catalogue), while remaining read-only: target
management and photometry setup still belong to the Observe workspace.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from argos.core.imaging.debayer import VIEW_G, VIEW_RAW, extract_plane
from argos.core.catalog import separation_arcmin
from argos.core.catalog.exoplanets import cached_exoplanet_hosts_in_cone
from argos.core.catalog.offline import essential_catalogue_objects
from argos.core.catalog.targets import ROLE_TARGET, TargetSet
from argos.core.imaging.metrics import (
    arcsec_per_full_px,
    arcsec_per_green_px,
    DEFAULT_STAR_RADIUS,
    TRACK_SNAP_SEARCH,
    measure_star_at,
)
from argos.core.imaging.astrometry_session import field_geometry, project_points
from argos.core.imaging.platesolve import format_dec_dms, format_ra_hms
from argos.ui import theme
from argos.ui.widgets.astrometry_settings import AstrometrySettingsDialog, SECTION_CATALOG
from argos.ui.widgets.fits_viewer import FitsViewer
from argos.ui.widgets.histogram_dock import HistogramDock
from argos.ui.widgets.image_toolbar import ImageToolbar
from argos.ui.widgets.overlay_bar import OverlayBar
from argos.workers.catalog_worker import CatalogRequest, CatalogWorker
from argos.workers.preview_processor import build_processed_frame
from argos.workers.solve_worker import SolveWorker

logger = logging.getLogger(__name__)


def read_fits_2d(path: str) -> np.ndarray | None:
    """Read a FITS file into a 2-D float32 array (NaNs zeroed, cubes collapsed)."""
    from astropy.io import fits

    with fits.open(path) as hdul:
        data = next((h.data for h in hdul if getattr(h, "data", None) is not None), None)
    if data is None:
        return None
    arr = np.nan_to_num(np.asarray(data, dtype=np.float32), nan=0.0)
    if arr.ndim == 3:
        arr = arr.mean(axis=0) if arr.shape[0] <= 4 else arr.mean(axis=2)
    return arr if arr.ndim == 2 else None


def read_fits_meta(path: str) -> dict:
    """Return a dict of useful header keywords from a FITS file."""
    from astropy.io import fits

    keys = (
        "OBJECT",
        "DATE-OBS",
        "EXPTIME",
        "EXPOSURE",
        "IMAGETYP",
        "FILTER",
        "GAIN",
        "INSTRUME",
        "OBSERVER",
        "SITENAME",
        "CRPIX1",
        "CRPIX2",
        "CRVAL1",
        "CRVAL2",
        "CD1_1",
        "CD2_2",
        "CCD-TEMP",
        "HFD",
        "FWHM",
        "NSTARS",
        "SKYLEVEL",
        "PEAKADU",
        "ECCENT",
        "EGAIN",
        "RDNOISE",
        "AIRMASS",
        "MOONSEP",
        "FRAME",
        "FRAMENO",
        "IMGNUM",
        "NFRAMES",
        "SEQUENCE",
    )
    meta = {}
    try:
        with fits.open(path) as hdul:
            for h in hdul:
                if getattr(h, "header", None) is None:
                    continue
                hdr = h.header
                for k in keys:
                    if k in hdr:
                        meta[k] = str(hdr[k]).strip()
                # Also grab ORIGIN / COMMENT / HISTORY as a single text block.
                for k in ("ORIGIN",):
                    if k in hdr:
                        meta[k] = str(hdr[k]).strip()
                break  # primary header only
    except Exception:
        pass
    return meta


def read_fits_header_text(path: str) -> str:
    """Return the complete primary FITS header for the read-only inspector."""
    try:
        from astropy.io import fits

        return str(fits.getheader(path, 0))
    except Exception:
        return "FITS header unavailable"


class AnalysisWindow(QMainWindow):
    """Floating window to inspect one loaded FITS frame.

    Read-only frame inspection with the same catalogue provenance and marker
    vocabulary as the live Observe image.
    """

    def __init__(self, config=None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._config = config
        self.setWindowTitle("Frame Viewer")
        self.setMinimumSize(900, 640)
        self.setWindowFlag(Qt.WindowType.Window, True)

        self._raw: np.ndarray | None = None
        self._channel = VIEW_RAW
        self._radius = DEFAULT_STAR_RADIUS
        self._green_shape: tuple[int, int] | None = None
        self._disp_shape: tuple[int, int] | None = None
        self._selected_green: tuple[float, float] | None = None
        self._solver: SolveWorker | None = None
        self._wcs = None  # platesolve.FrameWCS once solved
        self._meta: dict = {}  # header keywords
        self._header_text = ""
        self._path: Path | None = None
        self._selected_measurement = None
        self._selected_catalogue: tuple[str, str] | None = None
        self._target_set = TargetSet()
        self._catalog_result = None
        self._catalog_workers: set[CatalogWorker] = set()
        self._catalog_sources: list[tuple[str, tuple[float, float], str, str]] = []
        self._display_mag_limit = float(self._cfg("catalog.display_mag_limit", 18.0))
        self._armed: set[str] = set()
        self._load_generation = 0
        self._catalog_request_serial = 0

        self._build_ui()
        self._wire()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._toolbar = ImageToolbar()
        root.addWidget(self._toolbar)
        self._overlay_bar = OverlayBar()
        self._overlay_bar.set_magnitude_range(
            float(self._cfg("catalog.field_stars_mag_limit", 18.0))
        )
        self._overlay_bar.set_magnitude_limit(self._display_mag_limit)
        root.addWidget(self._overlay_bar)

        self._viewer = FitsViewer()
        self._histogram = HistogramDock(show_roi=False)
        self._histogram.setMinimumWidth(320)
        self._histogram.setMaximumWidth(420)

        # The review panel presents observation context and the clicked star;
        # whole-frame pixel statistics are not a useful decision aid here.
        self._info_panel = QWidget()
        self._info_panel.setMinimumWidth(320)
        self._info_panel.setMaximumWidth(420)
        info_layout = QVBoxLayout(self._info_panel)
        info_layout.setContentsMargins(8, 8, 8, 8)
        self._info_label = QLabel("No frame loaded")
        self._info_label.setWordWrap(True)
        self._info_label.setStyleSheet(
            f"color:{theme.FG_MUTED}; font-size:11px; font-family:{theme.FONT_MONO};"
            f" background:transparent;"
        )
        info_layout.addWidget(self._info_label)
        info_layout.addStretch()

        self._header_panel = QPlainTextEdit()
        self._header_panel.setReadOnly(True)
        self._header_panel.setPlaceholderText("No FITS header loaded")
        self._header_panel.setStyleSheet(
            f"color:{theme.FG_MUTED}; font-family:{theme.FONT_MONO}; font-size:11px;"
        )

        # Details stay available but do not compete with the image by default.
        self._right_tabs = QWidget()
        tab_layout = QVBoxLayout(self._right_tabs)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.setSpacing(0)
        from PyQt6.QtWidgets import QTabWidget

        self._tab_widget = QTabWidget()
        self._tab_widget.addTab(self._info_panel, "Frame · selected star")
        self._tab_widget.addTab(self._header_panel, "FITS header")
        self._tab_widget.addTab(self._histogram, "Adjust image")
        tab_layout.addWidget(self._tab_widget)

        split = QSplitter(Qt.Orientation.Horizontal)
        split.setChildrenCollapsible(False)
        split.addWidget(self._viewer)
        split.addWidget(self._right_tabs)
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 0)
        split.setSizes([900, 360])
        root.addWidget(split, 1)

        # Bottom bar: plate-solve + WCS grid + solve status.
        bar = QWidget()
        bar.setStyleSheet(f"background:{theme.SURFACE_3}; border-top:1px solid {theme.SURFACE_4};")
        brow = QHBoxLayout(bar)
        brow.setContentsMargins(10, 4, 10, 4)
        brow.setSpacing(10)

        self._solve_btn = QPushButton("Identify field")
        self._solve_btn.setToolTip("Determine sky coordinates and image scale with ASTAP")
        self._solve_btn.clicked.connect(self._on_solve)
        brow.addWidget(self._solve_btn)

        # Backwards-compatible handle used by tests and external integrations;
        # the visible control is the shared Coordinate grid overlay chip above.
        self._grid_btn = self._overlay_bar.control("grid")

        self._display_btn = QPushButton("Adjust image")
        self._display_btn.setCheckable(True)
        self._display_btn.setToolTip("Open the histogram, contrast and display tools")
        self._display_btn.toggled.connect(self._show_display_tools)
        brow.addWidget(self._display_btn)

        self._solve_lbl = QLabel("field not identified")
        self._solve_lbl.setStyleSheet(
            f"color:{theme.FG_MUTED}; font-family:{theme.FONT_MONO};"
            f" font-size:11px; background:transparent;"
        )
        brow.addWidget(self._solve_lbl, 1)
        root.addWidget(bar)

        self.setCentralWidget(central)

    def _show_display_tools(self, visible: bool) -> None:
        self._tab_widget.setCurrentIndex(2 if visible else 0)

    def _wire(self) -> None:
        self._toolbar.channel_changed.connect(self._on_channel)
        self._toolbar.palette_changed.connect(self._viewer.set_palette)
        self._toolbar.open_requested.connect(self._on_open)
        self._overlay_bar.toggled.connect(self._on_overlay_toggled)
        self._overlay_bar.configure_requested.connect(self._open_field_catalogue)
        self._overlay_bar.magnitude_changed.connect(self._on_catalogue_magnitude_changed)
        self._overlay_bar.magnitude_committed.connect(self._save_catalogue_magnitude)
        self._histogram.stretch_changed.connect(self._viewer.set_stretch)
        self._histogram.auto_requested.connect(self._viewer.auto_stretch)
        self._histogram.saturation_toggled.connect(self._on_saturation)
        self._histogram.crosshair_toggled.connect(self._viewer.set_crosshair_enabled)
        self._histogram.loupe_toggled.connect(self._viewer.set_loupe_enabled)
        self._histogram._astro_chk.hide()  # WCS grid is driven by our own Grid button
        self._histogram.star_radius_changed.connect(self._on_radius)
        self._histogram.rotation_changed.connect(self._viewer.set_rotation)
        # Same display rotation as the Capture screen (Auto → landscape).
        rotation = str(self._cfg("ui.display.rotation", "auto") or "auto")
        self._viewer.set_rotation(rotation)
        self._histogram.set_rotation_mode(rotation)
        self._viewer.levels_changed.connect(self._histogram.set_levels)
        self._viewer.star_clicked.connect(self._on_star_clicked)

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def load(self, path: str) -> bool:
        """Load a FITS file into the window. Returns False on failure."""
        try:
            arr = read_fits_2d(path)
        except Exception as exc:
            logger.warning("Open FITS failed: %s", exc)
            return False
        if arr is None:
            return False
        self._load_generation += 1
        self._raw = arr
        self._path = Path(path)
        self._target_set = self._load_session_targets(self._path)
        self._meta = read_fits_meta(path)
        self._header_text = read_fits_header_text(path)
        self._header_panel.setPlainText(self._header_text)
        self._selected_green = None
        self._selected_measurement = None
        self._selected_catalogue = None
        self._viewer.clear_selection()
        self._wcs = None
        self._viewer.set_astrometry_overlay(None)
        self._catalog_result = None
        self._catalog_sources = []
        self._armed.clear()
        self._clear_field_overlays()
        self._set_solve_text("field not identified", theme.FG_MUTED)
        self._channel = VIEW_RAW
        self._toolbar.set_view(VIEW_RAW)
        name = self._path.name
        h, w = arr.shape
        self.setWindowTitle(f"Frame Viewer — {name}  ({w}×{h})")
        self._update_info()
        self._reprocess()
        return True

    @staticmethod
    def _load_session_targets(path: Path) -> TargetSet:
        """Find the nearest Review session target set without changing it."""
        for folder in (path.parent, *path.parents):
            if (folder / "session.json").is_file():
                return TargetSet.load(folder / "targets.json")
        return TargetSet()

    def _update_info(self) -> None:
        """Refresh the useful observing context and the selected-star readout."""
        if self._raw is None:
            self._info_label.setText("No frame loaded")
            return
        lines = ["FRAME"]
        if self._path is not None:
            lines.append(f"File: {self._path.name}")
        lines.append(f"Dimensions: {self._raw.shape[1]} × {self._raw.shape[0]} px")
        labels = (
            ("OBJECT", "Object"),
            ("DATE-OBS", "Start (UTC)"),
            ("EXPTIME", "Exposure"),
            ("EXPOSURE", "Exposure"),
            ("FILTER", "Filter"),
            ("IMAGETYP", "Image type"),
            ("GAIN", "Gain"),
            ("CCD-TEMP", "Sensor"),
            ("INSTRUME", "Instrument"),
            ("NFRAMES", "Frames in sequence"),
            ("FRAME", "Frame number"),
            ("FRAMENO", "Frame number"),
            ("IMGNUM", "Frame number"),
            ("SEQUENCE", "Sequence"),
            ("AIRMASS", "Airmass"),
        )
        emitted: set[str] = set()
        for key, label in labels:
            value = self._meta.get(key)
            if value and label not in emitted:
                suffix = " s" if key in {"EXPTIME", "EXPOSURE"} else ""
                lines.append(f"{label}: {value}{suffix}")
                emitted.add(label)
        if self._selected_catalogue is not None:
            title, body = self._selected_catalogue
            lines.extend(("", "CATALOGUE SOURCE", title, body))
            if self._selected_measurement is not None:
                meas = self._selected_measurement
                lines.extend(("", "IMAGE MEASUREMENT"))
                if meas.fwhm is not None:
                    lines.append(
                        f"FWHM: {meas.fwhm:.2f} px " f"({meas.fwhm * arcsec_per_green_px():.1f}″)"
                    )
                if meas.hfd is not None:
                    lines.append(
                        f"HFD: {meas.hfd:.2f} px ({meas.hfd * arcsec_per_green_px():.1f}″)"
                    )
                lines.extend((f"SNR: {meas.snr:.0f}", f"Peak: {meas.peak_adu} ADU"))
        elif self._selected_measurement is None:
            lines.extend(("", "SELECTED STAR", "Click a star in the image to measure it."))
        else:
            meas = self._selected_measurement
            lines.extend(("", "SELECTED STAR", f"Position: {meas.x:.1f}, {meas.y:.1f} px"))
            if meas.fwhm is not None:
                lines.append(f"FWHM: {meas.fwhm:.2f} px ({meas.fwhm * arcsec_per_green_px():.1f}″)")
            if meas.hfd is not None:
                lines.append(f"HFD: {meas.hfd:.2f} px ({meas.hfd * arcsec_per_green_px():.1f}″)")
            if meas.eccentricity is not None:
                lines.append(f"Eccentricity: {meas.eccentricity:.2f}")
            lines.extend(
                (
                    f"SNR: {meas.snr:.0f}",
                    f"Peak: {meas.peak_adu} ADU",
                    f"Sky: {meas.sky_adu:.0f} ADU",
                )
            )
        self._info_label.setText("\n".join(lines))

    def _reprocess(self) -> None:
        if self._raw is None:
            return
        pf = build_processed_frame(self._raw, self._channel, self._radius)
        self._green_shape = pf.green_shape
        self._disp_shape = pf.display.shape[:2]
        self._histogram.set_histogram(pf.centers, pf.r, pf.g, pf.b, pf.lo, pf.hi)
        self._viewer.set_frame_geometry(pf.green_shape)
        self._viewer.display(pf.display)
        self._remeasure_selection()

    def _on_channel(self, channel: str) -> None:
        self._channel = channel
        self._reprocess()

    def _on_radius(self, radius: int) -> None:
        self._radius = max(2, int(radius))
        self._reprocess()

    def _on_open(self) -> None:
        from PyQt6.QtWidgets import QFileDialog

        start = str(self._cfg("sessions_path", Path.home()))
        path, _ = QFileDialog.getOpenFileName(
            self, "Open FITS", start, "FITS (*.fits *.fit *.fts);;All files (*)"
        )
        if path:
            self.load(path)

    # ------------------------------------------------------------------
    # Plate solving (optional, for info)
    # ------------------------------------------------------------------

    def _cfg(self, key: str, default):
        if self._config is None:
            return default
        value = self._config.get(key, default)
        return default if value is None else value

    def _on_saturation(self, enabled: bool) -> None:
        threshold = int(self._cfg("camera.full_well_adu", 60000))
        self._viewer.set_saturation(enabled, threshold)

    def _on_solve(self) -> None:
        if self._raw is None or (self._solver is not None and self._solver.isRunning()):
            return
        green = extract_plane(self._raw, VIEW_G)
        from argos.core.imaging.astrometry_session import build_solve_settings

        settings = build_solve_settings(self._cfg, self._green_shape, live=False)
        self._solve_btn.setEnabled(False)
        self._set_solve_text("identifying field… (ASTAP)", theme.WARNING)
        generation = self._load_generation
        self._solver = SolveWorker(green, settings, parent=self)
        self._solver.solved.connect(lambda result, g=generation: self._on_solved(result, g))
        self._solver.start()

    def _on_solved(self, result, generation: int | None = None) -> None:
        if generation is not None and generation != self._load_generation:
            return
        self._solve_btn.setEnabled(True)
        if not result.solved:
            self._set_solve_text(f"field not identified — {result.message}", theme.DANGER)
            return
        from argos.core.imaging.astrometry_session import (
            full_res_scale,
            overlay_for,
            wcs_from_result,
        )

        bits = [f"RA {result.ra_hours:.4f}h", f"Dec {result.dec_deg:+.4f}°"]
        scale = full_res_scale(result)
        if scale is not None:
            bits.append(f"{scale:.2f}″/px")
        if result.rotation_deg is not None:
            bits.append(f"rot {result.rotation_deg:.1f}°")
        self._set_solve_text("Field identified — " + "   ".join(bits), theme.SUCCESS)

        self._wcs = wcs_from_result(result, self._green_shape)
        if self._wcs is not None:
            overlay = overlay_for(self._wcs, self._green_shape, self._cfg)
            self._viewer.set_astrometry_overlay(overlay, self._green_shape)
            self._arm_overlay("grid", True, self._viewer.set_astrometry_enabled)
            self._remeasure_selection()
            self._fetch_field_catalogues()

    # ------------------------------------------------------------------
    # Solved-field catalogues — same sources and viewer layers as Observe
    # ------------------------------------------------------------------

    def _on_overlay_toggled(self, name: str, enabled: bool) -> None:
        setters = {
            "grid": self._viewer.set_astrometry_enabled,
            "catalogue": self._viewer.set_field_catalogue_enabled,
            "variables": self._viewer.set_catalog_enabled,
            "galaxies": lambda on: self._viewer.set_context_enabled("galaxies", on),
            "nebulae_clusters": lambda on: self._viewer.set_context_enabled("nebulae_clusters", on),
            "exoplanets": lambda on: self._viewer.set_context_enabled("exoplanets", on),
            "other_objects": lambda on: self._viewer.set_context_enabled("other_objects", on),
            "comparisons": self._viewer.set_comparison_enabled,
            "targets": self._viewer.set_target_enabled,
            "labels": self._viewer.set_marker_labels_enabled,
        }
        setters[name](enabled)

    def _arm_overlay(self, name: str, available: bool, setter) -> None:
        self._overlay_bar.set_available(name, available)
        if available and name not in self._armed:
            self._armed.add(name)
            checked = name != "labels"
            self._overlay_bar.set_checked(name, checked)
            setter(checked)

    def _clear_field_overlays(self) -> None:
        self._viewer.set_catalog_markers((), self._green_shape)
        self._viewer.set_field_catalogue_markers((), self._green_shape)
        self._viewer.set_comparison_markers((), self._green_shape)
        self._viewer.set_target_markers((), self._green_shape)
        for layer in ("galaxies", "nebulae_clusters", "exoplanets", "other_objects"):
            self._viewer.set_context_markers(layer, (), self._green_shape)
        for name in (
            "grid",
            "catalogue",
            "variables",
            "galaxies",
            "nebulae_clusters",
            "exoplanets",
            "other_objects",
            "comparisons",
            "targets",
            "labels",
        ):
            self._overlay_bar.set_checked(name, False)
            self._overlay_bar.set_available(name, False)
        for name in (
            "catalogue",
            "variables",
            "galaxies",
            "nebulae_clusters",
            "exoplanets",
            "other_objects",
            "comparisons",
            "targets",
        ):
            self._overlay_bar.set_count(name, 0)

    def _open_field_catalogue(self) -> None:
        if self._config is None:
            return
        dialog = AstrometrySettingsDialog(self._config, self, section=SECTION_CATALOG)
        dialog.saved.connect(self._refresh_catalogue_settings)
        dialog.exec()

    def _refresh_catalogue_settings(self) -> None:
        maximum = float(self._cfg("catalog.field_stars_mag_limit", 18.0))
        self._overlay_bar.set_magnitude_range(maximum)
        self._display_mag_limit = min(self._display_mag_limit, maximum)
        self._overlay_bar.set_magnitude_limit(self._display_mag_limit)
        if self._wcs is not None:
            self._fetch_field_catalogues()

    def _on_catalogue_magnitude_changed(self, value: float) -> None:
        self._display_mag_limit = float(value)
        self._project_field_catalogues()

    def _save_catalogue_magnitude(self, value: float) -> None:
        if self._config is not None:
            self._config.set("catalog.display_mag_limit", float(value))
            self._config.save()

    def _fetch_field_catalogues(self) -> None:
        geometry = field_geometry(self._wcs, self._green_shape)
        if geometry is None:
            return
        ra_deg, dec_deg, radius_deg, fov_arcmin = geometry
        identity_budget = max(
            50, min(5000, int(self._cfg("catalog.identification_max_objects", 400)))
        )
        want_stars = bool(self._cfg("catalog.field_stars_enabled", True))
        want_names = bool(self._cfg("catalog.named_objects_enabled", True))
        if want_stars and want_names:
            star_budget = max(25, round(identity_budget * 0.7))
            name_budget = max(25, identity_budget - star_budget)
        else:
            star_budget = name_budget = identity_budget
        target = next(iter(self._target_set.by_role(ROLE_TARGET)), None)
        request = CatalogRequest(
            ra_deg=ra_deg,
            dec_deg=dec_deg,
            radius_deg=radius_deg,
            fov_arcmin=fov_arcmin,
            mag_limit=float(self._cfg("catalog.mag_limit", 15.0)),
            max_results=int(self._cfg("catalog.max_results", 250)),
            include_suspected=bool(self._cfg("catalog.include_suspected", True)),
            comparison_target_name=(
                target.display_name if target is not None else self._meta.get("OBJECT")
            ),
            comparison_ra_deg=target.ra_deg if target is not None else None,
            comparison_dec_deg=target.dec_deg if target is not None else None,
            want_field_stars=want_stars,
            field_star_mag_limit=float(self._cfg("catalog.field_stars_mag_limit", 18.0)),
            field_star_max_results=star_budget,
            want_named_objects=want_names,
            named_object_max_results=name_budget,
            named_objects_allow_network=bool(
                self._cfg("catalog.named_objects_allow_network", True)
            ),
            want_exoplanet_hosts=bool(self._cfg("catalog.exoplanet_hosts_enabled", True)),
            exoplanet_hosts_allow_network=bool(
                self._cfg("catalog.exoplanet_hosts_allow_network", True)
            ),
        )
        self._set_solve_text("Field solved · identifying catalogue sources…", theme.WARNING)
        generation = self._load_generation
        self._catalog_request_serial += 1
        request_serial = self._catalog_request_serial
        worker = CatalogWorker(request, parent=self)
        self._catalog_workers.add(worker)
        worker.fetched.connect(
            lambda result, g=generation, s=request_serial: self._on_catalogues_fetched(result, g, s)
        )
        worker.finished.connect(lambda w=worker: self._finish_catalogue_worker(w))
        worker.start()

    def _finish_catalogue_worker(self, worker: CatalogWorker) -> None:
        self._catalog_workers.discard(worker)
        worker.deleteLater()

    def _on_catalogues_fetched(
        self, result, generation: int, request_serial: int | None = None
    ) -> None:
        if generation != self._load_generation or (
            request_serial is not None and request_serial != self._catalog_request_serial
        ):
            return
        if not result.ok:
            self._set_solve_text(
                f"Field solved · catalogues unavailable: {result.error}", theme.WARNING
            )
            return
        self._catalog_result = result
        self._project_field_catalogues()
        counts = (
            len(result.field_stars)
            + len(result.variables)
            + len(result.named_objects)
            + len(result.exoplanet_hosts)
        )
        self._set_solve_text(f"Field identified · {counts} catalogue sources", theme.SUCCESS)

    def _project_field_catalogues(self) -> None:
        """Project the fetched catalogues through this frame's solved WCS."""
        result = self._catalog_result
        geometry = field_geometry(self._wcs, self._green_shape)
        if result is None or geometry is None:
            return
        _ra_deg, _dec_deg, radius_deg, _fov_arcmin = geometry
        gs = self._green_shape
        self._catalog_sources = []

        variable_positions = project_points(
            self._wcs, gs, ((item.ra_deg, item.dec_deg) for item in result.variables)
        )
        variable_points = []
        for position, item in zip(variable_positions, result.variables):
            if position is None:
                continue
            body = self._variable_tooltip(item)
            variable_points.append((position[0], position[1], item.is_suspected, item.name, body))
            self._add_catalogue_source("variables", position, f"Variable star · {item.name}", body)
        self._viewer.set_catalog_markers(variable_points, gs)

        # Enrich Gaia with a conventional SIMBAD identity when both catalogues
        # describe the same physical source (3 arcsec cross-match).
        matched_named: set[int] = set()
        gaia_identities = []
        for star in result.field_stars:
            candidates = [
                (
                    separation_arcmin(star.ra_deg, star.dec_deg, item.ra_deg, item.dec_deg),
                    index,
                    item,
                )
                for index, item in enumerate(result.named_objects)
            ]
            match = min(candidates, default=None)
            if match is not None and match[0] <= 3.0 / 60.0:
                matched_named.add(match[1])
                gaia_identities.append(match[2])
            else:
                gaia_identities.append(None)

        gaia_positions = project_points(
            self._wcs, gs, ((item.ra_deg, item.dec_deg) for item in result.field_stars)
        )
        field_points = []
        for position, star, identity in zip(gaia_positions, result.field_stars, gaia_identities):
            if position is None or not self._magnitude_is_visible(star.g_mag):
                continue
            label = (
                identity.name
                if identity is not None and not self._is_generic_identifier(identity.name)
                else ""
            )
            body = self._gaia_tooltip(star, identity)
            field_points.append((position[0], position[1], label, body))
            title = (
                f"Identified star · {identity.name}" if identity else f"Gaia DR3 · {star.source_id}"
            )
            self._add_catalogue_source("catalogue", position, title, body)

        named_positions = project_points(
            self._wcs, gs, ((item.ra_deg, item.dec_deg) for item in result.named_objects)
        )
        context_points: dict[str, list] = {
            "galaxies": [],
            "nebulae_clusters": [],
            "other_objects": [],
        }
        for index, (position, item) in enumerate(zip(named_positions, result.named_objects)):
            if position is None or index in matched_named:
                continue
            body = self._named_tooltip(item)
            category = self._object_category(item.object_type)
            if category == "star":
                field_points.append((position[0], position[1], item.name, body))
                layer = "catalogue"
            elif category == "galaxy":
                layer = "galaxies"
                context_points[layer].append((position[0], position[1], item.name, body))
            elif category in {"nebula", "cluster"}:
                layer = "nebulae_clusters"
                context_points[layer].append((position[0], position[1], item.name, body))
            else:
                layer = "other_objects"
                context_points[layer].append((position[0], position[1], item.name, body))
            self._add_catalogue_source(layer, position, f"SIMBAD · {item.name}", body)

        # Bundled Messier/NGC/IC objects remain available offline.
        centre_ra, centre_dec, _radius, _fov = geometry
        essential = (
            [
                item
                for item in essential_catalogue_objects()
                if separation_arcmin(centre_ra, centre_dec, item.ra_degrees, item.dec_degrees)
                <= radius_deg * 60.0
            ]
            if bool(self._cfg("catalog.show_essential_objects", True))
            else []
        )
        essential_positions = project_points(
            self._wcs, gs, ((item.ra_degrees, item.dec_degrees) for item in essential)
        )
        for position, item in zip(essential_positions, essential):
            if position is None:
                continue
            body = self._deep_sky_tooltip(item)
            category = self._object_category(item.object_type)
            layer = "galaxies" if category == "galaxy" else "nebulae_clusters"
            context_points[layer].append((position[0], position[1], item.name, body))
            self._add_catalogue_source(layer, position, f"Deep sky · {item.name}", body)

        field_points = self._deduplicate_points(field_points)
        self._viewer.set_field_catalogue_markers(field_points, gs)
        for layer in context_points:
            points = self._deduplicate_points(context_points[layer])
            context_points[layer] = points
            self._viewer.set_context_markers(layer, points, gs)

        hosts = list(result.exoplanet_hosts)
        if not hosts and bool(self._cfg("catalog.show_cached_exoplanets", True)):
            hosts = cached_exoplanet_hosts_in_cone(centre_ra, centre_dec, radius_deg)
        host_positions = project_points(
            self._wcs, gs, ((item.ra_degrees, item.dec_degrees) for item in hosts)
        )
        exoplanet_points = []
        for position, host in zip(host_positions, hosts):
            if position is None:
                continue
            body = self._exoplanet_tooltip(host)
            exoplanet_points.append((position[0], position[1], host.host_name, body))
            self._add_catalogue_source(
                "exoplanets", position, f"Exoplanet host · {host.host_name}", body
            )
        self._viewer.set_context_markers("exoplanets", exoplanet_points, gs)

        comparison_positions = project_points(
            self._wcs, gs, ((item.ra_deg, item.dec_deg) for item in result.comparisons)
        )
        comparison_points = []
        for position, item in zip(comparison_positions, result.comparisons):
            if position is None:
                continue
            body = self._comparison_tooltip(item)
            comparison_points.append((position[0], position[1], body))
            self._add_catalogue_source(
                "comparisons", position, f"VSP reference · {item.auid}", body
            )
        self._viewer.set_comparison_markers(comparison_points, gs)

        target_positions = project_points(
            self._wcs,
            gs,
            ((item.ra_deg, item.dec_deg) for item in self._target_set.stars),
        )
        target_points = []
        for position, item in zip(target_positions, self._target_set.stars):
            if position is None:
                continue
            body = self._target_tooltip(item)
            target_points.append((position[0], position[1], item.display_name, item.role, body))
            self._add_catalogue_source(
                "targets", position, f"Selected {item.role} · {item.display_name}", body
            )
        self._viewer.set_target_markers(target_points, gs)

        counts = {
            "catalogue": len(field_points),
            "variables": len(variable_points),
            "galaxies": len(context_points["galaxies"]),
            "nebulae_clusters": len(context_points["nebulae_clusters"]),
            "exoplanets": len(exoplanet_points),
            "other_objects": len(context_points["other_objects"]),
            "comparisons": len(comparison_points),
            "targets": len(target_points),
        }
        setters = {
            "catalogue": self._viewer.set_field_catalogue_enabled,
            "variables": self._viewer.set_catalog_enabled,
            "galaxies": lambda on: self._viewer.set_context_enabled("galaxies", on),
            "nebulae_clusters": lambda on: self._viewer.set_context_enabled("nebulae_clusters", on),
            "exoplanets": lambda on: self._viewer.set_context_enabled("exoplanets", on),
            "other_objects": lambda on: self._viewer.set_context_enabled("other_objects", on),
            "comparisons": self._viewer.set_comparison_enabled,
            "targets": self._viewer.set_target_enabled,
        }
        for name, count in counts.items():
            self._overlay_bar.set_count(name, count)
            self._arm_overlay(name, True, setters[name])
        has_labels = any(counts.values())
        self._arm_overlay("labels", has_labels, self._viewer.set_marker_labels_enabled)

    def _add_catalogue_source(
        self, layer: str, position: tuple[float, float], title: str, body: str
    ) -> None:
        self._catalog_sources.append((layer, position, title, body))

    def _magnitude_is_visible(self, value: float | None) -> bool:
        return value is None or float(value) <= self._display_mag_limit

    @staticmethod
    def _deduplicate_points(points, radius_px: float = 8.0) -> list:
        selected = []
        radius2 = radius_px**2
        for point in points:
            if any(
                (point[0] - other[0]) ** 2 + (point[1] - other[1]) ** 2 <= radius2
                for other in selected
            ):
                continue
            selected.append(point)
        return selected

    # ------------------------------------------------------------------
    # Click-to-measure
    # ------------------------------------------------------------------

    def _on_star_clicked(self, x_disp: float, y_disp: float) -> None:
        gp = self._disp_to_green(x_disp, y_disp)
        if gp is None or self._raw is None:
            return
        source = self._nearest_catalogue_source(gp[0], gp[1])
        if source is not None:
            self._show_catalogue_selection(source)
            return
        self._selected_catalogue = None
        meas = measure_star_at(self._raw, gp[0], gp[1], self._radius)
        if meas is None:
            self._viewer.clear_selection()
            self._selected_green = None
            self._selected_measurement = None
            self._update_info()
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

    def _nearest_catalogue_source(self, gx: float, gy: float):
        priorities = {
            "targets": 0,
            "variables": 1,
            "comparisons": 2,
            "exoplanets": 3,
            "galaxies": 4,
            "nebulae_clusters": 4,
            "other_objects": 5,
            "catalogue": 6,
        }
        visible = [
            source for source in self._catalog_sources if self._overlay_bar.is_checked(source[0])
        ]
        if not visible:
            return None
        tolerance = 10.0
        if self._green_shape and self._disp_shape and self._disp_shape[1] > 0:
            tolerance = max(6.0, 14.0 * self._green_shape[1] / self._disp_shape[1])
        candidates = [
            (
                ((source[1][0] - gx) ** 2 + (source[1][1] - gy) ** 2) ** 0.5,
                priorities.get(source[0], 9),
                source,
            )
            for source in visible
        ]
        distance, _priority, source = min(candidates, default=(float("inf"), 9, None))
        return source if distance <= tolerance else None

    def _show_catalogue_selection(self, source) -> None:
        _layer, position, title, body = source
        self._selected_green = position
        self._selected_catalogue = (title, body)
        self._selected_measurement = measure_star_at(
            self._raw,
            position[0],
            position[1],
            self._radius,
            search=TRACK_SNAP_SEARCH,
        )
        dp = self._green_to_disp(position[0], position[1])
        if dp is not None:
            self._viewer.mark_selection(
                dp[0],
                dp[1],
                "",
                self._green_len_to_disp(self._radius),
                show_label=False,
            )
        self._tab_widget.setCurrentIndex(0)
        self._update_info()

    def _show_selection(self, meas) -> None:
        dp = self._green_to_disp(meas.x, meas.y)
        if dp is None:
            return
        radius_disp = self._green_len_to_disp(meas.radius)
        if self._selected_catalogue is None:
            self._viewer.mark_selection(dp[0], dp[1], self._format_star_text(meas), radius_disp)
        else:
            self._viewer.mark_selection(dp[0], dp[1], "", radius_disp, show_label=False)
        self._selected_measurement = meas
        self._update_info()

    def _format_star_text(self, meas) -> str:
        parts = ["Selected star"]
        if meas.fwhm is not None:
            parts.append(f"FWHM {meas.fwhm * arcsec_per_green_px():.1f}″")
        if meas.hfd is not None:
            parts.append(f"HFD {meas.hfd * arcsec_per_green_px():.1f}″")
        if meas.eccentricity is not None:
            parts.append(f"ecc {meas.eccentricity:.2f}")
        parts.append(f"SNR {meas.snr:.0f}")
        parts.append(f"peak {meas.peak_adu} ADU")
        text = "   ".join(parts) + f"\nscale  {arcsec_per_full_px():.2f}″/px"
        if self._wcs is not None:
            ra_h, dec_d = self._wcs.pixel_to_radec(meas.x, meas.y)
            text += f"\nRA {format_ra_hms(ra_h)}  Dec {format_dec_dms(dec_d)}"
        return text

    @staticmethod
    def _variable_tooltip(item) -> str:
        lines = ["AAVSO VSX variable star"]
        if item.var_type:
            lines.append(f"Type  {item.var_type}" + (" (suspected)" if item.is_suspected else ""))
        limits = []
        if item.max_mag:
            limits.append(f"maximum {item.max_mag}")
        if item.min_mag and item.min_mag != "?":
            limits.append(f"minimum {item.min_mag}")
        if limits:
            lines.append("  ".join(limits))
        if item.period:
            lines.append(f"Period  {item.period:g} d")
        if item.auid:
            lines.append(f"AUID  {item.auid}")
        lines.append(f"RA {format_ra_hms(item.ra_deg / 15.0)}  Dec {format_dec_dms(item.dec_deg)}")
        return "\n".join(lines)

    @staticmethod
    def _gaia_tooltip(star, identity=None) -> str:
        lines = []
        if identity is not None:
            lines.extend((f"Name  {identity.name}", f"Object type  {identity.object_type or '—'}"))
        lines.append(f"Gaia DR3 source  {star.source_id}")
        for label, value in (
            ("Gaia G", star.g_mag),
            ("Gaia BP", star.bp_mag),
            ("Gaia RP", star.rp_mag),
        ):
            if value is not None:
                lines.append(f"{label} magnitude  {value:.3f}")
        lines.extend(
            (
                f"RA {format_ra_hms(star.ra_deg / 15.0)}  Dec {format_dec_dms(star.dec_deg)}",
                "Sources  Gaia DR3" + (" · SIMBAD" if identity is not None else ""),
            )
        )
        return "\n".join(lines)

    @staticmethod
    def _named_tooltip(item) -> str:
        lines = [
            "SIMBAD identified object",
            f"Name  {item.name}",
            f"Object type  {item.object_type or '—'}",
        ]
        lines.extend(
            f"SIMBAD {band} magnitude  {value:.3f}" for band, value in getattr(item, "mags", ())
        )
        lines.append(f"RA {format_ra_hms(item.ra_deg / 15.0)}  Dec {format_dec_dms(item.dec_deg)}")
        return "\n".join(lines)

    @staticmethod
    def _deep_sky_tooltip(item) -> str:
        lines = [
            "Argos Essential Catalogue",
            f"Name  {item.name}",
            f"Object type  {item.object_type or 'Deep-sky object'}",
        ]
        if item.magnitude is not None:
            lines.append(f"Magnitude  {item.magnitude:.1f}")
        if item.aliases:
            lines.append(f"Also  {', '.join(item.aliases[:2])}")
        lines.append(
            f"RA {format_ra_hms(item.ra_degrees / 15.0)}  "
            f"Dec {format_dec_dms(item.dec_degrees)}"
        )
        return "\n".join(lines)

    @staticmethod
    def _exoplanet_tooltip(host) -> str:
        lines = [
            "NASA Exoplanet Archive host",
            f"Host  {host.host_name}",
            f"Confirmed planet(s)  {', '.join(host.planet_names)}",
        ]
        lines.extend(f"{band} magnitude  {value:.3f}" for band, value in getattr(host, "mags", ()))
        lines.extend(
            (
                f"RA {format_ra_hms(host.ra_degrees / 15.0)}  "
                f"Dec {format_dec_dms(host.dec_degrees)}",
                "Source  NASA Exoplanet Archive cache/API",
            )
        )
        return "\n".join(lines)

    @staticmethod
    def _comparison_tooltip(item) -> str:
        magnitudes = "  ".join(f"{band.band} {band.mag:.3f}" for band in item.bands) or "—"
        return (
            "AAVSO VSP reference candidate\n"
            f"AUID  {item.auid}\n"
            f"Catalogue magnitudes  {magnitudes}\n"
            f"RA {format_ra_hms(item.ra_deg / 15.0)}  Dec {format_dec_dms(item.dec_deg)}"
        )

    @staticmethod
    def _target_tooltip(item) -> str:
        magnitudes = "  ".join(f"{band} {value:.3f}" for band, value in item.mags.items()) or "—"
        return (
            f"Saved photometry {item.role}\n"
            f"Name  {item.display_name}\n"
            f"AUID  {item.auid or '—'}\n"
            f"Catalogue magnitudes  {magnitudes}\n"
            f"RA {format_ra_hms(item.ra_deg / 15.0)}  Dec {format_dec_dms(item.dec_deg)}"
        )

    @staticmethod
    def _object_category(object_type: str) -> str:
        value = (object_type or "").casefold()
        if any(token in value for token in ("gal", "qso", "agn")) or value in {
            "g",
            "gi",
            "gx",
            "gic",
        }:
            return "galaxy"
        if any(token in value for token in ("neb", "hii")) or value in {
            "pn",
            "pl",
            "nb",
            "snr",
        }:
            return "nebula"
        if any(token in value for token in ("cluster", "cl*")) or value in {
            "oc",
            "gc",
            "gb",
            "glc",
            "c+n",
        }:
            return "cluster"
        if "*" in value or "star" in value:
            return "star"
        return "other"

    @staticmethod
    def _is_generic_identifier(name: str) -> bool:
        compact = " ".join((name or "").split()).casefold()
        return compact.startswith(
            (
                "gaia ",
                "2mass ",
                "ucac",
                "sdss ",
                "pan-starrs ",
                "ps1 ",
                "wise ",
                "allwise ",
                "lamost ",
                "ztf ",
                "asassn ",
            )
        )

    # ------------------------------------------------------------------
    # Coordinate helpers
    # ------------------------------------------------------------------

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

    def _set_solve_text(self, text: str, color: str) -> None:
        self._solve_lbl.setText(text)
        self._solve_lbl.setStyleSheet(
            f"color:{color}; font-family:{theme.FONT_MONO};"
            f" font-size:11px; background:transparent;"
        )

    def closeEvent(self, event) -> None:
        if self._solver is not None and self._solver.isRunning():
            self._solver.wait(2000)
        for worker in tuple(self._catalog_workers):
            if worker.isRunning():
                worker.wait(2000)
        super().closeEvent(event)
