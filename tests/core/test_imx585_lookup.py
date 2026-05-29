"""Sanity checks for the IMX585 calibration lookup."""

from __future__ import annotations

from seercontrol.core.imaging import imx585


def test_egain_monotonically_decreases_with_gain() -> None:
    """Higher gain setting → more amplification → fewer e- per ADU."""
    values = [imx585.lookup_egain(g) for g in (0, 80, 100, 200, 300, 500, 600)]
    for i in range(len(values) - 1):
        assert values[i] > values[i + 1], (
            f"EGAIN should decrease with gain, but {values[i]} <= {values[i + 1]}"
        )


def test_egain_within_postprod_range_at_typical_gain() -> None:
    """Pipeline (varstar postprod) accepts 0.05 < g < 30 — gain=80 should pass."""
    g = imx585.lookup_egain(80)
    assert 0.05 < g < 30, f"EGAIN at gain=80 outside accepted range: {g}"


def test_read_noise_within_physical_bounds() -> None:
    """IMX585 read noise stays between ~0.5 and ~5 e- across the gain range."""
    for gain in (0, 80, 100, 252, 400, 600):
        rn = imx585.lookup_read_noise(gain)
        assert 0.5 <= rn <= 5.0, f"RDNOISE({gain})={rn} out of physical bounds"


def test_full_well_drops_at_hcg_threshold() -> None:
    """HCG mode at gain≥252 trades dynamic range for read noise."""
    assert imx585.full_well_capacity(100) == imx585.FULL_WELL_E
    assert imx585.full_well_capacity(251) == imx585.FULL_WELL_E
    assert imx585.full_well_capacity(252) < imx585.FULL_WELL_E


def test_lookup_clamps_at_extremes() -> None:
    """Gain values outside the anchor range still return finite values."""
    assert imx585.lookup_egain(-50) == imx585.lookup_egain(0)
    assert imx585.lookup_egain(1000) == imx585.lookup_egain(600)
