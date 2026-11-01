"""Binary frame encoding: layout, alignment, exact statistics, speed."""

from __future__ import annotations

import time

import numpy as np
import pytest

from argos.server.frames import encode_frame, frame_stats
from tests.server.conftest import decode_frame, reference_stats

TS = "2026-11-01T21:04:05.123Z"


def _encode(pixels, **kw):
    args = dict(seq=7, exposure_s=2.5, timestamp=TS, source="simulator")
    args.update(kw)
    return encode_frame(pixels, **args)


@pytest.mark.parametrize("shape", [(1, 1), (3, 5), (120, 160), (1920, 1080), (7, 9, 3)])
def test_roundtrip_geometry_and_alignment(shape):
    rng = np.random.default_rng(1)
    pixels = rng.integers(0, 65536, size=shape, dtype=np.uint16)
    header, decoded = decode_frame(_encode(pixels))
    assert decoded.shape == pixels.shape
    np.testing.assert_array_equal(decoded, pixels)
    assert (header["height"], header["width"]) == shape[:2]
    assert header["channels"] == (shape[2] if len(shape) == 3 else 1)
    assert header["dtype"] == "uint16"
    assert header["pixel_offset"] % 8 == 0
    assert header["seq"] == 7 and header["exposure_s"] == 2.5
    assert header["timestamp"] == TS and header["source"] == "simulator"


@pytest.mark.parametrize("seq", [0, 9, 10, 99_999, 10**12])
def test_offset_is_aligned_whatever_the_header_length(seq):
    # Header length changes with the number of digits; alignment must hold.
    _, _ = decode_frame(_encode(np.zeros((2, 3), np.uint16), seq=seq))


def test_row_zero_is_first_in_the_payload():
    pixels = np.zeros((4, 3), np.uint16)
    pixels[0, :] = 111  # top row
    pixels[-1, 0] = 999
    header, decoded = decode_frame(_encode(pixels))
    assert decoded[0].tolist() == [111, 111, 111]
    data = _encode(pixels)
    first = np.frombuffer(data, "<u2", count=3, offset=header["pixel_offset"])
    assert first.tolist() == [111, 111, 111]


def test_rgb_channels_are_interleaved():
    pixels = np.zeros((2, 2, 3), np.uint16)
    pixels[..., 0], pixels[..., 1], pixels[..., 2] = 1, 2, 3
    header, _ = decode_frame(_encode(pixels))
    data = _encode(pixels)
    raw = np.frombuffer(data, "<u2", count=12, offset=header["pixel_offset"])
    assert raw.tolist() == [1, 2, 3] * 4


@pytest.mark.parametrize("n", [1, 2, 3, 10, 11, 1001, 4096])
def test_stats_match_numpy_exactly(n):
    rng = np.random.default_rng(n)
    pixels = rng.normal(2000, 40, n).clip(0, 65535).astype(np.uint16)
    pixels[: max(1, n // 50)] = 65535  # saturated tail
    assert frame_stats(pixels) == pytest.approx(reference_stats(pixels), rel=0, abs=1e-9)


def test_stats_on_even_count_take_middle_mean():
    pixels = np.array([1, 2, 3, 10], np.uint16)
    stats = frame_stats(pixels)
    assert stats["median"] == 2.5
    # |x - 2.5| = 1.5, 0.5, 0.5, 7.5 → median 1.0
    assert stats["mad"] == 1.0
    assert stats["min"] == 1 and stats["max"] == 10 and stats["mean"] == 4.0


def test_header_stats_describe_the_payload():
    rng = np.random.default_rng(3)
    pixels = rng.integers(1000, 3000, size=(50, 40), dtype=np.uint16)
    header, decoded = decode_frame(_encode(pixels))
    assert header["stats"] == pytest.approx(reference_stats(decoded), abs=1e-9)


def test_rejects_non_uint16_and_bad_shapes():
    with pytest.raises(ValueError):
        _encode(np.zeros((2, 2), np.float32))
    with pytest.raises(ValueError):
        _encode(np.zeros((2, 2, 2), np.uint16))
    with pytest.raises(ValueError):
        _encode(np.zeros(5, np.uint16))


def test_big_endian_input_is_sent_little_endian():
    pixels = np.arange(6, dtype=">u2").reshape(2, 3)
    with pytest.raises(ValueError):
        _encode(pixels)  # dtype check is strict: callers convert first
    _, decoded = decode_frame(_encode(pixels.astype(np.uint16)))
    assert decoded.tolist() == [[0, 1, 2], [3, 4, 5]]


def test_full_frame_encoding_is_fast():
    rng = np.random.default_rng(0)
    pixels = rng.normal(2000, 40, (1920, 1080)).clip(0, 65535).astype(np.uint16)
    _encode(pixels)  # warm-up
    t0 = time.perf_counter()
    for _ in range(5):
        _encode(pixels)
    per_frame = (time.perf_counter() - t0) / 5
    # Budget ~40 ms; measured ~4 ms on an M-series Mac. Generous bound for CI.
    assert per_frame < 0.040, f"encode took {per_frame * 1e3:.1f} ms"
