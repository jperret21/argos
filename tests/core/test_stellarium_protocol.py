"""Stellarium Telescope Protocol v1.0 — binary roundtrip + framing."""

from __future__ import annotations

import math
import pytest

from argos.core.stellarium.protocol import (
    _GOTO_SIZE,
    _GOTO_STRUCT,
    _HEADER_STRUCT,
    _POS_SIZE,
    MSG_TYPE_POSITION,
    decode_goto,
    encode_position,
    find_next_message,
)


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #

def _build_goto(ra_hours: float, dec_degrees: float, ts: int = 1700000000_000000) -> bytes:
    """Re-implement the client-side packing so the test is independent of the
    server-side encoder."""
    rad_to_int = 0x80000000 / math.pi
    ra_rad = (ra_hours % 24.0) * math.pi / 12.0
    dec_rad = math.radians(dec_degrees)
    ra_int = int(round(ra_rad * rad_to_int)) & 0xFFFFFFFF
    dec_int = int(round(dec_rad * rad_to_int))
    body = _GOTO_STRUCT.pack(ts, ra_int, dec_int)
    return _HEADER_STRUCT.pack(_GOTO_SIZE, MSG_TYPE_POSITION) + body


# --------------------------------------------------------------------------- #
# decode_goto                                                                  #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "ra,dec",
    [
        (0.0, 0.0),
        (5.5900, -5.3900),
        (12.0, 89.5),
        (12.0, -89.5),
        (18.6156, 38.78),
        (23.9999, 0.0),
    ],
)
def test_decode_goto_roundtrip(ra: float, dec: float) -> None:
    pkt = _build_goto(ra, dec)
    msg = decode_goto(pkt)
    assert msg is not None
    assert msg.ra_hours == pytest.approx(ra, abs=1e-4)
    assert msg.dec_degrees == pytest.approx(dec, abs=1e-4)


def test_decode_goto_rejects_wrong_length() -> None:
    bad = b"\x00" * (_GOTO_SIZE - 1)
    assert decode_goto(bad) is None


def test_decode_goto_rejects_wrong_type() -> None:
    bad = _HEADER_STRUCT.pack(_GOTO_SIZE, 42) + b"\x00" * 16
    assert decode_goto(bad) is None


# --------------------------------------------------------------------------- #
# encode_position                                                              #
# --------------------------------------------------------------------------- #

def test_encode_position_has_expected_size_and_type() -> None:
    pkt = encode_position(5.59, -5.39, status=0)
    assert len(pkt) == _POS_SIZE  # 24 bytes
    length, msg_type = _HEADER_STRUCT.unpack_from(pkt, 0)
    assert length == _POS_SIZE
    assert msg_type == MSG_TYPE_POSITION


def test_encode_position_roundtrip_via_decoding() -> None:
    """Encode a position packet, then re-decode it manually to verify the
    on-wire integers map back to the same RA/Dec."""
    pkt = encode_position(18.6156, 38.78, status=0)
    # Position packet layout: header (4) + time (8) + ra (4) + dec (4) + status (4)
    ra_int = int.from_bytes(pkt[12:16], "little")
    dec_int = int.from_bytes(pkt[16:20], "little", signed=True)
    rad_to_int = 0x80000000 / math.pi
    ra_h = (ra_int / rad_to_int) * 12.0 / math.pi
    dec_d = math.degrees(dec_int / rad_to_int)
    assert ra_h == pytest.approx(18.6156, abs=1e-4)
    assert dec_d == pytest.approx(38.78, abs=1e-4)


# --------------------------------------------------------------------------- #
# Streaming / framing                                                          #
# --------------------------------------------------------------------------- #

def test_find_next_message_returns_zero_on_incomplete_buffer() -> None:
    assert find_next_message(b"") == 0
    assert find_next_message(b"\x00\x00") == 0  # only header bytes
    # Header says 20 bytes, only 10 present
    partial = _HEADER_STRUCT.pack(_GOTO_SIZE, MSG_TYPE_POSITION) + b"\x00" * 6
    assert find_next_message(partial) == 0


def test_two_concatenated_messages_decode_in_sequence() -> None:
    """A real TCP stream often delivers multiple frames in one chunk —
    ``find_next_message`` must let the reader peel them off one at a time."""
    pkt1 = _build_goto(5.59, -5.39)
    pkt2 = _build_goto(18.6156, 38.78)
    buf = pkt1 + pkt2

    n = find_next_message(buf)
    assert n == _GOTO_SIZE
    first = decode_goto(buf[:n])
    assert first is not None and first.ra_hours == pytest.approx(5.59, abs=1e-4)

    rest = buf[n:]
    n2 = find_next_message(rest)
    assert n2 == _GOTO_SIZE
    second = decode_goto(rest[:n2])
    assert second is not None and second.ra_hours == pytest.approx(18.6156, abs=1e-4)
