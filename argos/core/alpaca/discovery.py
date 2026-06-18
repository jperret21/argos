"""ASCOM Alpaca UDP discovery.

Sends a broadcast on port 32227 and collects responses from Alpaca servers
on the local network. Each responding device returns its HTTP port.

This module is pure Python with no Qt dependency.
It is designed to be called from a QThread worker (DiscoveryWorker).
"""

from __future__ import annotations

import json
import logging
import socket
from dataclasses import dataclass

logger = logging.getLogger(__name__)

DISCOVERY_PORT = 32227
DISCOVERY_MESSAGE = b"alpacadiscovery1"
DISCOVERY_TIMEOUT = 8.0  # seconds


@dataclass(frozen=True)
class AlpacaDevice:
    """A discovered Alpaca server on the local network."""

    host: str
    port: int

    def __str__(self) -> str:
        return f"{self.host}:{self.port}"


def discover(timeout: float = DISCOVERY_TIMEOUT) -> list[AlpacaDevice]:
    """Broadcast a discovery packet and return all responding Alpaca devices.

    Args:
        timeout: How long to wait for responses (seconds).

    Returns:
        List of discovered AlpacaDevice instances (may be empty).
    """
    results: list[AlpacaDevice] = []
    seen: set[tuple[str, int]] = set()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.settimeout(timeout)

    try:
        sock.bind(("", 0))
        sock.sendto(DISCOVERY_MESSAGE, ("255.255.255.255", DISCOVERY_PORT))
        logger.info("Discovery broadcast sent on port %d, waiting %.1fs…", DISCOVERY_PORT, timeout)

        while True:
            try:
                data, addr = sock.recvfrom(1024)
                host = addr[0]

                payload = json.loads(data.decode("utf-8"))
                port = int(payload.get("AlpacaPort", 80))

                key = (host, port)
                if key not in seen:
                    seen.add(key)
                    device = AlpacaDevice(host=host, port=port)
                    results.append(device)
                    logger.info("Discovered: %s", device)

            except socket.timeout:
                break
            except (json.JSONDecodeError, ValueError) as exc:
                logger.warning("Ignoring malformed discovery response from %s: %s", addr, exc)
            except Exception as exc:
                logger.warning("Unexpected error during discovery: %s", exc)

    except OSError as exc:
        logger.error("Failed to open discovery socket: %s", exc)
    finally:
        sock.close()

    logger.info("Discovery complete: %d device(s) found", len(results))
    return results
