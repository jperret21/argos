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
# Observatory — Argos' restrained graphite-and-brass default.
#
# The interface borrows the brass from the Argos mark (#c49a3c), then reserves
# it for focus, selection and deliberate actions.  The workspace itself stays
# neutral graphite: a scientific cockpit should not read like a dashboard of
# unrelated blue/green/purple status colours.
# ---------------------------------------------------------------------------

EQUILUX = Palette(
    name="Observatory",
    bg="#191b1f",
    bg2="#121417",
    surface="#22262c",
    border="#47515c",
    border_soft="#343c45",
    fg="#e8e5df",
    fg_muted="#aaa8a2",
    fg_disabled="#6d7278",
    accent="#c49a3c",
    accent_hover="#d6b25d",
    accent_deep="#8d6b2b",
    cyan="#7da8b2",
    success="#83a68b",
    warning="#d0a85a",
    danger="#bf7772",
    variable="#8fb7ca",
    font_ui='"Helvetica Neue", "Segoe UI", "Noto Sans", sans-serif',
    font_mono='"SF Mono", "Cascadia Mono", "JetBrains Mono", "Noto Sans Mono", "Menlo", "Consolas", monospace',
)

# ---------------------------------------------------------------------------
# Charcoal — higher-contrast graphite variant, still within Argos' brass family
# ---------------------------------------------------------------------------

CHARCOAL = Palette(
    name="Charcoal",
    bg="#232529",
    bg2="#181a1d",
    surface="#2c3035",
    border="#545c65",
    border_soft="#3d444c",
    fg="#ece9e2",
    fg_muted="#b0aea7",
    fg_disabled="#73777b",
    accent="#c49a3c",
    accent_hover="#d8b75f",
    accent_deep="#977331",
    cyan="#86a9af",
    success="#8ca58c",
    warning="#d1aa5e",
    danger="#c57b76",
    variable="#9abfcd",
    font_ui='"Helvetica Neue", "Segoe UI", "Noto Sans", sans-serif',
    font_mono='"SF Mono", "Cascadia Mono", "JetBrains Mono", "Noto Sans Mono", "Menlo", "Consolas", monospace',
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
    bg="#1a0304",
    bg2="#100102",
    surface="#2b080a",
    border="#501719",
    border_soft="#350c0e",
    fg="#d88f8f",  # readable, but deliberately well below white luminance
    fg_muted="#a65758",
    fg_disabled="#5a2829",
    accent="#c14d50",
    accent_hover="#df6264",
    accent_deep="#7d2327",
    cyan="#bb6667",  # informational tint, still strictly red-dominant
    success="#8b3437",  # state is communicated by label/icon as well as luminance
    warning="#ad494c",
    danger="#e05e61",
    variable="#985055",
    font_ui='"Helvetica Neue", "Segoe UI", "Noto Sans", sans-serif',
    font_mono='"SF Mono", "Cascadia Mono", "JetBrains Mono", "Noto Sans Mono", "Menlo", "Consolas", monospace',
)

# ---------------------------------------------------------------------------
# Registry — ordered dict consumed by the Settings UI and the theme module
# ---------------------------------------------------------------------------

#: All available preset palettes, in display order.
PALETTES: dict[str, Palette] = {p.name: p for p in (EQUILUX, CHARCOAL, NIGHT_RED)}
