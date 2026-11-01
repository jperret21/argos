"""Token auth, origin checks and the error envelope."""

from __future__ import annotations

import pytest
from starlette.websockets import WebSocketDisconnect

from argos import __version__
from tests.server.conftest import AUTH, TOKEN

PROTECTED = [
    ("GET", "/api/status"),
    ("POST", "/api/connection"),
    ("DELETE", "/api/connection"),
    ("POST", "/api/camera/capture"),
    ("POST", "/api/camera/live"),
    ("PATCH", "/api/camera/live"),
    ("POST", "/api/camera/stop"),
    ("POST", "/api/camera/open-fits"),
    ("POST", "/api/mount/goto"),
    ("POST", "/api/mount/stop"),
    ("POST", "/api/mount/park"),
    ("POST", "/api/mount/unpark"),
    ("POST", "/api/mount/tracking"),
]


def test_health_needs_no_token(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    boot_id = body.pop("boot_id")
    assert body == {"ok": True, "version": __version__, "api": 2}
    # One id per server process, the same on every call (log restarts are told by it).
    assert isinstance(boot_id, str) and len(boot_id) == 16
    assert client.get("/api/health").json()["boot_id"] == boot_id


@pytest.mark.parametrize("method,path", PROTECTED)
def test_protected_routes_reject_missing_token(client, method, path):
    response = client.request(method, path)
    assert response.status_code == 401
    assert response.json() == {
        "error": {"code": "unauthorized", "message": "Missing or invalid bearer token"}
    }
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize(
    "header",
    [f"Bearer {TOKEN}x", "Bearer ", f"Basic {TOKEN}", TOKEN, f"Bearer{TOKEN}"],
)
def test_wrong_token_or_scheme_is_rejected(client, header):
    response = client.get("/api/status", headers={"Authorization": header})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_bearer_scheme_is_case_insensitive(client):
    response = client.get("/api/status", headers={"Authorization": f"bearer {TOKEN}"})
    assert response.status_code == 200


@pytest.mark.parametrize("path", ["/ws/events", "/ws/frames"])
@pytest.mark.parametrize("query", ["", "?token=", "?token=nope"])
def test_websockets_close_4401_without_valid_token(client, path, query):
    with pytest.raises(WebSocketDisconnect) as info:
        with client.websocket_connect(path + query) as ws:
            ws.receive_text()
    assert info.value.code == 4401


@pytest.mark.parametrize("path", ["/ws/events", "/ws/frames"])
def test_websockets_close_4403_for_foreign_origin(client, path):
    with pytest.raises(WebSocketDisconnect) as info:
        with client.websocket_connect(
            f"{path}?token={TOKEN}", headers={"Origin": "http://evil.example"}
        ) as ws:
            ws.receive_text()
    assert info.value.code == 4403


def test_websocket_accepts_local_origin(client):
    with client.websocket_connect(
        f"/ws/events?token={TOKEN}", headers={"Origin": "http://localhost:5173"}
    ) as ws:
        assert ws.receive_json()["type"] == "status"


@pytest.mark.parametrize(
    "origin",
    [
        "http://localhost:5173",
        "http://127.0.0.1:4173",
        "http://localhost",
        "tauri://localhost",
        "http://tauri.localhost",
    ],
)
def test_cors_preflight_allows_local_origins(client, origin):
    response = client.options(
        "/api/status",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
    assert "authorization" in response.headers["access-control-allow-headers"].lower()


@pytest.mark.parametrize(
    "origin",
    [
        "http://evil.example",
        "https://localhost:5173",
        "http://localhost.evil.com",
        "http://127.0.0.2:5173",
        "null",
    ],
)
def test_cors_rejects_other_origins(client, origin):
    response = client.get("/api/health", headers={"Origin": origin})
    assert "access-control-allow-origin" not in response.headers


def test_cors_headers_present_on_401(client):
    # Otherwise the browser reports an opaque CORS failure instead of the 401.
    response = client.get("/api/status", headers={"Origin": "http://localhost:5173"})
    assert response.status_code == 401
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_unknown_route_uses_error_envelope(client):
    response = client.get("/api/nope", headers=AUTH)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_wrong_method_uses_error_envelope(client):
    response = client.get("/api/health/../camera/capture", headers=AUTH)
    assert response.status_code in (404, 405)
    assert "error" in response.json()


def test_no_public_schema_pages(client):
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404


# -- DNS rebinding: Host and Origin guards ------------------------------------


@pytest.mark.parametrize("host", ["rebind.attacker.example:8742", "192.168.1.20:8742", "evil"])
def test_foreign_host_is_refused_before_anything_runs(connected, host):
    response = connected.post(
        "/api/mount/tracking", json={"enabled": False}, headers={**AUTH, "Host": host}
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden_host"


@pytest.mark.parametrize("host", ["127.0.0.1:8742", "localhost:5173", "[::1]:8742", "localhost"])
def test_loopback_hosts_are_accepted(client, host):
    assert client.get("/api/health", headers={"Host": host}).status_code == 200


def test_foreign_origin_cannot_run_a_command(connected):
    # CORS alone would let this POST run (the browser only hides the answer).
    response = connected.post(
        "/api/mount/unpark", headers={**AUTH, "Origin": "http://rebind.attacker.example:8742"}
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden_origin"
    status = connected.get("/api/status", headers=AUTH).json()
    assert status["mount"]["state"] == "parked"  # nothing happened


def test_websocket_with_foreign_host_closes_4403(client):
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(
            f"/ws/events?token={TOKEN}", headers={"Host": "rebind.attacker.example:8742"}
        ) as ws:
            ws.receive_json()
    assert exc.value.code == 4403


def test_network_bind_accepts_any_host(make_client):
    from argos.server.app import create_app
    from argos.server.settings import Settings
    from tests.server.conftest import BASE_URL, LoopbackClient

    app = create_app(Settings(token=TOKEN, host="0.0.0.0"))
    with LoopbackClient(app, base_url=BASE_URL) as lan:
        assert lan.get("/api/health", headers={"Host": "192.168.1.20:8742"}).status_code == 200


# -- Unexpected failures keep the envelope (and CORS) -------------------------


def test_unexpected_exception_uses_the_envelope_with_cors(client, monkeypatch):
    hub = client.app.state.hub

    def broken():
        raise RuntimeError("boom")

    monkeypatch.setattr(hub, "status", broken)
    response = client.get("/api/status", headers={**AUTH, "Origin": "http://localhost:5173"})
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert "boom" not in response.json()["error"]["message"]  # details stay in the log
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
