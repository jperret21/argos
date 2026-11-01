"""The contract's error envelope and the handlers that enforce it.

Every 4xx/5xx leaves the server as::

    {"error": {"code": "<snake_case>", "message": "<human text>"}}

including FastAPI's own validation failures (mapped to ``400
invalid_argument``), unknown routes (``404 not_found``) and any unexpected
exception (``500 internal_error``, traceback in the server log), so the
front-end has exactly one shape to handle.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger(__name__)

#: Fallback codes for plain HTTP errors raised by the framework itself.
_STATUS_CODES = {
    400: "invalid_argument",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    413: "payload_too_large",
    415: "unsupported_media_type",
}


class ApiError(Exception):
    """An error with a contract code, raised anywhere and rendered by the handler.

    Args:
        status: HTTP status code.
        code: Stable snake_case identifier the front-end can switch on.
        message: Human-readable explanation, safe to show to the observer.
        headers: Extra response headers (``WWW-Authenticate`` for a 401).
    """

    def __init__(
        self, status: int, code: str, message: str, headers: dict[str, str] | None = None
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.headers = headers


def error_body(code: str, message: str) -> dict[str, Any]:
    return {"error": {"code": code, "message": message}}


def _describe_validation(exc: RequestValidationError) -> str:
    """One readable line from pydantic's error list (first error wins)."""
    errors = exc.errors()
    if not errors:
        return "Invalid request"
    first = errors[0]
    # loc is ("body", "exposure_s") — the leading "body" is noise for a user.
    loc = ".".join(str(part) for part in first.get("loc", ()) if part != "body")
    msg = first.get("msg", "invalid value")
    return f"{loc}: {msg}" if loc else msg


def install_error_handlers(app: FastAPI) -> None:
    """Route every error the app can raise through :func:`error_body`."""

    @app.exception_handler(ApiError)
    async def _api_error(_request: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(
            error_body(exc.code, exc.message), status_code=exc.status, headers=exc.headers
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            error_body("invalid_argument", _describe_validation(exc)), status_code=400
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _STATUS_CODES.get(exc.status_code, "http_error")
        message = exc.detail if isinstance(exc.detail, str) else code.replace("_", " ")
        return JSONResponse(
            error_body(code, message),
            status_code=exc.status_code,
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(Exception)
    async def _unexpected(_request: Request, exc: Exception) -> JSONResponse:
        # Backstop for a failure outside CatchAllMiddleware (in a middleware):
        # Starlette's ServerErrorMiddleware sends this, then re-raises the
        # exception, which uvicorn logs with its traceback.
        return JSONResponse(_internal_error(exc), status_code=500)


def _internal_error(exc: Exception) -> dict[str, Any]:
    return error_body(
        "internal_error", f"Unexpected server error ({exc.__class__.__name__}); see the server log"
    )


class CatchAllMiddleware:
    """Answer an unexpected exception with the envelope, *inside* CORS.

    Starlette sends its own 500 from the outermost layer, past the CORS
    middleware, so a browser would only see an opaque network failure. This
    pure ASGI layer sits under CORS (added before it): the 500 gets the CORS
    headers and the front-end can read ``internal_error``. The traceback goes
    to the server log.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = False

        async def send_tracked(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, receive, send_tracked)
        except Exception as exc:
            if started:
                raise  # too late for an envelope: let uvicorn close the response
            logger.exception("Unexpected error on %s %s", scope.get("method"), scope.get("path"))
            await JSONResponse(_internal_error(exc), status_code=500)(scope, receive, send)
