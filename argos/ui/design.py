"""Argos design system — single source of truth for layout primitives.

Every page and widget should compose with the elements below instead of
re-implementing spacing, typography, button styling, or card chrome. The
goal is that a new screen built three months from now still looks like the
rest of the app without anyone having to remember a stylesheet snippet.

Conventions:

* ``Spacing`` — use the constants ``SPACING_*`` not raw pixel values.
* ``Cards`` — use :class:`Card` (with :func:`card_layout`) for every dock /
  right-rail group. Never instantiate a bare ``QGroupBox``.
* ``Buttons`` — use :class:`PrimaryButton`, :class:`SuccessButton`,
  :class:`DangerButton`, or :class:`SecondaryButton` rather
  than ``QPushButton(...).setProperty("class", "primary")``.
* ``Labels`` — use :class:`MutedLabel` for form keys, :class:`MetricLabel`
  for monospace values (RA/Dec/HFD), and :class:`SectionLabel`
  for sub-section titles inside a card.

If something looks "off" in the UI, fix it here — *every* page picks the
change up automatically.
"""

from __future__ import annotations

import math

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDoubleSpinBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from argos.ui import theme

# --------------------------------------------------------------------------- #
# Spacing scale — Material-style 4-pt grid                                     #
# --------------------------------------------------------------------------- #

SPACING_XS = 4
SPACING_SM = 6
SPACING_MD = 10
SPACING_LG = 16
SPACING_XL = 24

# Card padding (left, top, right, bottom) — leaves room above the title.
CARD_PADDING: tuple[int, int, int, int] = (14, 18, 14, 14)

# Standard widget heights — kept consistent so forms line up across pages.
INPUT_HEIGHT = 30
BUTTON_HEIGHT = 34
BUTTON_PRIMARY_HEIGHT = 40

# Right-rail width range used by the Imaging page (and any future page that
# pins controls to the side of an image). Generous enough that long button
# labels ("▶  Sequence", "■  Abort") never clip.
RIGHT_RAIL_MIN_WIDTH = 420
RIGHT_RAIL_MAX_WIDTH = 580

# Typography sizes (pixel values, no rem/em in Qt stylesheets).
FONT_SIZE_BODY = 13
FONT_SIZE_LABEL = 13
FONT_SIZE_METRIC = 16
FONT_SIZE_HEADING = 22
FONT_SIZE_SECTION = 13

# Default max content width for sparse, form-style pages so they don't stretch
# edge-to-edge on wide windows. Dense workspaces (Imaging) ignore this.
PAGE_MAX_WIDTH = 880

# Fixed width for the numeric value box of a SliderSpin, so a column of them
# lines up (slider stretches, value box stays put).
VALUE_FIELD_WIDTH = 92


# --------------------------------------------------------------------------- #
# Containers                                                                   #
# --------------------------------------------------------------------------- #


class Card(QGroupBox):
    """Standard dock / panel container.

    Reserves a Preferred-Fixed vertical size policy so that, even when its
    parent shrinks past the preferred height, the card holds its layout
    instead of collapsing widgets on top of each other (a common pyqtgraph /
    pyqt6 gotcha that bit us in R2 before the QScrollArea wrapper landed).
    """

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(title, parent)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)


def card_layout(card: Card) -> QVBoxLayout:
    """Return the standard outer ``QVBoxLayout`` for a :class:`Card`.

    Sets the project-wide card padding and the medium inter-row spacing in
    one call so callers can't accidentally drift to different values.
    """
    layout = QVBoxLayout(card)
    layout.setContentsMargins(*CARD_PADDING)
    layout.setSpacing(SPACING_MD)
    return layout


def horizontal_divider(parent: QWidget | None = None) -> QFrame:
    """1-px horizontal separator in the theme's border color."""
    line = QFrame(parent)
    line.setFrameShape(QFrame.Shape.HLine)
    line.setStyleSheet(f"color:{theme.BORDER}; background:{theme.BORDER};")
    line.setFixedHeight(1)
    return line


