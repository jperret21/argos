"""Preset colour palettes for the Argos theme system (WS9c).

Each palette is a :class:`Palette` instance.  Import ``PALETTES`` (an ordered
dict of ``name → Palette``) and pass an entry to
:func:`argos.ui.theme.apply_palette` to switch themes at runtime.

Naming rules
------------
- ``bg`` / ``bg2`` — main window background / sub-surface (inputs, log)
- ``surface`` — raised elements (buttons, tab backgrounds)
- ``border`` / ``border_soft`` — hard and subtle separators
- ``fg`` / ``fg_muted`` / ``fg_disabled`` — text hierarchy
- ``accent`` / ``accent_hover`` / ``accent_deep`` — primary action colour
- ``cyan`` — secondary info accent (coords, mount status)
- ``success`` / ``warning`` / ``danger`` — semantic colours
- ``variable`` — VSX variable-star markers
- ``font_ui`` / ``font_mono`` — CSS font-family stacks
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Palette:
    """All colour tokens that parameterise the global QSS and widget stylesheets."""

    name: str

    # Backgrounds / surfaces
    bg: str
    bg2: str
    surface: str
    border: str
    border_soft: str

    # Text
    fg: str
    fg_muted: str
    fg_disabled: str

    # Accent (primary action / focus)
    accent: str
    accent_hover: str
    accent_deep: str

    # Secondary info accent
    cyan: str

    # Semantic
    success: str
    warning: str
    danger: str

    # Variable-star markers
    variable: str

    # Font stacks (CSS font-family values, already quoted where needed)
    font_ui: str
    font_mono: str


# ---------------------------------------------------------------------------
# Observatory — restrained neutral default for a scientific instrument.
#
# The previous blue/green/purple combination made every state compete for
# attention.  This palette reserves chroma for the active action and real
# warnings, while the everyday workspace stays in neutral graphite.
# ---------------------------------------------------------------------------

EQUILUX = Palette(
    name="Observatory",
    bg="#1c2026",
    bg2="#15191e",
    surface="#252b33",
    border="#343c47",
    border_soft="#282f38",
    fg="#e2e6ea",
    fg_muted="#9da8b5",
    fg_disabled="#626d78",
    accent="#7d9bb8",
    accent_hover="#91aec9",
    accent_deep="#5e7d9b",
    cyan="#7f9ead",
    success="#85a58a",
    warning="#b79a6a",
    danger="#b97979",
    variable="#a895bc",
    font_ui='"Avenir Next", "SF Pro Text", "Segoe UI Variable", "Noto Sans", "Helvetica Neue", sans-serif',
    font_mono='"SF Mono", "Cascadia Mono", "Noto Sans Mono", "Menlo", "Consolas", monospace',
)

# ---------------------------------------------------------------------------
# Charcoal — NINA-like charcoal + teal accent
# ---------------------------------------------------------------------------

CHARCOAL = Palette(
    name="Charcoal",
    bg="#222629",
    bg2="#161a1d",
    surface="#2e3236",
    border="#3d4347",
    border_soft="#303539",
    fg="#e0e3e6",
    fg_muted="#8c9198",
    fg_disabled="#505457",
    accent="#00b4d8",
    accent_hover="#48cae4",
    accent_deep="#0077b6",
    cyan="#52b8c8",
    success="#6aab5e",
    warning="#c4933a",
    danger="#d45c6e",
    variable="#b07cd4",
    font_ui='"Avenir Next", "SF Pro Text", "Segoe UI Variable", "Noto Sans", "Helvetica Neue", sans-serif',
    font_mono='"SF Mono", "Cascadia Mono", "Noto Sans Mono", "Menlo", "Consolas", monospace',
)

# ---------------------------------------------------------------------------
# High Contrast — maximum legibility (WCAG AA target)
# ---------------------------------------------------------------------------

HIGH_CONTRAST = Palette(
    name="High Contrast",
    bg="#000000",
    bg2="#0a0a0a",
    surface="#1a1a1a",
    border="#666666",
    border_soft="#444444",
    fg="#ffffff",
    fg_muted="#cccccc",
    fg_disabled="#666666",
    accent="#4db8ff",
    accent_hover="#80ccff",
    accent_deep="#1a8fe0",
    cyan="#5fd3e8",
    success="#66dd44",
    warning="#ffcc00",
    danger="#ff4444",
    variable="#dd88ff",
    font_ui='"Avenir Next", "SF Pro Text", "Segoe UI Variable", "Noto Sans", "Helvetica Neue", sans-serif',
    font_mono='"SF Mono", "Cascadia Mono", "Noto Sans Mono", "Menlo", "Consolas", monospace',
)

# ---------------------------------------------------------------------------
# Night (Red) — every colour derived from red/dark-red for dark adaptation.
#
# Rules:
#  - bg / bg2 / surface: very dark reds (low luminance, no blue/green bleed)
#  - border: slightly lighter dark red
#  - fg: desaturated warm red (not orange, just enough chroma to read against bg)
#  - accent: brighter red — the "primary action" highlight
#  - success / warning / danger distinguished by brightness/lightness only,
#    NOT by hue (all stay in the red family so no green/blue leaks)
#    success = dim/mid red  warning = mid-bright red  danger = bright red
#  - cyan / variable: warm red tint variants, no blue/green dominant channel
# ---------------------------------------------------------------------------

NIGHT_RED = Palette(
    name="Night (Red)",
    bg="#1a0000",
    bg2="#110000",
    surface="#280a0a",
    border="#3d1010",
    border_soft="#2a0808",
    fg="#c08080",  # desaturated warm red — readable but dim
    fg_muted="#7a4040",  # secondary: noticeably dimmer
    fg_disabled="#3d2020",
    accent="#e03030",  # bright red — primary action / focus
    accent_hover="#f04040",
    accent_deep="#b82020",
    cyan="#c45050",  # "info" tint — warm mid-red, no blue component
    success="#882828",  # dim red — "connected / OK" (lowest brightness)
    warning="#c44040",  # mid-bright red — caution
    danger="#ff5050",  # maximum brightness — error / alarm
    variable="#a03838",  # VSX markers — mid-dark red variant
    font_ui='"Avenir Next", "SF Pro Text", "Segoe UI Variable", "Noto Sans", "Helvetica Neue", sans-serif',
    font_mono='"SF Mono", "Cascadia Mono", "Noto Sans Mono", "Menlo", "Consolas", monospace',
)

# ---------------------------------------------------------------------------
# Registry — ordered dict consumed by the Settings UI and the theme module
# ---------------------------------------------------------------------------

#: All available preset palettes, in display order.
PALETTES: dict[str, Palette] = {p.name: p for p in (EQUILUX, CHARCOAL, HIGH_CONTRAST, NIGHT_RED)}
