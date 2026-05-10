"""Minimal ASCOM Alpaca mock server — pure Python, no dotnet needed.

Simulates telescope/0 and camera/0 endpoints with realistic responses.
Used by validate_alpaca.py for Level 1 testing without real hardware.

Usage:
    # Terminal 1 — start the mock
    .venv/bin/python scripts/mock_alpaca_server.py

    # Terminal 2 — run validation against it
    .venv/bin/python scripts/validate_alpaca.py localhost 8765
"""

from __future__ import annotations

import array
import json
import logging
import struct
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)

PORT = 8765

# ---------------------------------------------------------------------------
# Simulated state
# ---------------------------------------------------------------------------

_state = {
    # telescope
    "tel_connected":      False,
    "tel_ra":             5.5753,    # Orion RA
    "tel_dec":            -5.3911,
    "tel_altitude":       42.5,
    "tel_azimuth":        178.3,
    "tel_tracking":       False,
    "tel_slewing":        False,
    "tel_atpark":         False,
    "tel_canpark":        True,
    "tel_canslewasync":   True,
    "tel_name":           "Mock Seestar S30 Pro",
    # camera
    "cam_connected":      False,
    "cam_name":           "Mock IMX585",
    "cam_width":          3840,
    "cam_height":         2160,
    "cam_gain":           80,
    "cam_gainmin":        0,
    "cam_gainmax":        100,
    "cam_state":          0,        # 0=idle
    "cam_imageready":     False,
    "cam_exposure_start": 0.0,
    "cam_exposure_dur":   0.0,
}


def _ok(value=None) -> dict:
    return {"ClientTransactionID": 0, "ServerTransactionID": 0,
            "ErrorNumber": 0, "ErrorMessage": "", "Value": value}


def _err(number: int, message: str) -> dict:
    return {"ClientTransactionID": 0, "ServerTransactionID": 0,
            "ErrorNumber": number, "ErrorMessage": message}


# ---------------------------------------------------------------------------
# Request handler
# ---------------------------------------------------------------------------

