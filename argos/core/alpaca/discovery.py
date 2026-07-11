"""ASCOM Alpaca discovery — UDP broadcast plus TCP fallbacks.

Layered strategy (``discover_all``), designed for field networks where the
UDP broadcast often fails (phone hotspots block it, some APs isolate clients):

1. UDP broadcast on port 32227 (the standard Alpaca discovery protocol).
2. Direct HTTP probes of known candidates — the last-used host and the
   Seestar's fixed address in AP mode.
3. A TCP sweep of the local /24 subnet, confirming hits against the Alpaca
   management endpoint.

This module is pure Python with no Qt dependency.
It is designed to be called from a QThread worker (DiscoveryWorker).
"""

from __future__ import annotations

import json
import logging
import socket
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import requests

logger = logging.getLogger(__name__)

DISCOVERY_PORT = 32227
DISCOVERY_MESSAGE = b"alpacadiscovery1"
DISCOVERY_TIMEOUT = 8.0  # seconds

#: The Seestar's own address when it runs its access point (AP mode) —
#: the out-of-the-box field configuration, no home router involved.
SEESTAR_AP_HOST = "10.0.0.1"

PROBE_TIMEOUT = 2.0  # seconds, per direct HTTP probe
SCAN_CONNECT_TIMEOUT = 0.4  # seconds, per host during the subnet sweep
SCAN_WORKERS = 64


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


# --------------------------------------------------------------------------- #
# TCP fallbacks — for networks where the UDP broadcast never arrives           #
# --------------------------------------------------------------------------- #


def probe_alpaca(host: str, port: int, timeout: float = PROBE_TIMEOUT) -> bool:
    """True if ``host:port`` answers like an Alpaca server.

    Hits the management API (the one endpoint every Alpaca server must
    serve) rather than a bare TCP connect, so a random web server on the
    same port is not mistaken for the Seestar.
    """
    url = f"http://{host}:{port}/management/v1/configureddevices"
    try:
        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()
        resp.json()
        return True
    except (requests.RequestException, ValueError):
        return False


def local_ipv4() -> str | None:
    """Best-guess primary local IPv4, or None when no route exists.

    UDP connect() sends no packet — it only asks the OS which source
    address it would route through, so this works with no internet.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("198.51.100.1", 1))  # TEST-NET-2, never actually contacted
        return sock.getsockname()[0]
    except OSError:
        return None
    finally:
        sock.close()


def scan_subnet(port: int, timeout: float = SCAN_CONNECT_TIMEOUT) -> list[AlpacaDevice]:
    """Sweep the local /24 for an open Alpaca port, then confirm via HTTP.

    ~254 TCP connects across a thread pool finish in a couple of seconds;
    only hosts with the port open get the (slower) management probe.
    """
    local = local_ipv4()
    if local is None:
        logger.warning("Subnet scan skipped: no local IPv4 route")
        return []
    prefix = local.rsplit(".", 1)[0]
    hosts = [f"{prefix}.{i}" for i in range(1, 255) if f"{prefix}.{i}" != local]

    def port_open(host: str) -> bool:
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except OSError:
            return False

    logger.info("Scanning %s.0/24 for Alpaca port %d…", prefix, port)
    with ThreadPoolExecutor(max_workers=SCAN_WORKERS) as pool:
        open_hosts = [h for h, ok in zip(hosts, pool.map(port_open, hosts)) if ok]

    found = [AlpacaDevice(h, port) for h in open_hosts if probe_alpaca(h, port)]
    logger.info("Subnet scan: %d Alpaca server(s) found", len(found))
    return found


def discover_all(
    port: int,
    candidates: tuple[str, ...] = (),
    broadcast_timeout: float = DISCOVERY_TIMEOUT,
) -> list[AlpacaDevice]:
    """Layered discovery: UDP broadcast, then candidate probes, then /24 scan.

    Args:
        port: Alpaca HTTP port for the probe/scan fallbacks (the broadcast
              reply carries its own port).
        candidates: Hosts worth probing directly when the broadcast fails —
                    typically the last-used host and ``SEESTAR_AP_HOST``.
        broadcast_timeout: How long to wait for broadcast replies.

    Returns:
        Discovered devices, possibly empty. The first entry is the best pick.
    """
    devices = discover(timeout=broadcast_timeout)
    if devices:
        return devices

    seen: set[str] = set()
    for host in candidates:
        host = host.strip()
        if not host or host in seen:
            continue
        seen.add(host)
        logger.info("Broadcast silent — probing %s:%d directly…", host, port)
        if probe_alpaca(host, port):
            logger.info("Direct probe hit: %s:%d", host, port)
            return [AlpacaDevice(host, port)]

    return scan_subnet(port)
