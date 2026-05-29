"""Stellarium Telescope Protocol v1.0 — binary message codec.

Wire format (little-endian, all messages share a 4-byte header):

    LENGTH (uint16)   total message length including this header
    TYPE   (uint16)   message type

MessageType 0 in either direction carries a J2000 RA/Dec pointing:

    Client -> Server  (Stellarium asks the telescope to slew)
        TIME (uint64)   microseconds since Unix epoch (informational)
        RA   (uint32)   ra_rad * 0x80000000 / pi     mod 2**32
        DEC  (int32)    dec_rad * 0x80000000 / pi    (signed)
        Total: 20 bytes

    Server -> Client  (telescope reports current pointing, ~1 Hz)
        TIME   (uint64)
        RA     (uint32)
        DEC    (int32)
        STATUS (uint32)  0 = OK, non-zero = error code (driver-specific)
        Total: 24 bytes

The RA encoding maps 0..2*pi radians (i.e. 0..24 hours) onto the full
uint32 range, so wrap-around is implicit. Dec uses a signed int32 mapping
-pi/2..+pi/2 onto -2**31..+2**31 (full Dec range fits in the lower half).

Reference: Stellarium docs/telescope_server.html and the libnova
TelescopeServer implementation.
"""

from __future__ import annotations

import math
import struct
import time
from dataclasses import dataclass

# Header common to all messages — uint16 length, uint16 type
_HEADER_STRUCT = struct.Struct("<HH")
_HEADER_SIZE = _HEADER_STRUCT.size  # 4 bytes

# MessageType 0 client -> server: time uint64, RA uint32, Dec int32
_GOTO_STRUCT = struct.Struct("<QIi")
_GOTO_SIZE = _HEADER_SIZE + _GOTO_STRUCT.size  # 20 bytes

# MessageType 0 server -> client: time uint64, RA uint32, Dec int32, status uint32
_POS_STRUCT = struct.Struct("<QIiI")
_POS_SIZE = _HEADER_SIZE + _POS_STRUCT.size  # 24 bytes

MSG_TYPE_POSITION = 0

# Scaling constant: 0x80000000 / pi — what one radian becomes in the wire ints.
_RAD_TO_INT = 0x80000000 / math.pi


@dataclass(frozen=True)
class GotoMessage:
    """A Stellarium "go to this RA/Dec" command in J2000."""

    ra_hours: float        # decimal hours, 0 <= ra < 24
    dec_degrees: float     # decimal degrees, -90 <= dec <= +90
    sent_time_us: int      # microseconds since epoch (informational only)


def encode_position(
    ra_hours: float,
    dec_degrees: float,
    status: int = 0,
    when_us: int | None = None,
) -> bytes:
    """Encode a 24-byte server -> client current-position message.

    Args:
        ra_hours:     Current RA in decimal hours (J2000).
        dec_degrees:  Current Dec in decimal degrees (J2000).
        status:       0 for OK, non-zero to signal a driver error.
        when_us:      Microseconds since epoch; defaults to ``time.time()``.
    """
    ra_int, dec_int = _radec_to_int(ra_hours, dec_degrees)
    ts = when_us if when_us is not None else int(time.time() * 1_000_000)
    body = _POS_STRUCT.pack(ts, ra_int, dec_int, status & 0xFFFFFFFF)
    return _HEADER_STRUCT.pack(_POS_SIZE, MSG_TYPE_POSITION) + body


def decode_goto(buf: bytes) -> GotoMessage | None:
    """Decode a 20-byte client -> server slew request.

    Returns ``None`` if the buffer is not a valid MessageType 0 frame.
    """
    if len(buf) < _GOTO_SIZE:
        return None
    length, msg_type = _HEADER_STRUCT.unpack_from(buf, 0)
    if length != _GOTO_SIZE or msg_type != MSG_TYPE_POSITION:
        return None
    ts, ra_int, dec_int = _GOTO_STRUCT.unpack_from(buf, _HEADER_SIZE)
    ra_h, dec_d = _int_to_radec(ra_int, dec_int)
    return GotoMessage(ra_hours=ra_h, dec_degrees=dec_d, sent_time_us=ts)


def find_next_message(buf: bytes) -> int:
    """Return the byte length of the leading message in ``buf``, or 0 if
    incomplete. Lets a buffered reader peel one frame at a time without
    knowing the message type in advance.
    """
    if len(buf) < _HEADER_SIZE:
        return 0
    length, _ = _HEADER_STRUCT.unpack_from(buf, 0)
    return length if len(buf) >= length else 0


# --------------------------------------------------------------------------- #
# Coord packing                                                                #
# --------------------------------------------------------------------------- #

def _radec_to_int(ra_hours: float, dec_degrees: float) -> tuple[int, int]:
    """Pack J2000 RA hours / Dec degrees into Stellarium wire integers."""
    ra_rad = (ra_hours % 24.0) * math.pi / 12.0
    dec_rad = max(-math.pi / 2, min(math.pi / 2, math.radians(dec_degrees)))
    ra_int = int(round(ra_rad * _RAD_TO_INT)) & 0xFFFFFFFF
    dec_int = int(round(dec_rad * _RAD_TO_INT))
    # Clamp into int32 range (defensive, the math is already in-range)
    if dec_int > 0x7FFFFFFF:
        dec_int = 0x7FFFFFFF
    elif dec_int < -0x80000000:
        dec_int = -0x80000000
    return ra_int, dec_int


def _int_to_radec(ra_int: int, dec_int: int) -> tuple[float, float]:
    """Unpack wire integers back to RA hours / Dec degrees (J2000)."""
    ra_rad = (ra_int & 0xFFFFFFFF) / _RAD_TO_INT
    dec_rad = dec_int / _RAD_TO_INT
    ra_hours = (ra_rad * 12.0 / math.pi) % 24.0
    dec_degrees = math.degrees(dec_rad)
    return ra_hours, dec_degrees
