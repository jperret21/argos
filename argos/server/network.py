"""Network reachability for the status bar and the Link card (row A18).

Qt-free port of ``NetworkMonitor`` (``argos/workers/network_monitor.py:40-84``,
a ``QThread``), with the owner's decision Q-G13 applied:

- the configured Seestar address (``alpaca.host`` / ``alpaca.port``, re-read
  on every cycle as ``network_monitor.py:80-82``) is probed with one TCP
  connect every :data:`CHECK_INTERVAL_S`, and at once after the address
  changes; ``seestar`` is ``None`` while no address is configured, which the
  UI shows as "not configured" (fixes 01 P22);
- the internet is **not** probed in the background (Qt contacted 1.1.1.1 and
  8.8.8.8 every 10 s with no opt-in): :meth:`NetworkMonitor.check` with
  ``internet=True`` does it on demand, with the Qt targets and timeout;
  ``internet`` stays ``None`` until then.

Every probe publishes a ``network`` snapshot with its time, so the Link
card can say "checked 4 s ago".
"""

from __future__ import annotations

import logging
import socket
import threading
from typing import Any, Callable

from argos.server.state import utc_iso

logger = logging.getLogger(__name__)

#: network_monitor.py:32 (10 000 ms).
CHECK_INTERVAL_S = 10.0
#: network_monitor.py:33.
CONNECT_TIMEOUT_S = 1.5
#: network_monitor.py:37 — TCP/53 on public resolvers, tried in order.
INTERNET_TARGETS: tuple[tuple[str, int], ...] = (("1.1.1.1", 53), ("8.8.8.8", 53))

Probe = Callable[[str, int, float], bool]


def tcp_reachable(host: str, port: int, timeout: float = CONNECT_TIMEOUT_S) -> bool:
    """network_monitor.py:40-45."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


class NetworkMonitor:
    """Periodic Seestar probe plus the on-demand internet check; thread-safe.

    Args:
        address: Returns the configured ``(host, port)``; host ``""`` = none.
        publish: Called with the ``network`` snapshot after every probe.
        interval_s: Probe period.
        timeout_s: TCP connect timeout of one probe.
        probe: The reachability test (tests inject a fake).
        internet_targets: Hosts tried, in order, by the internet check.
    """

    def __init__(
        self,
        address: Callable[[], tuple[str, int]],
        publish: Callable[[dict[str, Any]], None] | None = None,
        *,
        interval_s: float = CHECK_INTERVAL_S,
        timeout_s: float = CONNECT_TIMEOUT_S,
        probe: Probe = tcp_reachable,
        internet_targets: tuple[tuple[str, int], ...] = INTERNET_TARGETS,
    ) -> None:
        self._address = address
        self._publish = publish
        self._interval = max(0.05, float(interval_s))
        self._timeout = float(timeout_s)
        self._probe = probe
        self._internet_targets = internet_targets
        self._state_lock = threading.Lock()
        self._check_lock = threading.Lock()  # one probe at a time, in order
        self._state: dict[str, Any] = {
            "seestar": None,
            "internet": None,
            "host": None,
            "port": None,
            "t": None,
            "internet_t": None,
        }
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None

    def snapshot(self) -> dict[str, Any]:
        with self._state_lock:
            return dict(self._state)

    # -- lifecycle -------------------------------------------------------------

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="argos-network", daemon=True)
        self._thread.start()

    def stop(self, timeout_s: float = 3.0) -> None:
        self._stop.set()
        self._wake.set()
        thread, self._thread = self._thread, None
        if thread is not None:
            thread.join(timeout_s)

    def wake(self) -> None:
        """Probe again now (the configured address changed)."""
        self._wake.set()

    def _run(self) -> None:
        logger.info("Network monitor started (every %g s, Seestar only)", self._interval)
        while not self._stop.is_set():
            try:
                self.check(internet=False)
            except Exception:
                logger.exception("Network probe failed")
            self._wake.wait(self._interval)
            self._wake.clear()
        logger.info("Network monitor stopped")

    # -- probes ----------------------------------------------------------------

    def check(self, internet: bool = False) -> dict[str, Any]:
        """Probe the Seestar (and the internet if asked); publish and return the state."""
        with self._check_lock:
            host, port = self._address()
            host = (host or "").strip()
            seestar = self._probe(host, int(port), self._timeout) if host else None
            changes: dict[str, Any] = {
                "seestar": seestar,
                "host": host or None,
                "port": int(port) if host else None,
                "t": utc_iso(),
            }
            if internet:
                reachable = any(self._probe(h, p, self._timeout) for h, p in self._internet_targets)
                changes.update(internet=reachable, internet_t=utc_iso())
            with self._state_lock:
                previous = dict(self._state)
                self._state.update(changes)
                state = dict(self._state)
            if previous["seestar"] != state["seestar"] or previous["internet"] != state["internet"]:
                logger.info(
                    "Network: Seestar %s, internet %s",
                    _word(state["seestar"]),
                    _word(state["internet"]),
                )
            if self._publish is not None:
                self._publish(state)
            return state


def _word(value: bool | None) -> str:
    return "not configured/not checked" if value is None else ("up" if value else "down")
