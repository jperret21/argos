"""The observer log: a bounded ring of structured lines (API 2, row A2).

Every line the server shows the observer goes through :class:`LogBook`:
it numbers the line (``seq``, also ``id``), stamps it in UTC and keeps the
last :data:`LOG_RING` lines, so a page that reloads can replay the night
with ``GET /api/logs?after=<seq>`` instead of losing it (v1 kept 200).

Levels follow the Qt activity log (148 ``log_message.emit`` sites use CMD,
INFO, OK, WARN and ERROR) plus ``debug``, which the server records only
while ``ui.log_level`` is DEBUG.
"""

from __future__ import annotations

import threading
from collections import deque
from typing import Any, Literal

from argos.server.state import utc_iso

LogLevel = Literal["debug", "cmd", "info", "ok", "warning", "error"]

#: Severity order, for the ``level`` filter of ``GET /api/logs``.
LEVEL_ORDER: dict[str, int] = {
    "debug": 0,
    "cmd": 1,
    "info": 2,
    "ok": 3,
    "warning": 4,
    "error": 5,
}

#: Lines kept for ``GET /api/logs``.
LOG_RING = 5000
#: Lines replayed to a ``/ws/events`` client right after its first ``status``.
LOG_HISTORY = 200


class LogBook:
    """Thread-safe ring of log entries with a monotonic sequence number."""

    def __init__(self, capacity: int = LOG_RING) -> None:
        self._lines: deque[dict[str, Any]] = deque(maxlen=max(1, int(capacity)))
        self._lock = threading.Lock()
        self._seq = 0

    def append(self, level: str, message: str, source: str, topic: str) -> dict[str, Any]:
        """Record one line and return its ``log`` event payload."""
        with self._lock:
            self._seq += 1
            entry = {
                "type": "log",
                "id": self._seq,
                "seq": self._seq,
                "level": level,
                "source": source,
                "topic": topic,
                "message": message,
                "t": utc_iso(),
            }
            self._lines.append(entry)
            return entry

    def recent(self, count: int = LOG_HISTORY) -> list[dict[str, Any]]:
        """The newest *count* lines, oldest first."""
        with self._lock:
            if count >= len(self._lines):
                return list(self._lines)
            return list(self._lines)[-count:]

    def page(self, after: int = 0, limit: int = 1000, level: str | None = None) -> dict[str, Any]:
        """Lines with ``seq > after``, oldest first (``GET /api/logs``)."""
        floor = LEVEL_ORDER.get(level, 0) if level else 0
        with self._lock:
            lines = list(self._lines)
            last = self._seq or None
        first = lines[0]["seq"] if lines else None
        entries = [
            line for line in lines if line["seq"] > after and LEVEL_ORDER[line["level"]] >= floor
        ][: max(0, int(limit))]
        # Lines after `after` were dropped when the oldest kept one is newer
        # than after + 1 (the ring rolled past them).
        truncated = first is not None and first > after + 1 and after < (last or 0)
        return {"entries": entries, "first_seq": first, "last_seq": last, "truncated": truncated}
