"""``python -m argos.server`` — run the headless server.

Startup prints exactly two lines on **stdout**, which a supervising process
(the future Tauri sidecar) parses::

    ARGOS_PORT=<port>
    ARGOS_TOKEN=<token>

Everything else — uvicorn's access log included — goes to stderr, so stdout
stays a clean machine channel. The socket is bound and listening *before*
the lines are printed, so a client that reads them can connect at once, and
``--port 0`` lets the OS choose a free port.

Ctrl-C (SIGINT) shuts down gracefully and exits with status 0, without the
KeyboardInterrupt traceback uvicorn's re-raised signal would print.
"""

from __future__ import annotations

import argparse
import logging
import re
import socket
import sys

from argos import __version__
from argos.server import DEFAULT_PORT

logger = logging.getLogger("argos.server")

#: Below this length a --dev-token is guessable; the CLI warns.
_SHORT_TOKEN = 16


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m argos.server",
        description="Headless ARGOS server (HTTP + WebSocket) for the web front-end.",
    )
    parser.add_argument("--host", default="127.0.0.1", help="interface to bind (default 127.0.0.1)")
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"TCP port (default {DEFAULT_PORT}; 0 = any free port)",
    )
    parser.add_argument(
        "--simulator", action="store_true", help="connect the built-in simulator at startup"
    )
    parser.add_argument(
        "--dev-token",
        metavar="TOKEN",
        help="fixed bearer token for development (default: random per launch)",
    )
    parser.add_argument("--version", action="version", version=f"ARGOS {__version__}")
    args = parser.parse_args(argv)
    if not 0 <= args.port <= 65535:
        parser.error("--port must be between 0 and 65535")
    if args.dev_token is not None and not args.dev_token.strip():
        parser.error("--dev-token must not be empty")
    return args


class _RedactTokens(logging.Filter):
    """Keep the bearer token out of logs (uvicorn logs WebSocket URLs with ``?token=``)."""

    _TOKEN = re.compile(r"(token=)[^&\s\"']+")

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        if "token=" in message:
            record.msg, record.args = self._TOKEN.sub(r"\1***", message), None
        return True


def _load_hardware_profile() -> None:
    """Make the user's configured telescope profile active, as ``main.py`` does.

    It only matters in Alpaca mode (CFA pattern of the raw frames); a broken
    config must not stop the server, so failures fall back to the default.
    """
    try:
        from argos.core.config import Config
        from argos.core.hardware import active

        scope = active.load_from_config(Config.load())
        logger.info("Telescope profile: %s", scope.describe())
    except Exception as exc:
        logger.warning("Could not load the telescope profile from config: %s", exc)


def _bind(host: str, port: int) -> socket.socket:
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    sock = socket.socket(family, socket.SOCK_STREAM)
    # Fast restarts while the previous socket sits in TIME_WAIT.
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((host, port))
    sock.listen(128)
    sock.setblocking(False)
    return sock


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stderr,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    for handler in logging.getLogger().handlers:
        handler.addFilter(_RedactTokens())

    import uvicorn

    from argos.server.app import create_app
    from argos.server.auth import make_token
    from argos.server.settings import Settings

    token = args.dev_token.strip() if args.dev_token else make_token()
    if args.dev_token and len(token) < _SHORT_TOKEN:
        # (The flag's name is not repeated here: the log must never contain
        # anything resembling the token.)
        logger.warning(
            "The fixed development token has only %d characters: a guessable token, "
            "for development only (the default is random per launch)",
            len(token),
        )
    if args.host not in ("127.0.0.1", "localhost", "::1"):
        logger.warning("Binding %s: the server is reachable from the network", args.host)
    try:
        sock = _bind(args.host, args.port)
    except OSError as exc:
        print(f"argos.server: cannot bind {args.host}:{args.port}: {exc}", file=sys.stderr)
        return 1
    port = sock.getsockname()[1]
    _load_hardware_profile()

    settings = Settings(token=token, host=args.host, port=port, simulator=args.simulator)
    app = create_app(settings)
    config = uvicorn.Config(
        app,
        log_config=None,  # keep our stderr logging; uvicorn would send access logs to stdout
        ws=_ws_implementation(),
        timeout_graceful_shutdown=3,
        ws_ping_interval=20.0,
        ws_ping_timeout=20.0,
        # permessage-deflate would zlib every frame on the event-loop thread:
        # 240 ms for a 1080×1920 frame (ratio 0.59 — sensor noise barely
        # compresses), for a localhost link that does not need it.
        ws_per_message_deflate=False,
    )
    print(f"ARGOS_PORT={port}", flush=True)
    print(f"ARGOS_TOKEN={token}", flush=True)
    logger.info("ARGOS %s server on http://%s:%d", __version__, args.host, port)
    try:
        uvicorn.Server(config).run(sockets=[sock])
    except KeyboardInterrupt:
        # uvicorn re-raises SIGINT after its graceful shutdown: a normal stop.
        pass
    return 0


def _ws_implementation() -> str:
    """The WebSocket implementation latest-frame-wins was verified with.

    uvicorn's "sansio" protocol waits for the socket to drain before each
    send, which bounds what a stalled frames client can pin in memory. Older
    uvicorn releases (the server extra allows >= 0.29) lack it and pick
    another implementation under "auto".
    """
    from uvicorn.config import WS_PROTOCOLS

    return "websockets-sansio" if "websockets-sansio" in WS_PROTOCOLS else "auto"


if __name__ == "__main__":
    sys.exit(main())
