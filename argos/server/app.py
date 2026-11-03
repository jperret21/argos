"""FastAPI application: routes, auth, CORS and the two WebSockets.

Routes are deliberately thin — validate, call one :class:`Hub` method, return
its dict. They are plain ``def`` functions, so FastAPI runs them in its
threadpool and a blocking device call never stalls the event loop that feeds
the WebSockets.
"""

from __future__ import annotations

import asyncio
import json
import logging
import platform
import threading
import time
from contextlib import asynccontextmanager
from typing import Annotated, Any, Awaitable, Callable, Literal

import anyio
from fastapi import APIRouter, Body, Depends, FastAPI, Query, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field, model_validator
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import Headers
from starlette.responses import FileResponse, JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send
from starlette.websockets import WebSocketDisconnect, WebSocketState

from argos import __version__
from argos.server import API_VERSION
from argos.server.auth import (
    ALLOWED_ORIGIN_REGEX,
    WS_CLOSE_FORBIDDEN_ORIGIN,
    WS_CLOSE_UNAUTHORIZED,
    TokenAuth,
    allowed_hosts,
    host_allowed,
    origin_allowed,
)
from argos.server.errors import ApiError, CatchAllMiddleware, error_body, install_error_handlers
from argos.server.events import EventBus
from argos.server import profiles as profile_records
from argos.server import runtime
from argos.server.hub import Hub
from argos.server.settings import Settings

logger = logging.getLogger(__name__)

#: Upper bound on one exposure (s). The Seestar driver's own ExposureMax is
#: lower; Alpaca rejects what it cannot do.
MAX_EXPOSURE_S = 3600.0

#: Concurrent /ws/frames clients. Each one can pin an encoded frame (4 MB for
#: a Seestar frame) in its socket buffer; past this, a newcomer is closed
#: with 1013 (try again later).
MAX_FRAME_CLIENTS = 8


# ---------------------------------------------------------------------------
# Request bodies — strict: no string→number coercion, no unknown fields.
# ---------------------------------------------------------------------------


