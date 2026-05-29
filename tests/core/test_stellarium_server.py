"""End-to-end test of the asyncio Stellarium server.

Exercises the path Stellarium -> StellariumServer -> on_goto callback,
then StellariumServer.set_position() -> client. No Qt involved.
"""

from __future__ import annotations

import asyncio
import math
import socket

import pytest

from seercontrol.core.stellarium.protocol import (
    _GOTO_SIZE,
    _GOTO_STRUCT,
    _HEADER_STRUCT,
    _POS_SIZE,
    _POS_STRUCT,
    MSG_TYPE_POSITION,
)
from seercontrol.core.stellarium.server import StellariumServer


def _free_port() -> int:
    """Pick a free TCP port on localhost so concurrent test runs don't clash."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _build_goto(ra_hours: float, dec_degrees: float) -> bytes:
    rad_to_int = 0x80000000 / math.pi
    ra_rad = (ra_hours % 24.0) * math.pi / 12.0
    dec_rad = math.radians(dec_degrees)
    ra_int = int(round(ra_rad * rad_to_int)) & 0xFFFFFFFF
    dec_int = int(round(dec_rad * rad_to_int))
    body = _GOTO_STRUCT.pack(0, ra_int, dec_int)
    return _HEADER_STRUCT.pack(_GOTO_SIZE, MSG_TYPE_POSITION) + body


def test_server_delivers_goto_to_callback_and_pushes_position() -> None:
    port = _free_port()
    received: list[tuple[float, float]] = []
    counts: list[int] = []

    async def scenario() -> tuple[float, float, int]:
        srv = StellariumServer(
            host="127.0.0.1",
            port=port,
            on_goto=lambda ra, dec: received.append((ra, dec)),
            on_client_count=counts.append,
            push_interval_s=0.15,
        )
        await srv.start()
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            try:
                writer.write(_build_goto(5.5900, -5.3900))
                await writer.drain()
                srv.set_position(7.0, 12.0, slewing=False)
                data = await asyncio.wait_for(reader.readexactly(_POS_SIZE), timeout=2.0)
            finally:
                writer.close()
                try:
                    await writer.wait_closed()
                except Exception:
                    pass
        finally:
            await srv.stop()
        _ts, ra_int, dec_int, status = _POS_STRUCT.unpack_from(data, 4)
        rad_to_int = 0x80000000 / math.pi
        ra_h = (ra_int / rad_to_int) * 12.0 / math.pi
        dec_d = math.degrees(dec_int / rad_to_int)
        return ra_h, dec_d, status

    ra_h, dec_d, status = asyncio.run(scenario())

    assert len(received) == 1
    assert received[0][0] == pytest.approx(5.59, abs=1e-4)
    assert received[0][1] == pytest.approx(-5.39, abs=1e-4)
    assert ra_h == pytest.approx(7.0, abs=1e-4)
    assert dec_d == pytest.approx(12.0, abs=1e-4)
    assert status == 0
    assert any(c >= 1 for c in counts)
