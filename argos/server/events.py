"""Thread-safe pub/sub between device threads and the asyncio WebSocket senders.

Devices run on plain threads (an exposure blocks for seconds, an Alpaca call
blocks on HTTP); WebSocket clients live on the event loop. :class:`EventBus`
is the only crossing point: :meth:`EventBus.publish` and
:meth:`EventBus.publish_frame` may be called from any thread and hand over
with ``loop.call_soon_threadsafe`` — the loop thread alone touches the
subscriber sets and queues, so they need no lock.

Every per-client buffer is bounded, so a stalled browser can never grow the
server's memory:

- **events** — a FIFO, so a client that keeps up sees every transition
  (``connecting`` before ``connected``, ``exposing`` before ``idle``…).
  Past :data:`EVENT_BACKLOG` pending messages it is compacted: only the
  newest snapshot of each kind survives (``status``, ``camera``, ``mount``,
  ``devices``, ``network``, ``activity``, ``config``, and ``job:<id>`` per
  job), then the oldest log lines go. Snapshots are complete, so a lagging
  client loses history, never the current state.
- **frames** — one pending slot per client, latest-frame-wins: a slow
  client skips frames instead of queueing them.

Snapshots carry a sequence number assigned under the hub lock, in the same
order as the state changes. A subscriber drops any snapshot older than what
it already holds, which closes the one race left: the ``status`` a client
receives on connect is read directly, while an older event may still sit in
the loop's callback queue.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from collections import deque
from typing import Any

logger = logging.getLogger(__name__)

#: Snapshot event types a newer snapshot makes obsolete. A ``status`` carries
#: the camera, mount and devices records, so it covers those events too. Any
#: other kind (``network``, ``activity``, ``config``, ``job:<id>``…) covers
#: only itself; ``log`` is a stream and is never covered.
_COVERED_BY = {
    "status": ("status", "camera", "mount", "devices"),
    "camera": ("camera",),
    "mount": ("mount",),
    "devices": ("devices",),
}

#: Pending messages per client before the backlog is compacted.
EVENT_BACKLOG = 256


class EventSubscriber:
    """One ``/ws/events`` client's pending messages (loop thread only)."""

    def __init__(self, capacity: int = EVENT_BACKLOG) -> None:
        self._queue: deque[tuple[str, dict[str, Any]]] = deque()
        self._floor: dict[str, int] = {}
        self._capacity = max(4, int(capacity))  # room for one of each snapshot type
        self._wake = asyncio.Event()
        self.closed = False
        #: Messages discarded by compaction (diagnostics).
        self.dropped = 0

    def offer(self, kind: str, seq: int | None, payload: dict[str, Any]) -> None:
        if kind != "log" and seq is not None:
            if seq <= self._floor.get(kind, -1):
                return  # older than a snapshot this client already holds
            for covered in _COVERED_BY.get(kind, (kind,)):
                self._floor[covered] = max(self._floor.get(covered, -1), seq)
        self._queue.append((kind, payload))
        if len(self._queue) > self._capacity:
            self._compact()
        self._wake.set()

    def _compact(self) -> None:
        """Keep the newest snapshot of each type and as many recent logs as fit."""
        newest = {kind: i for i, (kind, _) in enumerate(self._queue) if kind != "log"}
        kept = [
            item for i, item in enumerate(self._queue) if item[0] == "log" or newest[item[0]] == i
        ]
        excess = len(kept) - self._capacity
        if excess > 0:
            logs = [i for i, item in enumerate(kept) if item[0] == "log"][:excess]
            drop = set(logs)
            kept = [item for i, item in enumerate(kept) if i not in drop]
        self.dropped += len(self._queue) - len(kept)
        self._queue = deque(kept)

    def close(self) -> None:
        self.closed = True
        self._wake.set()

    async def next_batch(self) -> list[dict[str, Any]]:
        """Wait for pending messages and take them all, in order; ``[]`` once closed."""
        while not self._queue:
            if self.closed:
                return []
            await self._wake.wait()
            self._wake.clear()
        batch = [payload for _, payload in self._queue]
        self._queue.clear()
        return batch