class AlpacaHandler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        logger.debug(fmt, *args)

    def _send_json(self, data: dict, status: int = 200) -> None:
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _parse_body(self) -> dict[str, str]:
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length).decode() if length else ""
        return {k: v[0] for k, v in parse_qs(raw).items()}

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        parts = parsed.path.strip("/").split("/")
        # /api/v1/{device}/{number}/{attribute}
        if len(parts) < 4 or parts[0] != "api" or parts[1] != "v1":
            self._send_json(_err(400, "bad path"), 400)
            return
        device, attribute = parts[2], parts[4] if len(parts) > 4 else parts[3]
        self._handle_get(device, attribute)

    def do_PUT(self) -> None:
        parsed = urlparse(self.path)
        parts = parsed.path.strip("/").split("/")
        if len(parts) < 4:
            self._send_json(_err(400, "bad path"), 400)
            return
        device, method = parts[2], parts[4] if len(parts) > 4 else parts[3]
        body = self._parse_body()
        self._handle_put(device, method, body)

    # ------------------------------------------------------------------
    # GET dispatch
    # ------------------------------------------------------------------

    def _handle_get(self, device: str, attr: str) -> None:  # noqa: C901
        s = _state

        if device == "telescope":
            if not s["tel_connected"] and attr != "connected":
                self._send_json(_err(1031, "not connected")); return
            # Auto-complete slew after 2s
            if s["tel_slewing"] and time.time() - s.get("_slew_start", 0) > 2.0:
                s["tel_slewing"] = False
            MAP = {
                "connected":          s["tel_connected"],
                "name":               s["tel_name"],
                "rightascension":     s["tel_ra"],
                "declination":        s["tel_dec"],
                "altitude":           s["tel_altitude"],
                "azimuth":            s["tel_azimuth"],
                "tracking":           s["tel_tracking"],
                "slewing":            s["tel_slewing"],
                "atpark":             s["tel_atpark"],
                "canpark":            s["tel_canpark"],
                "canslewasync":       s["tel_canslewasync"],
                "canmoveaxis":        False,
                "utcdate":            time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "description":        "Mock Seestar Alpaca server",
                "driverinfo":         "SeerControl mock",
                "driverversion":      "1.0",
                "interfaceversion":   3,
                "supportedactions":   [],
            }
            val = MAP.get(attr)
            if val is None and attr not in MAP:
                self._send_json(_err(1024, f"not implemented: {attr}")); return
            self._send_json(_ok(val)); return

        if device == "camera":
            if not s["cam_connected"] and attr != "connected":
                self._send_json(_err(1031, "not connected")); return
            # Auto-complete exposure
            if s["cam_state"] in (1, 2):
                elapsed = time.time() - s["cam_exposure_start"]
                if elapsed >= s["cam_exposure_dur"]:
                    s["cam_state"] = 0
                    s["cam_imageready"] = True
            if attr == "imagearray":
                if not s["cam_imageready"]:
                    self._send_json(_err(1028, "no image ready")); return
                # Return a small 100x100 test pattern as column-major int32 list
                w, h = 100, 100
                data = [[int(x * 655 + y * 6) for y in range(h)] for x in range(w)]
                self._send_json({**_ok(), "Value": data,
                                 "Type": 2, "Rank": 2}); return
            MAP = {
                "connected":    s["cam_connected"],
                "name":         s["cam_name"],
                "cameraxsize":  s["cam_width"],
                "cameraysize":  s["cam_height"],
                "gain":         s["cam_gain"],
                "gainmin":      s["cam_gainmin"],
                "gainmax":      s["cam_gainmax"],
                "camerastate":  s["cam_state"],
                "imageready":   s["cam_imageready"],
                "ccdtemperature": 20.0,
                "description":  "Mock IMX585",
                "driverinfo":   "SeerControl mock",
                "driverversion": "1.0",
                "interfaceversion": 3,
                "supportedactions": [],
            }
            val = MAP.get(attr)
            if val is None and attr not in MAP:
                self._send_json(_err(1024, f"not implemented: {attr}")); return
            self._send_json(_ok(val)); return

        self._send_json(_err(400, f"unknown device: {device}"))

    # ------------------------------------------------------------------
    # PUT dispatch
    # ------------------------------------------------------------------

    def _handle_put(self, device: str, method: str, body: dict) -> None:
        s = _state

        if device == "telescope":
            if method == "connected":
                s["tel_connected"] = body.get("Connected", "").lower() == "true"
                logger.info("Telescope connected=%s", s["tel_connected"])
                self._send_json(_ok()); return
            if not s["tel_connected"]:
                self._send_json(_err(1031, "not connected")); return
            if method == "tracking":
                s["tel_tracking"] = body.get("Tracking", "").lower() == "true"
                self._send_json(_ok()); return
            if method == "slewtocoordinatesasync":
                s["tel_ra"]  = float(body.get("RightAscension", s["tel_ra"]))
                s["tel_dec"] = float(body.get("Declination", s["tel_dec"]))
                s["tel_slewing"] = True
                s["_slew_start"] = time.time()
                self._send_json(_ok()); return
            if method == "abortslew":
                s["tel_slewing"] = False
                self._send_json(_ok()); return
            if method == "park":
                s["tel_atpark"] = True
                self._send_json(_ok()); return
            if method == "unpark":
                s["tel_atpark"] = False
                self._send_json(_ok()); return
            if method == "utcdate":
                self._send_json(_ok()); return
            if method in ("targetrightascension", "targetdeclination"):
                self._send_json(_ok()); return
            self._send_json(_err(1024, f"not implemented: {method}")); return

        if device == "camera":
            if method == "connected":
                s["cam_connected"] = body.get("Connected", "").lower() == "true"
                logger.info("Camera connected=%s", s["cam_connected"])
                self._send_json(_ok()); return
            if not s["cam_connected"]:
                self._send_json(_err(1031, "not connected")); return
            if method == "gain":
                s["cam_gain"] = int(body.get("Gain", s["cam_gain"]))
                self._send_json(_ok()); return
            if method == "startexposure":
                dur = float(body.get("Duration", 1.0))
                s["cam_exposure_dur"]   = dur
                s["cam_exposure_start"] = time.time()
                s["cam_state"]          = 2      # exposing
                s["cam_imageready"]     = False
                logger.info("Exposure started: %.2fs", dur)
                self._send_json(_ok()); return
            if method == "stopexposure":
                s["cam_state"]      = 0
                s["cam_imageready"] = False
                self._send_json(_ok()); return
            self._send_json(_err(1024, f"not implemented: {method}")); return

        self._send_json(_err(400, f"unknown device: {device}"))


# ---------------------------------------------------------------------------

def main() -> None:
    server = HTTPServer(("localhost", PORT), AlpacaHandler)
    logger.info("Mock Alpaca server running on localhost:%d", PORT)
    logger.info("Stop with Ctrl+C")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Stopped.")


if __name__ == "__main__":
    main()