def scroll_page(max_width: int = PAGE_MAX_WIDTH) -> tuple[QScrollArea, QVBoxLayout]:
    """Build a vertically-scrolling page body, centered and width-capped.

    Returns ``(scroll_area, content_layout)``: add the scroll area to the page
    root layout and fill ``content_layout`` with cards/sections. Capping the
    width stops sparse, form-style pages from stretching edge-to-edge on wide
    windows (which makes them look empty and unstructured).
    """
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    holder = QWidget()
    outer = QHBoxLayout(holder)
    outer.setContentsMargins(SPACING_XL, SPACING_LG, SPACING_XL, SPACING_XL)

    column = QWidget()
    column.setMaximumWidth(max_width)
    content = QVBoxLayout(column)
    content.setContentsMargins(0, 0, 0, 0)
    content.setSpacing(SPACING_LG)

    outer.addStretch(1)
    outer.addWidget(column, 6)
    outer.addStretch(1)
    scroll.setWidget(holder)
    return scroll, content


def two_columns(spacing: int = SPACING_LG) -> tuple[QHBoxLayout, QVBoxLayout, QVBoxLayout]:
    """Return ``(row, left, right)`` — two equal side-by-side column layouts.

    Add the row to a content layout, then drop cards into ``left`` / ``right``
    to put several sections next to each other instead of one tall column.
    """
    row = QHBoxLayout()
    row.setSpacing(spacing)
    left = QVBoxLayout()
    left.setSpacing(spacing)
    right = QVBoxLayout()
    right.setSpacing(spacing)
    row.addLayout(left, 1)
    row.addLayout(right, 1)
    return row, left, right


# --------------------------------------------------------------------------- #
# Composite inputs                                                             #
# --------------------------------------------------------------------------- #


class SliderSpin(QWidget):
    """Slider + value box kept in sync — the camera-control idiom from NINA /
    SharpCap (drag for coarse, type for exact).

    Lays out as ``[────── slider ──────] [ value ]`` with the value box at a
    fixed width so a column of these lines up cleanly. Use ``logarithmic=True``
    for wide-range values like exposure time, where a linear slider would waste
    most of its travel on long exposures.
    """

    valueChanged = pyqtSignal(float)

    _STEPS = 1000

    def __init__(
        self,
        minimum: float,
        maximum: float,
        value: float,
        *,
        decimals: int = 0,
        step: float = 1.0,
        suffix: str = "",
        logarithmic: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._min = float(minimum)
        self._max = float(maximum)
        self._decimals = decimals
        self._log = logarithmic and self._min > 0.0
        self._guard = False

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(SPACING_SM)

        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(0, self._STEPS)

        self._spin: QDoubleSpinBox | QSpinBox
        if decimals > 0:
            self._spin = QDoubleSpinBox()
            self._spin.setDecimals(decimals)
            self._spin.setSingleStep(step)
            self._spin.setRange(self._min, self._max)
        else:
            self._spin = QSpinBox()
            self._spin.setSingleStep(int(step) or 1)
            self._spin.setRange(int(self._min), int(self._max))
        if suffix:
            self._spin.setSuffix(suffix)
        self._spin.setFixedWidth(VALUE_FIELD_WIDTH)
        self._spin.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        row.addWidget(self._slider, 1)
        row.addWidget(self._spin, 0)

        self._slider.valueChanged.connect(self._on_slider)
        self._spin.valueChanged.connect(self._on_spin)
        self.setValue(value)

    # value <-> slider mapping --------------------------------------------

    def _to_slider(self, value: float) -> int:
        value = max(self._min, min(self._max, float(value)))
        if self._log:
            lo, hi = math.log10(self._min), math.log10(self._max)
            t = (math.log10(value) - lo) / (hi - lo) if hi > lo else 0.0
        else:
            span = self._max - self._min
            t = (value - self._min) / span if span else 0.0
        return int(round(t * self._STEPS))

    def _from_slider(self, pos: int) -> float:
        t = pos / self._STEPS
        if self._log:
            lo, hi = math.log10(self._min), math.log10(self._max)
            return 10 ** (lo + t * (hi - lo))
        return self._min + t * (self._max - self._min)

    # sync ----------------------------------------------------------------

    def _on_slider(self, pos: int) -> None:
        if self._guard:
            return
        self._guard = True
        raw = self._from_slider(pos)
        self._spin.setValue(raw if self._decimals > 0 else int(round(raw)))
        self._guard = False
        self.valueChanged.emit(float(self._spin.value()))

    def _on_spin(self, _value: float) -> None:
        if self._guard:
            return
        self._guard = True
        self._slider.setValue(self._to_slider(self._spin.value()))
        self._guard = False
        self.valueChanged.emit(float(self._spin.value()))

    # public --------------------------------------------------------------

    def value(self) -> float:
        return float(self._spin.value())

    def setValue(self, value: float) -> None:
        self._guard = True
        self._spin.setValue(value if self._decimals > 0 else int(round(value)))
        self._slider.setValue(self._to_slider(value))
        self._guard = False


# --------------------------------------------------------------------------- #
# Buttons                                                                      #
# --------------------------------------------------------------------------- #


class _BaseButton(QPushButton):
    """Common sizing + min-width so buttons in a row never get clipped."""

    _CLASS: str = ""
    _HEIGHT: int = BUTTON_HEIGHT
    _MIN_WIDTH: int = 90

    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        if self._CLASS:
            self.setProperty("class", self._CLASS)
        self.setMinimumHeight(self._HEIGHT)
        self.setMinimumWidth(self._MIN_WIDTH)
        # Allow horizontal growth so two side-by-side buttons share the width.
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)


