"""Alpaca discovery as a cancellable job (row A16).

Qt-free port of ``DiscoveryWorker.run`` (``argos/workers/discovery_worker.py:50-64``)
and of the layered search it calls, ``argos.core.alpaca.discovery.discover_all``
(``discovery.py:167-199``): UDP broadcast, then direct HTTP probes of the
candidates (the last-used host and the profile's access-point address,
``device_session.py:203-205``), then a TCP sweep of the local /24. The core
functions block for their whole duration (8 s of broadcast, a pool sweep),
so the two long layers are re-implemented here with short waits that check
the job's cancel event (``discover`` ``discovery.py:48-97`` and
``scan_subnet`` ``discovery.py:138-164``); the HTTP probe, ``local_ipv4``
and the constants are the core's own.

Differences from the Qt app, by design (``web/spec/02`` §1.2 #4, §2.5):
every device found is returned (Qt kept the first), the probe layer tries
every candidate, each device's ``ServerName`` is read, and the whole search
can be cancelled.
"""

from __future__ import annotations

import json
import logging
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Callable

import requests

from argos.core.alpaca import discovery as core
from argos.server.jobs import JobCancelled, JobContext

logger = logging.getLogger(__name__)

#: How often a blocking wait looks at the cancel event (s).
_SLICE_S = 0.25
#: Timeout of the ``ServerName`` read per device (s).
NAME_TIMEOUT_S = 1.0

Endpoint = tuple[str, int]


@dataclass(frozen=True)
class DiscoveryLayers:
    """The network operations of one search; tests replace them with fakes."""

    broadcast: Callable[[float, threading.Event], list[Endpoint]]
    probe: Callable[[str, int], bool]
    scan: Callable[[int, threading.Event], list[Endpoint]]
    name: Callable[[str, int], str | None]


def broadcast(timeout_s: float, cancel: threading.Event) -> list[Endpoint]:
    """Alpaca UDP discovery (port of ``discovery.py:48-97``), cancellable."""
    found: list[Endpoint] = []
    seen: set[Endpoint] = set()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(_SLICE_S)
        sock.bind(("", 0))
        sock.sendto(core.DISCOVERY_MESSAGE, ("255.255.255.255", core.DISCOVERY_PORT))
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline and not cancel.is_set():
            try:
                data, addr = sock.recvfrom(1024)
            except socket.timeout:
                continue
            try:
                port = int(json.loads(data.decode("utf-8")).get("AlpacaPort", 80))
            except (ValueError, AttributeError) as exc:
                logger.warning("Ignoring malformed discovery response from %s: %s", addr, exc)
                continue
            key = (addr[0], port)
            if key not in seen:
                seen.add(key)
                found.append(key)
    except OSError as exc:
        logger.error("Discovery broadcast failed: %s", exc)
    finally:
        sock.close()
    return found


def probe(host: str, port: int) -> bool:
    """The core's management-API probe (``discovery.py:105-119``, 2 s)."""
    return core.probe_alpaca(host, port)


def scan(port: int, cancel: threading.Event) -> list[Endpoint]:
    """TCP sweep of the local /24 (port of ``discovery.py:138-164``), cancellable."""
    local = core.local_ipv4()
    if local is None:
        logger.warning("Subnet scan skipped: no local IPv4 route")
        return []
    prefix = local.rsplit(".", 1)[0]
    hosts = [f"{prefix}.{i}" for i in range(1, 255) if f"{prefix}.{i}" != local]

    def port_open(host: str) -> bool:
        if cancel.is_set():
            return False
        try:
            with socket.create_connection((host, port), timeout=core.SCAN_CONNECT_TIMEOUT):
                return True
        except OSError:
            return False

    pool = ThreadPoolExecutor(max_workers=core.SCAN_WORKERS, thread_name_prefix="argos-scan")
    try:
        futures = [pool.submit(port_open, host) for host in hosts]
        while not all(f.done() for f in futures):
            if cancel.wait(0.05):
                return []
        open_hosts = [h for h, f in zip(hosts, futures) if f.result()]
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    found = []
    for host in open_hosts:
        finished, confirmed = _call_unless_cancelled(
            lambda h=host: core.probe_alpaca(h, port), cancel
        )
        if not finished:
            return found  # cancelled: the job ends at its next check
        if confirmed:
            found.append((host, port))
    return found