class FrameSubscriber:
    """One ``/ws/frames`` client: a single latest-frame-wins slot (loop thread only)."""

    def __init__(self) -> None:
        self._pending: bytes | None = None
        self._wake = asyncio.Event()
        self.closed = False
        #: Frames overwritten before this client took them (diagnostics).
        self.skipped = 0

    def offer(self, frame: bytes) -> None:
        if self._pending is not None:
            self.skipped += 1
        self._pending = frame
        self._wake.set()

    def close(self) -> None:
        self.closed = True
        self._wake.set()

    async def next_frame(self) -> bytes | None:
        """Wait for the newest frame; ``None`` once closed."""
        while self._pending is None:
            if self.closed:
                return None
            await self._wake.wait()
            self._wake.clear()
        frame, self._pending = self._pending, None
        return frame


class EventBus:
    """Fan-out of events and encoded frames to every connected client."""

    def __init__(self) -> None:
        self._lock = threading.Lock()  # guards _loop for publisher threads
        self._loop: asyncio.AbstractEventLoop | None = None
        # Loop-thread state.
        self._events: set[EventSubscriber] = set()
        self._frames: set[FrameSubscriber] = set()
        self._latest_frame: bytes | None = None

    # -- lifecycle (loop thread) ------------------------------------------

    def attach(self, loop: asyncio.AbstractEventLoop) -> None:
        with self._lock:
            self._loop = loop

    def detach(self) -> None:
        """Stop accepting publications and release every waiting client."""
        with self._lock:
            self._loop = None
        for sub in (*self._events, *self._frames):
            sub.close()
        self._events.clear()
        self._frames.clear()

    # -- publishing (any thread) -----------------------------------------

    def publish(self, kind: str, seq: int | None, payload: dict[str, Any]) -> None:
        """Queue one JSON event (a snapshot kind with its *seq*, or ``log``)."""
        self._call_soon(self._dispatch_event, kind, seq, payload)

    def publish_frame(self, frame: bytes) -> None:
        """Queue one encoded binary frame for every frame client."""
        self._call_soon(self._dispatch_frame, frame)

    def _call_soon(self, callback, *args) -> None:
        with self._lock:
            loop = self._loop
        if loop is None:
            return  # not serving (startup/shutdown): nobody to tell
        try:
            loop.call_soon_threadsafe(callback, *args)
        except RuntimeError:
            pass  # loop closed under us during shutdown

    # -- dispatch (loop thread) ------------------------------------------

    def _dispatch_event(self, kind: str, seq: int | None, payload: dict[str, Any]) -> None:
        for sub in self._events:
            sub.offer(kind, seq, payload)

    def _dispatch_frame(self, frame: bytes) -> None:
        self._latest_frame = frame
        for sub in self._frames:
            sub.offer(frame)

    # -- subscriptions (loop thread) -------------------------------------

    def subscribe_events(
        self,
        initial: tuple[int, dict[str, Any]] | None = None,
        history: list[dict[str, Any]] | None = None,
        snapshots: list[tuple[str, int, dict[str, Any]]] | None = None,
    ) -> EventSubscriber:
        """Register a client, pre-loaded with a ``status`` snapshot, the other
        current *snapshots* (``network``, ``activity``) and past log lines.

        A log line published just before this call can arrive twice (once from
        *history*, once from the loop's queue); the front-end drops the lines
        whose ``seq`` it already holds.
        """
        sub = EventSubscriber()
        if initial is not None:
            seq, payload = initial
            sub.offer("status", seq, payload)
        for kind, seq, payload in snapshots or ():
            sub.offer(kind, seq, payload)
        for payload in history or ():
            sub.offer("log", None, payload)
        self._events.add(sub)
        return sub

    def unsubscribe_events(self, sub: EventSubscriber) -> None:
        self._events.discard(sub)
        sub.close()

    def subscribe_frames(self) -> FrameSubscriber:
        """Register a client, pre-loaded with the most recent frame if any."""
        sub = FrameSubscriber()
        if self._latest_frame is not None:
            sub.offer(self._latest_frame)
        self._frames.add(sub)
        return sub

    def unsubscribe_frames(self, sub: FrameSubscriber) -> None:
        self._frames.discard(sub)
        sub.close()

    @property
    def client_count(self) -> int:
        return len(self._events) + len(self._frames)

    @property
    def frame_client_count(self) -> int:
        return len(self._frames)
