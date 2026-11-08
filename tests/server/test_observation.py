"""Observation identity (A38, A39), catalogue lookups (A40, A41, A20), opened files (A27),
conditions (A37) and the wave 3 event streams."""

from __future__ import annotations

import json
import socket
import struct
import time

import numpy as np
import pytest
from astropy.io import fits

from argos.core.catalog.object_resolver import (
    NearbyObject,
    ObjectResolutionError,
    ResolvedObject,
)
from argos.server.events import EventSubscriber
from tests.server.conftest import (
    AUTH,
    TOKEN,
    decode_frame,
    log_messages,
    receive_bytes,
    receive_json,
    receive_until,
    science_client,
    status,
    wait_for,
)

SS_CYG = ResolvedObject("SS Cyg", 325.6790, 43.5862, "V*", "CDS Sesame")
M42 = ResolvedObject("M 42", 83.8221, -5.3911, "HII", "Argos Essential Catalogue")


@pytest.fixture
def client(make_client, tmp_path):
    return science_client(make_client, tmp_path)


def _observation(client) -> dict:
    return client.get("/api/observation", headers=AUTH).json()


# ---------------------------------------------------------------------------
# Observation
# ---------------------------------------------------------------------------


def test_object_name_is_shared_and_announced(client):
    assert _observation(client)["object_name"] == ""
    with client.websocket_connect(f"/ws/events?token={TOKEN}") as events:
        first = receive_json(events)
        assert first["observation"]["object_name"] == ""
        record = client.put("/api/observation", json={"object_name": " T  CrB "}, headers=AUTH)
        event = receive_until(events, lambda m: m["type"] == "observation")
    assert record.json()["object_name"] == "T CrB" == event["object_name"]
    assert event["revision"] == record.json()["revision"] == 1
    assert status(client)["observation"]["object_name"] == "T CrB"


def test_a_variable_target_becomes_the_photometry_target(client):
    """Q-P8: only a variable-star type writes the target role of targets/<object>.json."""
    record = client.post(
        "/api/observation/target",
        json={"name": "SS Cyg", "ra_hours": 21.71268, "dec_deg": 43.58612, "object_type": "V*",
              "source": "CDS Sesame"},
        headers=AUTH,
    ).json()  # fmt: skip
    assert record["object_name"] == "SS Cyg"
    assert record["target"]["is_variable"] and record["target"]["programme"] == "variable"
    path = client.sessions_path / "targets" / "SS_Cyg.json"
    assert record["photometry_target"]["path"] == str(path)
    saved = json.loads(path.read_text())
    assert saved["object"] == "SS Cyg"
    assert [s["role"] for s in saved["stars"]] == ["target"]
    assert saved["stars"][0]["ra_deg"] == pytest.approx(21.71268 * 15.0)
    assert "Catalogue target: SS Cyg — RA 21.71268h Dec +43.58612°" in log_messages(client)


def test_a_non_variable_target_is_only_an_identity(client):
    record = client.post(
        "/api/observation/target",
        json={"name": "M 42", "ra_hours": 5.588, "dec_deg": -5.39, "object_type": "HII"},
        headers=AUTH,
    ).json()
    assert record["target"]["name"] == "M 42" and record["photometry_target"] is None
    assert not (client.sessions_path / "targets").exists()
    renamed = client.put("/api/observation", json={"object_name": "Orion"}, headers=AUTH).json()
    assert renamed["target"] is None  # a target whose name differs is dropped
    cleared = client.delete("/api/observation/target", headers=AUTH).json()
    assert cleared["object_name"] == "Orion" and cleared["target"] is None


def test_an_exoplanet_programme_also_writes_the_target(client):
    record = client.post(
        "/api/observation/target",
        json={"name": "HAT-P-7", "ra_hours": 19.4796, "dec_deg": 47.9690, "object_type": "*",
              "programme": "exoplanet"},
        headers=AUTH,
    ).json()  # fmt: skip
    assert record["photometry_target"]["name"] == "HAT-P-7"


@pytest.mark.parametrize(
    "body",
    [
        {"name": "", "ra_hours": 1.0, "dec_deg": 1.0},
        {"name": "X", "ra_hours": 25.0, "dec_deg": 1.0},
        {"name": "X", "ra_hours": 1.0, "dec_deg": 91.0},
        {"name": "X", "ra_hours": 1.0, "dec_deg": 1.0, "programme": "comet"},
    ],
)
def test_target_bodies_are_checked(client, body):
    assert client.post("/api/observation/target", json=body, headers=AUTH).status_code == 400


def test_take_shot_writes_the_observation_object(make_client, tmp_path):
    client = science_client(make_client, tmp_path, connect=("camera",))
    client.put("/api/observation", json={"object_name": "RR Lyr"}, headers=AUTH)
    client.post("/api/camera/capture", json={"exposure_s": 0.02, "save": True}, headers=AUTH)
    saved = wait_for(lambda: client.get("/api/camera/saved", headers=AUTH).json()["saves"])
    with fits.open(saved[0]["path"]) as hdul:
        assert hdul[0].header["OBJECT"] == "RR Lyr"