class PrimaryButton(_BaseButton):
    """Blue, used for the dominant action of a card (Slew, Take Shot…)."""

    _CLASS = "primary"
    _HEIGHT = BUTTON_PRIMARY_HEIGHT


class SuccessButton(_BaseButton):
    """Green, used for "start the long-running thing" (▶ Sequence, ▶ Tracking)."""

    _CLASS = "success"
    _HEIGHT = BUTTON_PRIMARY_HEIGHT


class DangerButton(_BaseButton):
    """Red, used for stop/abort/destructive actions."""

    _CLASS = "danger"


class SecondaryButton(_BaseButton):
    """Neutral outline button (Sync, Park, Jog…)."""

    _CLASS = ""


# --------------------------------------------------------------------------- #
# Labels                                                                       #
# --------------------------------------------------------------------------- #


class MutedLabel(QLabel):
    """Form-key / hint label — dim, no background. Min width so the label
    column of a QFormLayout never collapses below readable size."""

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setMinimumWidth(72)
        self.setStyleSheet(
            f"color:{theme.FG_MUTED}; font-size:{FONT_SIZE_LABEL}px;" f" background:transparent;"
        )


class MetricLabel(QLabel):
    """Live value — monospace, accent colour, bold."""

    def __init__(self, text: str = "—", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setStyleSheet(
            f"color:{theme.ACCENT}; font-size:{FONT_SIZE_METRIC}px;"
            f" font-weight:bold; font-family:{theme.FONT_MONO};"
            f" background:transparent;"
        )


class SectionLabel(QLabel):
    """Bold sub-heading inside a card (e.g. "Goto", "Calibration")."""

    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setStyleSheet(
            f"color:{theme.FG}; font-size:{FONT_SIZE_SECTION}px; font-weight:bold;"
            f" letter-spacing:0.5px; background:transparent;"
            f" padding-top:{SPACING_SM}px;"
        )


class HeadingLabel(QLabel):
    """Large blue heading — used by mode pages above their content."""

    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.setStyleSheet(
            f"color:{theme.ACCENT}; font-size:{FONT_SIZE_HEADING}px; font-weight:bold;"
            f" background:transparent; padding:{SPACING_MD}px 0;"
        )


# --------------------------------------------------------------------------- #
# Layout helpers                                                               #
# --------------------------------------------------------------------------- #


def button_row(*buttons: QPushButton, stretch_each: bool = True) -> QHBoxLayout:
    """Lay out buttons horizontally with the standard inter-button spacing.

    Pass ``stretch_each=False`` to keep buttons at their min size (useful
    when there are 3+ small action buttons and you don't want them to grow
    to fill the row).
    """
    row = QHBoxLayout()
    row.setSpacing(SPACING_SM)
    row.setContentsMargins(0, 0, 0, 0)
    for btn in buttons:
        if stretch_each:
            row.addWidget(btn, 1)
        else:
            row.addWidget(btn)
    return row


def stat_color(value: float, *, ok_below: float, warn_below: float) -> str:
    """Pick a colour for a metric based on threshold ranges.

    Used by HFD / drift / SNR readouts.

    Args:
        value:        Current metric value.
        ok_below:     Strictly below this the value is "good" (green).
        warn_below:   Strictly below this (but at or above ``ok_below``) the
                      value is "warning" (amber). At or above ``warn_below``
                      the value is "danger" (red).
    """
    if value < ok_below:
        return theme.SUCCESS
    if value < warn_below:
        return theme.WARNING
    return theme.DANGER
