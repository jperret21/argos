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
import threading
import time
from contextlib import asynccontextmanager
from typing import Any, Awaitable, Callable, Literal

import anyio
from fastapi import APIRouter, Depends, FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field, model_validator
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import Headers
from starlette.responses import JSONResponse
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
            self._hub.publish_log(level, message)
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


def create_app(settings: Settings, hub: Hub | None = None) -> FastAPI:
    """Build the ASGI app. *hub* is injectable for tests; one is created otherwise."""
    hub = hub or Hub(EventBus(), sim=settings.sim)
    auth = TokenAuth(settings.token)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        hub.bus.attach(asyncio.get_running_loop())
        bridge = _LogBridge(hub)
        logging.getLogger(_BRIDGED_LOGGER).addHandler(bridge)
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
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
        max_age=600,
    )
    app.add_middleware(_LocalGuard, hosts=hosts)

    public = APIRouter()
    api = APIRouter(prefix="/api", dependencies=[Depends(auth.require)])

    @public.get("/api/health")
    def health() -> dict[str, Any]:
        return {"ok": True, "version": __version__, "api": API_VERSION}

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

    @app.websocket("/ws/events")
    async def ws_events(websocket: WebSocket) -> None:
        if not await _admit(websocket, auth, hosts):
            return
        # The status first (contract), then the recent log lines, so a page
        # opened mid-session still shows what happened before it.
        sub = hub.bus.subscribe_events(hub.status_event(), history=hub.log_history())

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