# ---------------------------------------------------------------------------
# Catalogue lookups (resolver injected: no network in the suite)
# ---------------------------------------------------------------------------


def test_resolve_returns_the_resolver_record(client):
    hub = client.app.state.hub
    calls: list[tuple] = []

    def resolve(query, **kwargs):
        calls.append((query, kwargs))
        return SS_CYG

    hub.observation.resolve_object = resolve
    record = client.get("/api/catalog/resolve?q=ss%20cyg", headers=AUTH).json()
    assert record == {
        "name": "SS Cyg",
        "ra_hours": pytest.approx(325.6790 / 15.0),
        "dec_deg": 43.5862,
        "object_type": "V*",
        "type_label": "Variable star",
        "is_variable": True,
        "source": "CDS Sesame",
    }
    # The configured cache, never the module default under ~/Argos.
    assert str(calls[0][1]["cache_path"]).startswith(str(client.sessions_path.parent))


@pytest.mark.parametrize(
    "message, status_code, code",
    [
        ("No ICRS coordinates found for ‘Zork’.", 404, "not_found"),
        (
            "Catalogue unavailable. Connect to the internet or use a previously searched "
            "target.",
            502,
            "lookup_failed",
        ),
    ],
)
def test_resolve_errors_keep_the_resolver_text(client, message, status_code, code):
    def fail(query, **kwargs):
        raise ObjectResolutionError(message)

    client.app.state.hub.observation.resolve_object = fail
    answer = client.get("/api/catalog/resolve?q=Zork", headers=AUTH)
    assert answer.status_code == status_code
    assert answer.json()["error"] == {"code": code, "message": message}


def test_resolve_needs_a_designation(client):
    answer = client.get("/api/catalog/resolve?q=%20", headers=AUTH)
    assert answer.status_code == 400
    assert answer.json()["error"]["message"] == "Enter an object designation first."


def test_resolve_a_bundled_object_offline(client):
    """The bundled essential catalogue answers without a network (real resolver)."""
    record = client.get("/api/catalog/resolve?q=M42", headers=AUTH).json()
    assert record["name"] == "M 42" and record["source"] == "Argos Essential Catalogue"


def test_suggest_is_offline_and_bounded(client):
    answer = client.get("/api/catalog/suggest?q=M3&limit=3", headers=AUTH).json()
    assert answer["query"] == "M3" and 0 < len(answer["names"]) <= 3
    assert client.get("/api/catalog/suggest?q=", headers=AUTH).json()["names"] == []


def test_nearby_uses_the_network_only_when_asked(client):
    seen: list[dict] = []

    def nearby(ra_deg, dec_deg, **kwargs):
        seen.append(kwargs)
        return [NearbyObject(M42, 12.5)]

    client.app.state.hub.observation.resolve_nearby = nearby
    answer = client.get("/api/catalog/nearby?ra_hours=5.588&dec_deg=-5.39", headers=AUTH).json()
    assert answer["network"] is False and seen[-1]["allow_network"] is False
    assert answer["candidates"][0]["name"] == "M 42"
    assert answer["candidates"][0]["separation_arcsec"] == 12.5
    client.get("/api/catalog/nearby?ra_hours=5.588&dec_deg=-5.39&network=true", headers=AUTH)
    assert seen[-1]["allow_network"] is True


def _stellarium_goto(port: int, ra_hours: float, dec_deg: float) -> None:
    ra = int(round(ra_hours / 24.0 * 0x100000000)) % 0x100000000
    dec = int(round(dec_deg / 90.0 * 0x40000000))
    packet = struct.pack("<HHqIi", 20, 0, int(time.time() * 1e6), ra, dec)
    with socket.create_connection(("127.0.0.1", port), timeout=2) as sock:
        sock.sendall(packet)
        time.sleep(0.2)


def test_a_stellarium_goto_offers_names_never_sets_one(client):
    """A20: target_suggestions after a Stellarium GoTo (offline by default)."""
    hub = client.app.state.hub
    calls: list[dict] = []

    def nearby(ra_deg, dec_deg, **kwargs):
        calls.append(kwargs)
        return [NearbyObject(M42, 3.0)]

    hub.observation.resolve_nearby = nearby
    with socket.socket() as probe:  # a free port for the bridge
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    started = client.post("/api/stellarium", json={"port": port}, headers=AUTH)
    assert started.status_code == 200, started.text
    try:
        with client.websocket_connect(f"/ws/events?token={TOKEN}") as events:
            receive_json(events)
            _stellarium_goto(port, 5.588, -5.39)
            ready = receive_until(
                events, lambda m: m["type"] == "target_suggestions" and m["state"] == "ready"
            )
    finally:
        client.delete("/api/stellarium", headers=AUTH)
    assert ready["candidates"][0]["name"] == "M 42"
    assert calls[-1]["allow_network"] is False  # stellarium.online_target_lookup is off
    assert _observation(client)["object_name"] == ""  # offered, not set
    assert client.get("/api/stellarium", headers=AUTH).json()["suggestions"]["state"] == "ready"
    assert "Stellarium target-name suggestion: 1 nearby catalogue candidate(s)." in log_messages(
        client
    )


