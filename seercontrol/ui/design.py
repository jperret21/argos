"""SeerControl design system — single source of truth for layout primitives.

Every page and widget should compose with the elements below instead of
re-implementing spacing, typography, button styling, or card chrome. The
goal is that a new screen built three months from now still looks like the
rest of the app without anyone having to remember a stylesheet snippet.

Conventions:
    Spacing — use the constants ``SPACING_*`` not raw pixel values.
    Cards   — use :class:`Card` (with :func:`card_layout`) for every dock /
              right-rail group. Never instantiate a bare ``QGroupBox``.
    Buttons — use :class:`PrimaryButton`, :class:`SuccessButton`,
              :class:`DangerButton`, or :class:`SecondaryButton` rather
              than ``QPushButton(...).setProperty("class", "primary")``.
    Labels  — use :class:`MutedLabel` for form keys, :class:`MetricLabel`
              for monospace values (RA/Dec/HFD), and :class:`SectionLabel`
              for sub-section titles inside a card.

If something looks "off" in the UI, fix it here — *every* page picks the
change up automatically.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from seercontrol.ui import theme


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
INPUT_HEIGHT          = 30
BUTTON_HEIGHT         = 34
BUTTON_PRIMARY_HEIGHT = 40

# Right-rail width range used by the Imaging page (and any future page that
# pins controls to the side of an image). Generous enough that long button
# labels ("▶  Sequence", "■  Abort") never clip.
RIGHT_RAIL_MIN_WIDTH = 420
RIGHT_RAIL_MAX_WIDTH = 580

# Typography sizes (pixel values, no rem/em in Qt stylesheets).
FONT_SIZE_BODY    = 12
FONT_SIZE_LABEL   = 12
FONT_SIZE_METRIC  = 15
FONT_SIZE_HEADING = 20
FONT_SIZE_SECTION = 12


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


# --------------------------------------------------------------------------- #
# Buttons                                                                      #
# --------------------------------------------------------------------------- #

class _BaseButton(QPushButton):
    """Common sizing + min-width so buttons in a row never get clipped."""

    _CLASS:  str = ""
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

    _CLASS  = "primary"
    _HEIGHT = BUTTON_PRIMARY_HEIGHT


class SuccessButton(_BaseButton):
    """Green, used for "start the long-running thing" (▶ Sequence, ▶ Tracking)."""

    _CLASS  = "success"
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
            f"color:{theme.FG_MUTED}; font-size:{FONT_SIZE_LABEL}px;"
            f" background:transparent;"
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
