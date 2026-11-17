"""Bearer-token authentication and the origin allow-list.

The server binds 127.0.0.1, but any web page the observer opens can still
*reach* localhost. Two independent guards keep such pages out:

- a per-launch random token (``secrets.token_urlsafe``) that every route but
  ``GET /api/health`` requires — as ``Authorization: Bearer`` over HTTP, as
  ``?token=`` on WebSockets, because browsers cannot set WebSocket headers;
- an origin allow-list: CORS for HTTP, and an explicit ``Origin`` check on
  WebSockets, which CORS does not cover;
- a ``Host`` allow-list (loopback names only, when the server is bound to
  loopback) and a refusal of any HTTP request whose ``Origin`` is foreign.
  CORS only stops a page from *reading* an answer; a DNS-rebinding page is
  same-origin once its hostname resolves to 127.0.0.1, so it needs no
  preflight and its request would still *run*. Its ``Host`` (and ``Origin``)
  name the attacker's domain, which these checks refuse.
"""

from __future__ import annotations

import re
import secrets

from fastapi import Request

from argos.server.errors import ApiError

#: Origins the front-end can legitimately run from: the Vite dev server or a
#: preview on any localhost port, and the Tauri webview on each platform.
ALLOWED_ORIGIN_REGEX = (
    r"^(http://(localhost|127\.0\.0\.1)(:\d{1,5})?"
    r"|tauri://localhost"
    r"|http://tauri\.localhost)$"
)
_ALLOWED_ORIGIN = re.compile(ALLOWED_ORIGIN_REGEX)

#: Host names a loopback-bound server answers to (the Tauri webview included).
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1", "tauri.localhost"})

#: WebSocket close codes (4000–4999 is the application range).
WS_CLOSE_UNAUTHORIZED = 4401
WS_CLOSE_FORBIDDEN_ORIGIN = 4403


def make_token() -> str:
    """A fresh random token for one server launch."""
    return secrets.token_urlsafe(32)


def origin_allowed(origin: str | None) -> bool:
    """True when *origin* may talk to the server.

    A missing ``Origin`` header means a non-browser client (curl, a test, the
    Tauri sidecar supervisor): the token alone authenticates it.
    """
    return origin is None or bool(_ALLOWED_ORIGIN.match(origin))


def is_loopback(host: str) -> bool:
    """True for the interfaces that keep the server off the network."""
    return host.strip("[]") in ("127.0.0.1", "localhost", "::1")


def host_name(header: str | None) -> str | None:
    """The host part of a ``Host`` header, lower-cased, without port or brackets."""
    if not header:
        return None
    header = header.strip().lower()
    if header.startswith("["):  # [::1]:8742
        end = header.find("]")
        return header[1:end] if end > 0 else None
    return header.rsplit(":", 1)[0] if header.count(":") == 1 else header


def allowed_hosts(bound_host: str) -> frozenset[str] | None:
    """Host names to accept, or ``None`` (any) when bound to a network interface.

    A server deliberately bound to a LAN address is reached under names and
    addresses this process cannot know; the token and the origin checks then
    stand alone (the CLI already warns about such a bind).
    """
    if not is_loopback(bound_host):
        return None
    return LOOPBACK_HOSTS | {bound_host.strip("[]").lower()}


def host_allowed(header: str | None, allowed: frozenset[str] | None) -> bool:
    if allowed is None:
        return True
    name = host_name(header)
    return name is not None and name in allowed


class TokenAuth:
    """Constant-time comparison against the launch token."""

    def __init__(self, token: str) -> None:
        if not token:
            raise ValueError("token must not be empty")
        self._token = token.encode("utf-8")

    def check(self, presented: str | None) -> bool:
        if not presented:
            return False
        return secrets.compare_digest(presented.encode("utf-8"), self._token)

    def require(self, request: Request) -> None:
        """FastAPI dependency: raise ``401 unauthorized`` without a valid bearer token."""
        header = request.headers.get("authorization", "")
        scheme, _, value = header.partition(" ")
        if scheme.lower() != "bearer" or not self.check(value.strip()):
            raise ApiError(
                401,
                "unauthorized",
                "Missing or invalid bearer token",
                headers={"WWW-Authenticate": "Bearer"},
            )