class _Body(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


class ConnectBody(_Body):
    mode: Literal["simulator", "alpaca"]
    host: str | None = Field(default=None, min_length=1, max_length=253)
    port: int | None = Field(default=None, ge=1, le=65535)

    @model_validator(mode="after")
    def _alpaca_needs_address(self) -> "ConnectBody":
        if self.mode == "alpaca" and (self.host is None or self.port is None):
            raise ValueError("alpaca mode needs host and port")
        return self


class ExposureBody(_Body):
    exposure_s: float = Field(gt=0.0, le=MAX_EXPOSURE_S)
    gain: int = Field(ge=0, le=1000)


class OpenFitsBody(_Body):
    path: str = Field(min_length=1, max_length=4096)


class GotoBody(_Body):
    ra_hours: float = Field(ge=0.0, le=24.0)
    dec_deg: float = Field(ge=-90.0, le=90.0)


class TrackingBody(_Body):
    enabled: bool


class DeviceConnectBody(_Body):
    """API 2: one device or all of them; the address defaults to the config's."""

    mode: Literal["simulator", "alpaca"] = "alpaca"
    host: str | None = Field(default=None, min_length=1, max_length=253)
    port: int | None = Field(default=None, ge=1, le=65535)


class DiscoveryBody(_Body):
    port: int | None = Field(default=None, ge=1, le=65535)
    candidates: list[Annotated[str, Field(min_length=1, max_length=253)]] | None = Field(
        default=None, max_length=8
    )
    broadcast_timeout_s: float | None = Field(default=None, ge=0.5, le=30.0)


class ProfileBody(_Body):
    key: str = Field(min_length=1, max_length=40)


class NetworkCheckBody(_Body):
    internet: bool = False


class StellariumBody(_Body):
    """A19: both default to the config (``stellarium.host``, ``stellarium.port``)."""

    host: str | None = Field(default=None, min_length=1, max_length=253)
    port: int | None = Field(default=None, ge=1024, le=65535)


class SupportBundleBody(_Body):
    """A5: where to write the ZIP (``null`` = keep it for a download) and what goes in."""

    destination: str | None = Field(default=None, min_length=1, max_length=4096)
    include_session: bool = False
    session_dir: str | None = Field(default=None, min_length=1, max_length=4096)
    include_site: bool = False
    include_crash_reports: bool = True
    overwrite: bool = False


class SiteSearchBody(_Body):
    """A82: the free-form place query (an empty one is refused with the Qt text)."""

    query: str = Field(max_length=200)


#: Server-side software credited by ``/api/app/info`` (the front-end adds its own).
# fmt: off
CREDITS = (
    {"name": "Python", "use": "server runtime", "licence": "PSF-2.0",
     "url": "https://www.python.org"},
    {"name": "NumPy", "use": "image arrays", "licence": "BSD-3-Clause",
     "url": "https://numpy.org"},
    {"name": "Astropy", "use": "FITS, coordinates, time", "licence": "BSD-3-Clause",
     "url": "https://www.astropy.org"},
    {"name": "alpyca", "use": "ASCOM Alpaca client", "licence": "MIT",
     "url": "https://github.com/ASCOMInitiative/alpyca"},
    {"name": "Requests", "use": "HTTP client", "licence": "Apache-2.0",
     "url": "https://requests.readthedocs.io"},
    {"name": "FastAPI", "use": "HTTP API", "licence": "MIT",
     "url": "https://fastapi.tiangolo.com"},
    {"name": "Starlette", "use": "HTTP and WebSocket toolkit", "licence": "BSD-3-Clause",
     "url": "https://www.starlette.io"},
    {"name": "Uvicorn", "use": "HTTP server", "licence": "BSD-3-Clause",
     "url": "https://www.uvicorn.org"},
)
# fmt: on

PROJECT_URL = "https://github.com/jperret21/argos"
DOCS_URL = "https://perretjules.com/argos/"


def _log_topic(logger_name: str) -> str:
    """Topic of a bridged ``argos.core`` record, from its logger name."""
    if ".alpaca.camera" in logger_name:
        return "camera"
    if ".alpaca.telescope" in logger_name:
        return "mount"
    if ".alpaca.discovery" in logger_name:
        return "discovery"
    if ".alpaca" in logger_name or ".hardware" in logger_name:
        return "connection"
    return "app"


# ---------------------------------------------------------------------------
# Logging bridge: core library messages → /ws/events "log"
# ---------------------------------------------------------------------------

_BRIDGED_LOGGER = "argos.core"


#: A core message repeated within this window is forwarded once.
_BRIDGE_REPEAT_S = 60.0


class _LogBridge(logging.Handler):
    """Forward ``argos.core`` warnings and errors (Alpaca driver…) as log events.

    The hub's own messages are published directly by :meth:`Hub.log`; only the
    core library, which knows nothing about the server, comes through here.
    INFO stays in the server log: the core logs every exposure start and
    download, which in live view would flood the observer's log. A message
    repeated within :data:`_BRIDGE_REPEAT_S` (a driver warning on every
    frame) is forwarded once.
    """

    def __init__(self, hub: Hub) -> None:
        super().__init__(level=logging.WARNING)
        self._hub = hub
        self._recent: dict[str, float] = {}
        self._recent_lock = threading.Lock()

    def _first_in_window(self, message: str) -> bool:
        now = time.monotonic()
        with self._recent_lock:
            if len(self._recent) > 256:
                self._recent = {m: t for m, t in self._recent.items() if now - t < _BRIDGE_REPEAT_S}
            last = self._recent.get(message)
            if last is not None and now - last < _BRIDGE_REPEAT_S:
                return False
            self._recent[message] = now
            return True

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = record.getMessage()
            if not self._first_in_window(message):
                return
            level = "error" if record.levelno >= logging.ERROR else "warning"
            self._hub.publish_log(level, message, source="core", topic=_log_topic(record.name))
        except Exception:
            self.handleError(record)


# ---------------------------------------------------------------------------
# Host / Origin guard (DNS rebinding)
# ---------------------------------------------------------------------------


class _LocalGuard:
    """Refuse HTTP requests for a foreign ``Host`` or from a foreign ``Origin``.

    Outermost layer, so nothing behind it runs for such a request. CORS
    preflights (OPTIONS) are left to the CORS middleware, which refuses them
    itself; WebSockets are checked in :func:`_admit` to close with 4403.
    """

    def __init__(self, app: ASGIApp, hosts: frozenset[str] | None) -> None:
        self.app = app
        self.hosts = hosts

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            headers = Headers(scope=scope)
            refusal = None
            if not host_allowed(headers.get("host"), self.hosts):
                refusal = error_body("forbidden_host", "This server only answers on localhost")
            elif scope["method"] != "OPTIONS" and not origin_allowed(headers.get("origin")):
                refusal = error_body("forbidden_origin", "Requests from this origin are refused")
            if refusal is not None:
                await JSONResponse(refusal, status_code=403)(scope, receive, send)
                return
        await self.app(scope, receive, send)


# ---------------------------------------------------------------------------
# WebSocket plumbing
# ---------------------------------------------------------------------------


async def _admit(
    websocket: WebSocket, auth: TokenAuth, hosts: frozenset[str] | None = None
) -> bool:
    """Accept, then close with an application code if the client is not allowed.

    Closing *before* accepting would surface as a bare HTTP 403 on the
    handshake, which a browser reports as close code 1006 — the contract's
    4401 must be visible to the front-end, so the socket is accepted first.
    """
    await websocket.accept()
    if not host_allowed(websocket.headers.get("host"), hosts) or not origin_allowed(
        websocket.headers.get("origin")
    ):
        await websocket.close(code=WS_CLOSE_FORBIDDEN_ORIGIN, reason="forbidden origin")
        return False
    if not auth.check(websocket.query_params.get("token")):
        await websocket.close(code=WS_CLOSE_UNAUTHORIZED, reason="unauthorized")
        return False
    return True


async def _pump(websocket: WebSocket, send_next: Callable[[], Awaitable[bool]]) -> None:
    """Run *send_next* until it returns False or the client goes away.

    A second task drains the client side, which is how a disconnect is
    noticed while the sender waits for something to send. An anyio task
    group (Starlette's own concurrency layer) keeps cancellation clean when
    the server or the client ends the session first.
    """
    bus_closed = False

    async with anyio.create_task_group() as group:

        async def sender() -> None:
            nonlocal bus_closed
            try:
                while await send_next():
                    pass
                bus_closed = True
            except (WebSocketDisconnect, anyio.ClosedResourceError, RuntimeError, OSError):
                pass  # the client vanished mid-send
            group.cancel_scope.cancel()

        async def receiver() -> None:
            try:
                while (await websocket.receive())["type"] != "websocket.disconnect":
                    pass
            except (WebSocketDisconnect, anyio.ClosedResourceError, RuntimeError, OSError):
                pass
            group.cancel_scope.cancel()

        group.start_soon(sender)
        group.start_soon(receiver)

    if bus_closed and websocket.application_state == WebSocketState.CONNECTED:
        # The server is shutting down: say so instead of dropping the socket.
        try:
            await websocket.close(code=1001, reason="server shutting down")
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------


def app_info(settings: Settings, hub: Hub) -> dict[str, Any]:
    """``GET /api/app/info`` (row A1): about, paths, help header, support summary."""
    from argos.core.hardware import active

    get = hub.config.get
    path = hub.config.path
    return {
        "name": "ARGOS",
        "version": __version__,
        "api": API_VERSION,
        "python": runtime.python_version(),
        "platform": platform.platform(terse=True),
        "paths": {
            "config": str(path) if path is not None else None,
            "config_dir": str(hub.config.directory) if hub.config.directory else None,
            "sessions": str(get("sessions_path", "")),
            "presets": str(get("data_paths.sequence_presets_directory", "")),
            "calibrations": str(get("data_paths.camera_calibration_directory", "")),
            "diagnostics": str(settings.log_dir) if settings.log_dir is not None else None,
            "log_file": str(settings.log_file) if settings.log_file is not None else None,
        },
        "profile": profile_records.summary(active.profile()),
        "log_level": str(get("ui.log_level", "INFO")),
        "diagnostics_enabled": bool(get("diagnostics.enabled", False)),
        # As the Qt support-bundle summary (shell.py:515).
        "astap_configured": bool(get("astrometry.astap_path", "")),
        "licence": "GPL-3.0-or-later",
        "licence_name": "GNU GPL v3 or later",
        "copyright": "Copyright © 2026 ARGOS contributors",
        "author": "Jules Perret",
        "description": (
            "Scientific acquisition and differential photometry for ZWO Seestar telescopes."
        ),
        "credits": [dict(c) for c in CREDITS],
        "project_url": PROJECT_URL,
        "docs_url": DOCS_URL,
    }


def create_app(settings: Settings, hub: Hub | None = None) -> FastAPI:
    """Build the ASGI app. *hub* is injectable for tests; one is created otherwise."""
    hub = hub or Hub(EventBus(), sim=settings.sim, settings=settings)
    auth = TokenAuth(settings.token)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        hub.bus.attach(asyncio.get_running_loop())
        bridge = _LogBridge(hub)
        logging.getLogger(_BRIDGED_LOGGER).addHandler(bridge)
        hub.start()
        if settings.simulator:
            try:
                await run_in_threadpool(hub.connect, "simulator")
            except ApiError as exc:
                logger.error("Simulator auto-connect failed: %s", exc.message)
        try:
            yield
        finally:
            await run_in_threadpool(hub.shutdown)
            logging.getLogger(_BRIDGED_LOGGER).removeHandler(bridge)
            hub.bus.detach()

    app = FastAPI(
        title="ARGOS server",
        version=__version__,
        lifespan=lifespan,
        # Every route but /api/health needs the token: no public schema pages.
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.hub = hub
    app.state.settings = settings
    hosts = allowed_hosts(settings.host)
    install_error_handlers(app)
    # Last added runs first: guard → CORS → catch-all → routes.
    app.add_middleware(CatchAllMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=ALLOWED_ORIGIN_REGEX,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
        max_age=600,
    )
    app.add_middleware(_LocalGuard, hosts=hosts)

    public = APIRouter()
    api = APIRouter(prefix="/api", dependencies=[Depends(auth.require)])

    @public.get("/api/health")
    def health() -> dict[str, Any]:
        return {"ok": True, "version": __version__, "api": API_VERSION, "boot_id": hub.boot_id}

    @api.get("/status")
    def status() -> dict[str, Any]:
        return hub.status()

    @api.post("/connection")
    def connect(body: ConnectBody) -> dict[str, Any]:
        return hub.connect(body.mode, body.host, body.port)

    @api.delete("/connection")
    def disconnect() -> dict[str, Any]:
        return hub.disconnect()

    @api.post("/camera/capture")
    def capture(body: ExposureBody) -> dict[str, Any]:
        return hub.capture(body.exposure_s, body.gain)

    @api.post("/camera/live")
    def live(body: ExposureBody) -> dict[str, Any]:
        return hub.live(body.exposure_s, body.gain)

    @api.patch("/camera/live")
    def live_update(body: ExposureBody) -> dict[str, Any]:
        return hub.update_live(body.exposure_s, body.gain)

    @api.post("/camera/stop")
    def camera_stop() -> dict[str, Any]:
        return hub.stop_camera()

    @api.post("/camera/open-fits")
    def open_fits(body: OpenFitsBody) -> dict[str, Any]:
        return hub.open_fits(body.path)

    @api.post("/mount/goto")
    def mount_goto(body: GotoBody) -> dict[str, Any]:
        return hub.mount_goto(body.ra_hours, body.dec_deg)

    @api.post("/mount/stop")
    def mount_stop() -> dict[str, Any]:
        return hub.mount_stop()

    @api.post("/mount/park")
    def mount_park() -> dict[str, Any]:
        return hub.mount_park()

    @api.post("/mount/unpark")
    def mount_unpark() -> dict[str, Any]:
        return hub.mount_unpark()

    @api.post("/mount/tracking")
    def mount_tracking(body: TrackingBody) -> dict[str, Any]:
        return hub.mount_tracking(body.enabled)

    # -- API 2 (wave 1) -------------------------------------------------------

    @api.get("/app/info")
    def get_app_info() -> dict[str, Any]:
        return app_info(settings, hub)

    @api.get("/logs")
    def get_logs(
        after: int = Query(default=0, ge=0),
        limit: int = Query(default=1000, ge=1, le=5000),
        level: Literal["debug", "cmd", "info", "ok", "warning", "error"] | None = None,
    ) -> dict[str, Any]:
        return {**hub.logbook.page(after=after, limit=limit, level=level), "boot_id": hub.boot_id}

    @api.get("/config")
    def get_config() -> dict[str, Any]:
        return hub.config.snapshot()

    @api.patch("/config")
    def patch_config(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
        return hub.config.patch(body, source="api").to_dict()

    @api.get("/devices")
    def get_devices() -> dict[str, Any]:
        return hub.devices()

    # connect-all before {device_id}: the literal path must win.
    @api.post("/devices/connect-all")
    def devices_connect_all(body: DeviceConnectBody | None = None) -> dict[str, Any]:
        body = body or DeviceConnectBody()
        return hub.connect_all(body.mode, body.host, body.port)

    @api.delete("/devices")
    def devices_disconnect_all() -> dict[str, Any]:
        return hub.disconnect_all()

    @api.post("/devices/{device_id}/connect")
    def device_connect(device_id: str, body: DeviceConnectBody | None = None) -> dict[str, Any]:
        body = body or DeviceConnectBody()
        return hub.connect_device(device_id, body.mode, body.host, body.port)

    @api.delete("/devices/{device_id}")
    def device_disconnect(device_id: str) -> dict[str, Any]:
        return hub.disconnect_device(device_id)

    @api.post("/discovery", status_code=202)
    def discovery(body: DiscoveryBody | None = None) -> dict[str, Any]:
        body = body or DiscoveryBody()
        job = hub.start_discovery(body.port, body.candidates, body.broadcast_timeout_s)
        return {"job_id": job["id"], "job": job}

    @api.get("/profiles")
    def get_profiles() -> dict[str, Any]:
        return hub.profiles()

    @api.put("/profile")
    def put_profile(body: ProfileBody) -> dict[str, Any]:
        return hub.set_profile(body.key)

    @api.get("/network")
    def get_network() -> dict[str, Any]:
        return hub.network_state()

    @api.post("/network/check")
    def network_check(body: NetworkCheckBody | None = None) -> dict[str, Any]:
        return hub.network_check(internet=(body or NetworkCheckBody()).internet)

    @api.get("/stellarium")
    def get_stellarium() -> dict[str, Any]:
        return hub.stellarium_state()

    @api.post("/stellarium")
    def start_stellarium(body: StellariumBody | None = None) -> dict[str, Any]:
        body = body or StellariumBody()
        return hub.stellarium_start(body.host, body.port)

    @api.delete("/stellarium")
    def stop_stellarium() -> dict[str, Any]:
        return hub.stellarium_stop()

    @api.get("/jobs")
    def get_jobs() -> dict[str, Any]:
        return {"jobs": hub.jobs.list()}

    @api.get("/jobs/{job_id}")
    def get_job(job_id: str) -> dict[str, Any]:
        return hub.jobs.get(job_id)

    @api.delete("/jobs/{job_id}")
    def cancel_job(job_id: str) -> dict[str, Any]:
        return hub.jobs.cancel(job_id)

    # -- API 2 (wave 2: Settings) ---------------------------------------------

    @api.get("/jobs/{job_id}/download")
    def job_download(job_id: str) -> FileResponse:
        path, name = hub.job_download(job_id)
        return FileResponse(path, media_type="application/zip", filename=name)

    @api.post("/support-bundle", status_code=202)
    def support_bundle(body: SupportBundleBody | None = None) -> dict[str, Any]:
        body = body or SupportBundleBody()
        job = hub.start_support_bundle(
            destination=body.destination,
            include_session=body.include_session,
            session_dir=body.session_dir,
            include_site=body.include_site,
            include_crash_reports=body.include_crash_reports,
            overwrite=body.overwrite,
        )
        return {"job_id": job["id"], "job": job}

    @api.get("/diagnostics/crash-reports")
    def crash_reports(since: str | None = Query(default=None, max_length=40)) -> dict[str, Any]:
        return hub.crash_reports(since)

    @api.get("/fs/list")
    def fs_list(
        path: str | None = Query(default=None, max_length=4096),
        kind: Literal["any", "dir", "file"] = "any",
        ext: str | None = Query(default=None, max_length=200),
        counts: Literal["fits"] | None = None,
        hidden: bool = False,
    ) -> dict[str, Any]:
        return hub.fs_list(path, kind=kind, ext=ext, counts=counts, hidden=hidden)

    @api.get("/sessions")
    def sessions(
        offset: int = Query(default=0, ge=0), limit: int = Query(default=50, ge=1, le=500)
    ) -> dict[str, Any]:
        return hub.sessions_page(offset=offset, limit=limit)

    @api.get("/astrometry/astap")
    def astap(
        path: str | None = Query(default=None, max_length=4096),
        database_path: str | None = Query(default=None, max_length=4096),
        database: str | None = Query(default=None, max_length=40),
    ) -> dict[str, Any]:
        return hub.astap_state(path, database_path, database)

    @api.post("/site/search", status_code=202)
    def site_search(body: SiteSearchBody) -> dict[str, Any]:
        job = hub.start_site_search(body.query)
        return {"job_id": job["id"], "job": job}

    @api.get("/site/check")
    def site_check() -> dict[str, Any]:
        return hub.site_check_state()

    @api.post("/site/check")
    def site_check_now() -> dict[str, Any]:
        return hub.site_check_now()

    @api.get("/caches")
    def caches() -> dict[str, Any]:
        return hub.caches()

    @api.delete("/caches/{kind}")
    def clear_cache(kind: str) -> dict[str, Any]:
        return hub.clear_cache(kind)

    @api.get("/catalogues/essential")
    def essential_catalogue() -> dict[str, Any]:
        from argos.core.catalog.offline import essential_catalogue_info

        return dict(essential_catalogue_info())

    @app.websocket("/ws/events")
    async def ws_events(websocket: WebSocket) -> None:
        if not await _admit(websocket, auth, hosts):
            return
        # The status first (contract), then the other snapshots and the recent
        # log lines, so a page opened mid-session still shows what happened.
        sub = hub.bus.subscribe_events(
            hub.status_event(), history=hub.log_history(), snapshots=hub.initial_snapshots()
        )

        async def send_next() -> bool:
            batch = await sub.next_batch()
            for message in batch:
                await websocket.send_text(json.dumps(message, separators=(",", ":")))
            return bool(batch)

        try:
            await _pump(websocket, send_next)
        finally:
            hub.bus.unsubscribe_events(sub)

    @app.websocket("/ws/frames")
    async def ws_frames(websocket: WebSocket) -> None:
        if not await _admit(websocket, auth, hosts):
            return
        if hub.bus.frame_client_count >= MAX_FRAME_CLIENTS:
            await websocket.close(code=1013, reason="too many frame clients")
            return
        sub = hub.bus.subscribe_frames()

        async def send_next() -> bool:
            frame = await sub.next_frame()
            if frame is None:
                return False
            await websocket.send_bytes(frame)
            return True

        try:
            await _pump(websocket, send_next)
        finally:
            hub.bus.unsubscribe_frames(sub)

    app.include_router(public)
    app.include_router(api)
    return app
