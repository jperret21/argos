"""Headless ARGOS server — the HTTP + WebSocket back end of the web front-end.

The desktop UI is moving from PyQt6 to a web front-end (Svelte) that talks to
this server over ``http://127.0.0.1``. The server drives the devices (the
built-in simulator, or a Seestar through the existing Alpaca wrappers in
``argos.core.alpaca``) and streams state and frames to the browser.

**No Qt, anywhere.** Nothing under ``argos.server`` may import PyQt6, directly
or transitively — ``tests/server/test_no_qt.py`` enforces it. The scientific
core is reused untouched; the Qt app keeps running unchanged next to it.

The wire contract is documented in ``argos/server/protocol.md``. Run with::

    python -m argos.server [--host 127.0.0.1] [--port 8742] [--simulator] [--dev-token TOKEN]
                           [--config-dir DIR] [--log-dir DIR] [--connect-timeout S]
"""

#: Version of the wire contract (``GET /api/health`` → ``"api"``). Bump on any
#: breaking change to routes, payloads or the binary frame layout.
API_VERSION = 2

#: Default TCP port. ``--port 0`` lets the OS pick one (the Tauri sidecar
#: reads the actual port from the ``ARGOS_PORT=`` line on stdout).
DEFAULT_PORT = 8742
