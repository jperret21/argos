"""Statistics dock — the per-frame numbers as a compact key/value grid (WS9b).

NINA's Statistics panel: a dense 2-column grid of the current frame's whole-image
statistics (Mean / Median / StdDev / MAD / Min / Max / bit depth) plus the
green-plane star metrics (#Stars / HFD / FWHM / eccentricity). The thin
always-visible stats strip under the image shows only six of these; this dock is
where the user reads the full set on demand.

All values are *computed off the UI thread* by :func:`build_processed_frame`
(whole-frame median / MAD / std) and :mod:`argos.core.imaging.metrics` (stars);
the dock only formats and displays. It fills from the same per-frame payload the
Imaging page already dispatches to the other docks (see ``_on_processed``).
"""

from __future__ import annotations

from PyQt6.QtWidgets import QGridLayout, QWidget

from argos.ui import design


class StatisticsDock(design.Card):
    """Compact 2-column key/value grid of the current frame's statistics."""

    #: Ordered (label, key) rows. ``key`` is looked up in the value-label map so
    #: :meth:`set_frame` can address each cell without keeping widget refs around.
    _ROWS = (
        ("Mean", "mean"),
        ("Median", "median"),
        ("StdDev", "stddev"),
        ("MAD", "mad"),
        ("Min", "min"),
        ("Max", "max"),
        ("#Stars", "stars"),
        ("HFD", "hfd"),
        ("FWHM", "fwhm"),
        ("Eccentricity", "ecc"),
        ("Bit depth", "bits"),
    )

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Statistics", parent)
        self._values: dict[str, design.MetricLabel] = {}
        self._build_ui()

    def _build_ui(self) -> None:
        outer = design.card_layout(self)
        grid = QGridLayout()
        grid.setHorizontalSpacing(design.SPACING_MD)
        grid.setVerticalSpacing(design.SPACING_SM)
        grid.setColumnStretch(1, 1)
        for row, (label, key) in enumerate(self._ROWS):
            value = design.MetricLabel("—")
            self._values[key] = value
            grid.addWidget(design.MutedLabel(label), row, 0)
            grid.addWidget(value, row, 1)
        outer.addLayout(grid)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_frame(self, pf) -> None:
        """Refresh all cells from a :class:`ProcessedFrame` payload.

        ``pf`` carries the whole-frame stats (``vmean``/``vmedian``/``vstd``/
        ``vmad``/``vmin``/``vmax``/``bit_depth``), the green-plane focus metrics
        (``metrics.hfd``/``metrics.star_count``) and the detected-star field
        (``stars.mean_fwhm``/``stars.mean_eccentricity``) — all computed off the
        UI thread.
        """
        m = pf.metrics
        self._values["mean"].setText(f"{pf.vmean:.1f}")
        self._values["median"].setText(f"{pf.vmedian:.0f}")
        self._values["stddev"].setText(f"{pf.vstd:.1f}")
        self._values["mad"].setText(f"{pf.vmad:.1f}")
        self._values["min"].setText(f"{int(pf.vmin)}")
        self._values["max"].setText(f"{int(pf.vmax)}")
        self._values["stars"].setText(str(m.star_count))
        self._values["hfd"].setText(f"{m.hfd:.2f} px" if m.hfd is not None else "—")
        fwhm = pf.stars.mean_fwhm
        self._values["fwhm"].setText(f"{fwhm:.2f} px" if fwhm is not None else "—")
        ecc = pf.stars.mean_eccentricity
        self._values["ecc"].setText(f"{ecc:.3f}" if ecc is not None else "—")
        self._values["bits"].setText(f"{pf.bit_depth}-bit")

    def clear(self) -> None:
        """Reset every cell to the empty placeholder (e.g. on target switch)."""
        for value in self._values.values():
            value.setText("—")
