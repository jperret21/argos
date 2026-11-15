"""The Frame Viewer's FITS reader (``argos/ui/analysis_window.py``)."""

from __future__ import annotations

import numpy as np

from argos.core.imaging.metrics import measure_star_at


def _star_frame(rng: np.random.Generator) -> np.ndarray:
    """A 200×200 GRBG frame in counts: sky 1000 ± 20 ADU, one star of peak 20 000."""
    frame = rng.normal(1000.0, 20.0, size=(200, 200))
    yy, xx = np.mgrid[0:200, 0:200]
    frame += 19000.0 * np.exp(-((xx - 100.0) ** 2 + (yy - 120.0) ** 2) / (2 * 3.0**2))
    return frame


def test_a_float_frame_in_0_1_is_measured_in_counts_s65(tmp_path) -> None:
    """S65: a calibrated float frame in [0, 1] (Siril's ``r_light_*.fit``) was read
    as is, so Measure star gave SNR 0 and peak 0 ADU (the sky sigma is floored at
    a count, the peak truncated to an integer) and Identify field handed ASTAP a
    black plane. It is scaled by 65535, as the web viewer does."""
    from astropy.io import fits

    from argos.ui.analysis_window import read_fits_2d

    counts = _star_frame(np.random.default_rng(7))
    fits.PrimaryHDU(counts.astype(np.uint16)).writeto(tmp_path / "counts.fit")
    fits.PrimaryHDU((counts / 65535.0).astype(np.float32)).writeto(tmp_path / "unit.fit")

    raw_counts = read_fits_2d(str(tmp_path / "counts.fit"))
    raw_unit = read_fits_2d(str(tmp_path / "unit.fit"))
    assert float(raw_unit.max()) > 1000.0
    m_counts = measure_star_at(raw_counts, 50, 60, 6)
    m_unit = measure_star_at(raw_unit, 50, 60, 6)
    assert m_unit is not None and m_counts is not None
    assert m_unit.snr > 100 and abs(m_unit.snr - m_counts.snr) < 0.02 * m_counts.snr
    assert abs(m_unit.peak_adu - m_counts.peak_adu) <= 2


def test_a_float_frame_in_counts_is_read_unchanged(tmp_path) -> None:
    from astropy.io import fits

    from argos.ui.analysis_window import read_fits_2d

    counts = _star_frame(np.random.default_rng(3)).astype(np.float32)
    fits.PrimaryHDU(counts).writeto(tmp_path / "float_counts.fit")
    assert np.array_equal(read_fits_2d(str(tmp_path / "float_counts.fit")), counts)