# ---------------------------------------------------------------------------
# Opened files (A27): dated from the header, metered
# ---------------------------------------------------------------------------


def _write(path, data, **cards):
    hdu = fits.PrimaryHDU(data=data)
    for key, value in cards.items():
        hdu.header[key.replace("_", "-")] = value
    hdu.writeto(path)
    return path


@pytest.mark.parametrize(
    "cards, epoch",
    [
        ({"DATE_OBS": "2026-11-01T19:00:00.000", "EXPTIME": 10.0,
          "DATE_AVG": "2026-11-01T19:00:05.002"}, "2026-11-01T19:00:05.002Z"),
        ({"DATE_OBS": "2026-11-01T19:00:00.000", "EXPTIME": 10.0}, "2026-11-01T19:00:05.000Z"),
        ({"DATE_OBS": "2026-11-01", "EXPTIME": 10.0}, None),  # no time part: never midnight
        ({}, None),
    ],
)  # fmt: skip
def test_open_fits_is_dated_from_its_header(client, tmp_path, cards, epoch):
    data = np.full((8, 8), 1500, np.uint16)
    data[4, 4] = 9000
    path = _write(tmp_path / "frame.fit", data, BAYERPAT="RGGB", **cards)
    with client.websocket_connect(f"/ws/frames?token={TOKEN}") as frames:
        with client.websocket_connect(f"/ws/events?token={TOKEN}") as events:
            receive_json(events)
            answer = client.post("/api/camera/open-fits", json={"path": str(path)}, headers=AUTH)
            assert answer.status_code == 200, answer.text
            header, _ = decode_frame(receive_bytes(frames))
            metrics = receive_until(events, lambda m: m["type"] == "frame_metrics")
    assert header["origin"] == "file" and header["epoch_utc"] == epoch
    assert header["path"] == str(path) and header["file_name"] == "frame.fit"
    assert header["bayer"] == "RGGB" and metrics["seq"] == header["seq"]
    if epoch is None:
        assert (
            "frame.fit has no usable DATE-OBS time (or EXPTIME) — no photometry point can be "
            "dated, so none will be measured on it." in log_messages(client)
        )
    # An opened file adds no conditions row.
    assert client.get("/api/session/conditions", headers=AUTH).json()["rows"] == []


# ---------------------------------------------------------------------------
# Conditions page and the stream kinds under backpressure
# ---------------------------------------------------------------------------


def test_conditions_rows_follow_live_frames(make_client, tmp_path):
    client = science_client(make_client, tmp_path, connect=("camera",))
    client.post("/api/camera/live", json={"exposure_s": 0.02}, headers=AUTH)
    page = wait_for(
        lambda: len((p := client.get("/api/session/conditions", headers=AUTH).json())["rows"]) >= 3
        and p
    )
    client.post("/api/camera/stop", headers=AUTH)
    seqs = [row["seq"] for row in page["rows"]]
    assert seqs == sorted(seqs) and page["boot_id"] == client.app.state.hub.boot_id
    row = page["rows"][0]
    assert row["origin"] == "live" and row["airmass_mount"] is None  # no mount
    assert row["airmass_target"] is None  # no target, no site (X2)
    later = client.get(f"/api/session/conditions?since_seq={seqs[0]}", headers=AUTH).json()
    assert later["rows"][0]["seq"] == seqs[1]
    limited = client.get("/api/session/conditions?limit=1", headers=AUTH).json()
    assert len(limited["rows"]) == 1 and limited["truncated"] is True


def test_stream_kinds_survive_backpressure_after_the_logs():
    import asyncio

    sub = EventSubscriber(capacity=6)
    sub.offer("log", None, {"type": "log", "i": 0})
    sub.offer("frame_saved", None, {"type": "frame_saved", "seq": 1})
    for seq in range(1, 20):
        sub.offer("focuser", seq, {"type": "focuser", "n": seq})
    sub.offer("conditions", None, {"type": "conditions", "seq": 1})
    sub.offer("log", None, {"type": "log", "i": 1})
    sub.offer("frame_saved", None, {"type": "frame_saved", "seq": 2})
    batch = asyncio.run(asyncio.wait_for(sub.next_batch(), 1.0))
    kinds = [m["type"] for m in batch]
    assert kinds.count("focuser") == 1 and batch[kinds.index("focuser")]["n"] == 19
    assert [m["seq"] for m in batch if m["type"] == "frame_saved"] == [1, 2]
    assert any(m["type"] == "conditions" for m in batch)


def test_suggestions_come_in_natural_order_best_match_first(client):
    """Review of wave 3: 'M 1' lists M 1, then M 10-M 19, never M 100 before M 13."""
    names = client.get("/api/catalog/suggest?q=M 1&limit=6", headers=AUTH).json()["names"]
    assert names[0] == "M 1"
    assert names[1:6] == ["M 10", "M 11", "M 12", "M 13", "M 14"]
