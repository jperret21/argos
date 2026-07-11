"""QThread worker for quiet background network checks.

Every cycle it answers two questions the field observer actually has:
is the Seestar reachable, and is there internet for the AAVSO catalogs?
Both are plain TCP connects with short timeouts — no HTTP, no payload —
so a cycle costs a few packets at most.

The Seestar check targets the configured Alpaca host/port (re-read every
cycle, so a profile switch is picked up without a restart). The internet
check connects to well-known public resolvers (Cloudflare, then Google).

Usage:
    monitor = NetworkMonitor(config)
    monitor.state_changed.connect(status_bar.set_network)
    monitor.start()
    # ...
    monitor.stop()
    monitor.wait()
"""

from __future__ import annotations

import logging
import socket

from PyQt6.QtCore import QThread, pyqtSignal

from argos.core.config import Config

logger = logging.getLogger(__name__)

CHECK_INTERVAL_MS = 10_000
CONNECT_TIMEOUT = 1.5  # seconds per TCP attempt

# (host, port) pairs tried in order for the internet check — TCP/53 to
# public DNS resolvers, the least likely thing a hotspot would block.
_INTERNET_TARGETS = (("1.1.1.1", 53), ("8.8.8.8", 53))


def _tcp_reachable(host: str, port: int, timeout: float = CONNECT_TIMEOUT) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


class NetworkMonitor(QThread):
    """Periodically checks Seestar + internet reachability.

    Signals:
        state_changed: (seestar_ok: bool | None, internet_ok: bool).
                       ``seestar_ok`` is None while no host is configured.
    """

    state_changed = pyqtSignal(object, bool)  # bool | None, bool

    def __init__(self, config: Config, parent=None) -> None:
        super().__init__(parent)
        self._config = config
        self._running = False

    def run(self) -> None:
        self._running = True
        logger.info("NetworkMonitor started (interval=%dms)", CHECK_INTERVAL_MS)
        while self._running:
            self._check()
            # Sleep in short slices so stop() is honoured promptly at shutdown.
            waited = 0
            while self._running and waited < CHECK_INTERVAL_MS:
                self.msleep(250)
                waited += 250
        logger.info("NetworkMonitor stopped")

    def stop(self) -> None:
        """Request the loop to stop. Call wait() after to join the thread."""
        self._running = False

    def _check(self) -> None:
        host = self._config.alpaca_host
        port = self._config.alpaca_port
        seestar_ok: bool | None = _tcp_reachable(host, port) if host else None
        internet_ok = any(_tcp_reachable(h, p) for h, p in _INTERNET_TARGETS)
        self.state_changed.emit(seestar_ok, internet_ok)