def server_name(host: str, port: int) -> str | None:
    """``ServerName`` from the Alpaca management API, or ``None``."""
    try:
        response = requests.get(
            f"http://{host}:{port}/management/v1/description", timeout=NAME_TIMEOUT_S
        )
        response.raise_for_status()
        value = response.json().get("Value") or {}
        name = value.get("ServerName") if isinstance(value, dict) else None
        return str(name).strip() or None if name else None
    except (requests.RequestException, ValueError, AttributeError):
        return None


DEFAULT_LAYERS = DiscoveryLayers(broadcast=broadcast, probe=probe, scan=scan, name=server_name)


def _call_unless_cancelled(fn: Callable[[], Any], cancel: threading.Event) -> tuple[bool, Any]:
    """Run a short blocking call on a helper thread; stop waiting on cancel.

    An HTTP probe cannot be interrupted; the search must not wait for it once
    the observer cancelled, so the call finishes (≤ 2 s) on its own thread
    and its answer is dropped. Returns ``(finished, value)``.
    """
    box: dict[str, Any] = {}
    done = threading.Event()

    def target() -> None:
        try:
            box["value"] = fn()
        except Exception as exc:  # the core probe swallows its own errors
            box["error"] = exc
        finally:
            done.set()

    threading.Thread(target=target, name="argos-discovery-call", daemon=True).start()
    while not done.wait(_SLICE_S / 5):
        if cancel.is_set():
            return False, None
    if "error" in box:
        raise box["error"]
    return True, box.get("value")


def _abandonable(fn: Callable[[], Any], cancel: threading.Event) -> Any:
    """:func:`_call_unless_cancelled` inside a job: a cancel ends the job."""
    finished, value = _call_unless_cancelled(fn, cancel)
    if not finished:
        raise JobCancelled()
    return value


def run_discovery(
    ctx: JobContext,
    *,
    port: int,
    candidates: tuple[str, ...],
    broadcast_timeout_s: float,
    layers: DiscoveryLayers = DEFAULT_LAYERS,
) -> dict[str, Any]:
    """The job body: layered search, stopping at the first layer with a result."""
    cancel = ctx.cancel_event
    searched: list[str] = []
    method: str | None = None
    endpoints: list[Endpoint] = []

    ctx.progress(0, 3, "broadcast", f"Listening for Alpaca replies ({broadcast_timeout_s:g} s)")
    searched.append("broadcast")
    endpoints = layers.broadcast(broadcast_timeout_s, cancel)
    ctx.check()
    if endpoints:
        method = "broadcast"
    else:
        ctx.progress(1, 3, "probe", "Broadcast silent — probing known addresses")
        searched.append("probe")
        seen: set[str] = set()
        for host in candidates:
            host = (host or "").strip()
            if not host or host in seen:
                continue
            seen.add(host)
            if _abandonable(lambda h=host: layers.probe(h, port), cancel):
                endpoints.append((host, port))
            ctx.check()
        if endpoints:
            method = "probe"
        else:
            ctx.progress(2, 3, "subnet", "Sweeping the local network")
            searched.append("subnet")
            endpoints = layers.scan(port, cancel)
            ctx.check()
            if endpoints:
                method = "subnet"
    ctx.progress(3, 3, "names", f"{len(endpoints)} found" if endpoints else "Nothing found")
    devices = []
    for host, device_port in endpoints:
        name = _abandonable(lambda h=host, p=device_port: layers.name(h, p), cancel)
        devices.append({"host": host, "port": device_port, "name": name})
    return {"devices": devices, "method": method, "searched": searched}
