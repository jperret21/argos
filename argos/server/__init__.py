"""Headless ARGOS server — the HTTP + WebSocket back end of the web front-end.

Since 0.5.0 the desktop app is a web front-end (Svelte, in a Tauri shell) that
talks to this server over ``http://127.0.0.1``. The server drives the devices
(the built-in simulator, or a Seestar through the Alpaca wrappers in
``argos.core.alpaca``) and streams state and frames to the front-end.

**No Qt, anywhere.** Nothing under ``argos.server`` may import PyQt6, directly
or transitively — ``tests/server/test_no_qt.py`` enforces it. The scientific
core is shared with the retired PyQt6 app, which stays in the repository only
as the reference for the parity tests.

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
