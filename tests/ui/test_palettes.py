"""Unit tests for the WS9c palette/theme system.

Checks:
1. Every Palette preset has all required fields set (non-empty strings).
2. Equilux constants match the historical hard-coded values byte-for-byte.
3. Night (Red) contains no green-dominant or blue-dominant colours — every hex
   triplet (R, G, B) must have R >= G and R >= B (i.e. red channel dominates
   or ties with both others).
4. apply_palette() rebinds module-level constants correctly.
5. get_stylesheet() reflects the newly applied palette.
"""

from __future__ import annotations

import dataclasses
import re

import pytest

from argos.ui.palettes import EQUILUX, NIGHT_RED, PALETTES, Palette
from argos.ui import theme


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _all_color_fields(palette: Palette) -> list[tuple[str, str]]:
    """Return (field_name, value) for every str field whose name is not a font."""
    return [
        (f.name, getattr(palette, f.name))
        for f in dataclasses.fields(palette)
        if f.name not in ("name", "font_ui", "font_mono")
    ]


def _parse_hex(color: str) -> tuple[int, int, int]:
    """Parse '#rrggbb' → (r, g, b) integer triple."""
    m = re.fullmatch(r"#([0-9a-fA-F]{2})([0-9a-fA-F]{2})([0-9a-fA-F]{2})", color.strip())
    assert m is not None, f"Not a valid #rrggbb color: {color!r}"
    return int(m.group(1), 16), int(m.group(2), 16), int(m.group(3), 16)


# ---------------------------------------------------------------------------
# Test 1 — all palettes are complete
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("palette", list(PALETTES.values()))
def test_palette_complete(palette: Palette) -> None:
    """Every color field must be a non-empty string."""
    for field_name, value in _all_color_fields(palette):
        assert isinstance(value, str) and value.strip(), (
            f"Palette '{palette.name}' field '{field_name}' is empty or not a string"
        )
    # Font stacks must also be non-empty
    assert palette.font_ui.strip(), f"Palette '{palette.name}' font_ui is empty"
    assert palette.font_mono.strip(), f"Palette '{palette.name}' font_mono is empty"


# ---------------------------------------------------------------------------
# Test 2 — Equilux matches historical byte-identical defaults
# ---------------------------------------------------------------------------

_HISTORICAL = {
    "bg":          "#2d2d2d",
    "bg2":         "#1f1f1f",
    "surface":     "#3c3c3c",
    "border":      "#484848",
    "border_soft": "#3a3a3a",
    "fg":          "#dedede",
    "fg_muted":    "#9a9a9a",
    "fg_disabled": "#5a5a5a",
    "accent":      "#5294e2",
    "accent_hover":"#6aa3ea",
    "accent_deep": "#3a7bd5",
    "cyan":        "#4eb3c9",
    "success":     "#7ab648",
    "warning":     "#c89030",
    "danger":      "#d45c6e",
    "variable":    "#c678dd",
}

@pytest.mark.parametrize("field,expected", list(_HISTORICAL.items()))
def test_equilux_matches_historical(field: str, expected: str) -> None:
    actual = getattr(EQUILUX, field)
    assert actual.lower() == expected.lower(), (
        f"EQUILUX.{field}: expected {expected!r}, got {actual!r}"
    )


# ---------------------------------------------------------------------------
# Test 3 — Night (Red) has no green-dominant or blue-dominant colours
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("field_name,value", _all_color_fields(NIGHT_RED))
def test_night_palette_no_green_blue_dominant(field_name: str, value: str) -> None:
    """In Night (Red), the red channel must be >= both green and blue channels."""
    r, g, b = _parse_hex(value)
    assert r >= g and r >= b, (
        f"NIGHT_RED.{field_name} = {value!r}: "
        f"red channel ({r}) must dominate over green ({g}) and blue ({b})"
    )


# ---------------------------------------------------------------------------
# Test 4 — apply_palette() rebinds module-level constants
# ---------------------------------------------------------------------------

def test_apply_palette_rebinds_constants() -> None:
    from argos.ui.palettes import CHARCOAL

    original_accent = theme.ACCENT
    try:
        theme.apply_palette(CHARCOAL)
        assert theme.ACCENT == CHARCOAL.accent
        assert theme.BG == CHARCOAL.bg
        assert theme.SUCCESS == CHARCOAL.success
        assert theme.DANGER == CHARCOAL.danger
        # Back-compat aliases
        assert theme.TEXT_PRIMARY == CHARCOAL.fg
        assert theme.TEXT_MUTED == CHARCOAL.fg_muted
        assert theme.SURFACE_3 == CHARCOAL.bg2
    finally:
        # Restore equilux so other tests are unaffected
        theme.apply_palette(EQUILUX)
        assert theme.ACCENT == original_accent


# ---------------------------------------------------------------------------
# Test 5 — get_stylesheet() reflects the applied palette
# ---------------------------------------------------------------------------

def test_get_stylesheet_reflects_palette() -> None:
    from argos.ui.palettes import HIGH_CONTRAST

    try:
        theme.apply_palette(HIGH_CONTRAST)
        qss = theme.get_stylesheet()
        assert HIGH_CONTRAST.bg in qss, "QSS should contain the new bg color"
        assert HIGH_CONTRAST.accent in qss, "QSS should contain the new accent color"
        # The old equilux accent should NOT appear (they differ)
        assert EQUILUX.accent not in qss
    finally:
        theme.apply_palette(EQUILUX)
