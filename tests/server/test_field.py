"""Wave 4: field identification, catalogue, layers, selection, targets, centre and sync.

A fake ASTAP (a script that writes the ``.ini`` ASTAP would) solves the
simulator's synthetic frames, which a real ASTAP cannot; the catalogue
queries and the point identification are injected (no network). One test
solves a copy of a real Seestar frame with the installed ASTAP, and skips
with its reason when ASTAP or such a frame is absent.
"""

from __future__ import annotations

import json
import math
import os
import shutil
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from argos.core.catalog.aavso import Band, ComparisonStar, VariableStar
from argos.core.catalog.field_objects import NamedFieldObject
from argos.core.catalog.gaia import GaiaStar
from argos.core.catalog.point_identity import PointIdentityLookupError, PointSourceIdentity
from argos.core.catalog.targets import TargetSet, TargetStar
from argos.core.imaging.astrometry_session import field_geometry, project_points
from argos.core.imaging.platesolve import FrameWCS, find_astap
from argos.server.field_solve import to_frame
from tests.server.conftest import (
    AUTH,
    TOKEN,
    log_messages,
    receive_until,
    science_client,
    wait_for,
)

SCALE = 7.35 / 3600.0  # deg per green px
CRVAL = (291.366, 42.784)
#: The simulator's frames are 160 x 120: the green plane is 80 x 60.
GREEN_SHAPE = (60, 80)
WCS_FIELDS = {
    "CRVAL1": CRVAL[0],
    "CRVAL2": CRVAL[1],
    "CRPIX1": 40.5,
    "CRPIX2": 30.5,
    "CD1_1": -SCALE,
    "CD1_2": 0.0,
    "CD2_1": 0.0,
    "CD2_2": SCALE,
}
GREEN_WCS = FrameWCS(CRVAL[0], CRVAL[1], 40.5, 30.5, (-SCALE, 0.0, 0.0, SCALE))

FAKE_ASTAP = """#!{python}
import json, sys, time
from pathlib import Path
here = Path(__file__).resolve().parent
behaviour = json.loads((here / "behaviour.json").read_text())
with (here / "calls.jsonl").open("a") as log:
    log.write(json.dumps(sys.argv[1:]) + "\\n")
fits = Path(sys.argv[sys.argv.index("-f") + 1])
time.sleep(behaviour.get("sleep", 0))
if behaviour["mode"] == "fail":
    text = "PLTSOLVD=F\\nERROR=No solution found\\n"
else:
    text = "PLTSOLVD=T\\n" + "".join(f"{{k}}={{v}}\\n" for k, v in behaviour["wcs"].items())
fits.with_suffix(".ini").write_text(text)
"""


class FakeAstap:
    def __init__(self, folder: Path) -> None:
        folder.mkdir(parents=True, exist_ok=True)
        self.folder = folder
        self.path = folder / "astap_cli"
        self.path.write_text(FAKE_ASTAP.format(python=sys.executable))
        self.path.chmod(0o755)
        self.set("solve")

    def set(self, mode: str, sleep: float = 0.0, wcs: dict | None = None) -> None:
        behaviour = {"mode": mode, "sleep": sleep, "wcs": wcs or WCS_FIELDS}
        (self.folder / "behaviour.json").write_text(json.dumps(behaviour))

    def calls(self) -> list[list[str]]:
        log = self.folder / "calls.jsonl"
        if not log.exists():
            return []
        return [json.loads(line) for line in log.read_text().splitlines()]


def sky(gx: float, gy: float) -> tuple[float, float]:
    ra, dec = GREEN_WCS.pixel_to_world_deg(gx, gy)
    return float(ra), float(dec)


def comparison(auid, gx, gy, v, b=None):
    bands = tuple(Band(n, m) for n, m in (("V", v), ("B", b)) if m is not None)
    return ComparisonStar(auid, *sky(gx, gy), label=str(int(v * 10)), bands=bands, chart_id="X99")


class FakeCatalog:
    """The query functions of ``argos.core.catalog`` (field_catalog.run_request)."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple, dict]] = []
        self.variables = [
            VariableStar(
                "RR Lyr",
                *sky(40.0, 30.0),
                auid="000-BCD-123",
                var_type="RRAB",
                category="Variable",
                max_mag="7.06 V",
                min_mag="8.12 V",
                period=0.567,
            )
        ]
        self.comparisons = [
            comparison("000-AAA-001", 20.0, 15.0, 9.5, 10.1),
            comparison("000-AAA-002", 62.0, 45.0, 10.2),
        ]
        self.field_stars = [
            GaiaStar("1001", *sky(20.0, 15.0), g_mag=9.4),
            GaiaStar("1002", *sky(22.0, 15.0), g_mag=11.0),
            GaiaStar("1003", *sky(10.0, 50.0), g_mag=12.5),
        ]
        self.named_objects = [
            NamedFieldObject("HD 1001", *sky(10.0, 50.0), object_type="*"),
            NamedFieldObject("NGC 9999", *sky(70.0, 10.0), object_type="Galaxy"),
        ]

    def _log(self, name, args, kwargs):
        self.calls.append((name, args, kwargs))

    def vsx_cone_search(self, *args, **kwargs):
        self._log("vsx", args, kwargs)
        return list(self.variables)

    def vsp_chart(self, *args, **kwargs):
        self._log("vsp", args, kwargs)
        return list(self.comparisons)

    def gaia_cone_search(self, *args, **kwargs):
        self._log("gaia", args, kwargs)
        return list(self.field_stars)

    def simbad_field_objects(self, *args, **kwargs):
        self._log("simbad", args, kwargs)
        return list(self.named_objects)

    def exoplanet_hosts_in_cone(self, *args, **kwargs):
        self._log("exoplanets", args, kwargs)
        return []


@pytest.fixture
def field_client(make_client, tmp_path):
    client = science_client(make_client, tmp_path, connect=("mount", "camera"))
    astap = FakeAstap(tmp_path / "astap")
    db = tmp_path / "astap-db"
    db.mkdir()
    response = client.patch(
        "/api/config",
        json={
            "astrometry.astap_path": str(astap.path),
            "astrometry.database": "D50",
            "astrometry.database_path": str(db),
            "astrometry.live_resolve_s": 3600,
            "catalog.show_cached_exoplanets": False,
        },
        headers=AUTH,
    )
    assert response.status_code == 200, response.text
    for path, body in (("/api/mount/unpark", None), ("/api/mount/tracking", {"enabled": True})):
        assert client.post(path, json=body, headers=AUTH).status_code == 200
    hub = client.app.state.hub
    hub.field.catalog_api = FakeCatalog()
    hub.field.identify_point = lambda *args, **kwargs: None
    client.hub = hub  # type: ignore[attr-defined]
    client.astap = astap  # type: ignore[attr-defined]
    client.db = db  # type: ignore[attr-defined]
    return client


def take_frame(client) -> int:
    hub = client.hub
    before = hub.field._frame.seq if hub.field._frame else 0
    response = client.post("/api/camera/capture", json={"exposure_s": 0.05}, headers=AUTH)
    assert response.status_code == 200, response.text
    wait_for(lambda: hub.field._frame is not None and hub.field._frame.seq > before)
    wait_for(lambda: client.get("/api/status", headers=AUTH).json()["camera"]["state"] == "idle")
    return hub.field._frame.seq


def settle(client, timeout: float = 10.0) -> None:
    wait_for(client.hub.field.idle, timeout=timeout)


def wait_job(client, job_id: str, timeout: float = 15.0) -> dict:
    return wait_for(
        lambda: (
            job
            if (job := client.get(f"/api/jobs/{job_id}", headers=AUTH).json())["state"]
            in ("done", "failed", "cancelled")
            else None
        ),
        timeout=timeout,
    )


def solve(client) -> dict:
    response = client.post("/api/field/solve", headers=AUTH)
    assert response.status_code == 202, response.text
    job = wait_job(client, response.json()["job_id"])
    settle(client)
    return job


# -- A43-A45: identify field -------------------------------------------------------


def test_solve_needs_a_frame(field_client):
    response = field_client.post("/api/field/solve", headers=AUTH)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "no_frame"
    assert field_client.get("/api/field", headers=AUTH).json()["state"] == "none"


def test_identify_field_is_a_job_with_the_s24_database_flags(field_client):
    seq = take_frame(field_client)
    job = solve(field_client)
    assert job["kind"] == "field_solve" and job["state"] == "done"
    field = field_client.get("/api/field", headers=AUTH).json()
    assert field["state"] == "solved" and field["generation"] == 1
    solution = field["solution"]
    assert solution["frame_seq"] == seq and solution["mode"] == "manual"
    assert solution["ra_hours"] == pytest.approx(CRVAL[0] / 15.0)
    assert solution["dec_deg"] == pytest.approx(CRVAL[1])
    assert solution["scale_arcsec_px"] == pytest.approx(7.35 / 2.0, abs=1e-3)  # per frame px
    assert solution["hint"]["source"] == "mount"
    assert job["result"]["summary"] == solution["summary"]
    wcs = field["wcs"]
    assert wcs["crpix"] == [2 * 40.5 - 0.5, 2 * 30.5 - 0.5]
    assert wcs["cd"][0][0] == pytest.approx(-SCALE / 2.0)
    assert wcs["frame_shape"] == [120, 160]
    assert field["grid"]["lines"]
    argv = field_client.astap.calls()[-1]
    assert argv[argv.index("-D") + 1] == "D50"  # S24: the set survives the folder
    assert argv[argv.index("-d") + 1] == str(field_client.db)
    assert "-ra" in argv  # the mount's pointing as the hint
    assert any(m.startswith("Plate-solving frame #") for m in log_messages(field_client))
    assert any(m.startswith("Solved — RA 19.4244h") for m in log_messages(field_client))


def test_a_failed_solve_keeps_the_last_solution(field_client):
    take_frame(field_client)
    solve(field_client)
    field_client.astap.set("fail")
    job = solve(field_client)
    assert job["state"] == "failed" and job["error"]["code"] == "not_solved"
    field = field_client.get("/api/field", headers=AUTH).json()
    assert field["state"] == "failed" and field["solution"] is not None
    assert field["last_attempt"]["outcome"] == "failed"
    assert "Solve: No solution found" in log_messages(field_client)


def test_a_solve_can_be_cancelled_and_refuses_a_second_one(field_client):
    take_frame(field_client)
    field_client.astap.set("solve", sleep=30)
    started = field_client.post("/api/field/solve", headers=AUTH)
    assert started.status_code == 202
    job_id = started.json()["job_id"]
    wait_for(lambda: field_client.astap.calls())  # ASTAP is running
    second = field_client.post("/api/field/solve", headers=AUTH)
    assert second.status_code == 409 and second.json()["error"]["owner"] == job_id
    assert field_client.delete(f"/api/jobs/{job_id}", headers=AUTH).status_code == 200
    job = wait_job(field_client, job_id, timeout=3.0)
    assert job["state"] == "cancelled"
    field = field_client.get("/api/field", headers=AUTH).json()
    assert field["state"] == "none" and field["last_attempt"]["outcome"] == "cancelled"
    assert "Field identification cancelled." in log_messages(field_client)
    # The field route cancels too.
    job_id = field_client.post("/api/field/solve", headers=AUTH).json()["job_id"]
    wait_for(lambda: len(field_client.astap.calls()) >= 2)
    field_client.delete("/api/field/solve", headers=AUTH)
    assert wait_job(field_client, job_id, timeout=3.0)["state"] == "cancelled"


def test_automatic_identification_solves_when_due(field_client):
    response = field_client.put("/api/field/auto", json={"enabled": True}, headers=AUTH)
    assert response.json()["auto"] is True and response.json()["auto_source"] == "observer"
    take_frame(field_client)
    settle(field_client)
    field = field_client.get("/api/field", headers=AUTH).json()
    assert field["state"] == "solved" and field["solution"]["mode"] == "auto"
    calls = len(field_client.astap.calls())
    take_frame(field_client)  # not due: 3600 s, and the mount did not move
    settle(field_client)
    assert len(field_client.astap.calls()) == calls
    argv = field_client.astap.calls()[-1]
    assert argv[argv.index("-r") + 1] == "5"  # the live search radius
    assert "Automatic field identification on" in log_messages(field_client)


def test_a_sequence_arms_identification_and_restores_it(field_client):
    hub = field_client.hub
    hub.field.arm_for_sequence()
    field = field_client.get("/api/field", headers=AUTH).json()
    assert field["auto"] is True and field["auto_source"] == "sequence"
    hub.field.disarm_after_sequence()
    assert field_client.get("/api/field", headers=AUTH).json()["auto"] is False


# -- invalidation ------------------------------------------------------------------


def test_goto_invalidates_the_field_and_its_layers(field_client):
    take_frame(field_client)
    solve(field_client)
    assert field_client.get("/api/field/layers", headers=AUTH).json()["available"] is True
    response = field_client.post(
        "/api/mount/goto", json={"ra_hours": 5.0, "dec_deg": 20.0}, headers=AUTH
    )
    assert response.status_code == 200
    field = field_client.get("/api/field", headers=AUTH).json()
    assert field["state"] == "invalidated" and field["reason"] == "slew"
    assert field["wcs"] is None and field["solution"] is None
    layers = field_client.get("/api/field/layers", headers=AUTH).json()
    assert layers["available"] is False and layers["layers"]["stars"] == []
    assert field_client.get("/api/field/catalog", headers=AUTH).json()["state"] == "idle"
    assert "GoTo — the field moved; identify it again." in log_messages(field_client)


def test_mount_moved_outside_argos_invalidates(field_client):
    take_frame(field_client)
    solve(field_client)
    mount = field_client.hub._slots["mount"].handle
    reading = mount.read()
    mount.goto(reading.ra_hours, reading.dec_deg - 1.0)  # Stellarium, the Seestar app…
    wait_for(lambda: field_client.get("/api/field", headers=AUTH).json()["reason"] == "mount_moved")


def test_a_frame_of_another_size_invalidates(field_client):
    take_frame(field_client)
    solve(field_client)
    hub = field_client.hub
    hub.field.on_frame(999, np.zeros((100, 100), np.uint16), "live")
    settle(field_client)
    field = field_client.get("/api/field", headers=AUTH).json()
    assert field["state"] == "invalidated" and field["reason"] == "geometry"


def write_fits(path: Path, data: np.ndarray, **cards) -> Path:
    from astropy.io import fits

    hdu = fits.PrimaryHDU(data=data)
    for key, value in cards.items():
        hdu.header[key] = value
    hdu.writeto(path)
    return path


def test_open_fits_invalidates_and_solves_with_the_header_hint(field_client, tmp_path):
    take_frame(field_client)
    solve(field_client)
    raw = np.full((120, 160), 800, np.uint16)
    path = write_fits(
        tmp_path / "frame.fits",
        raw,
        OBJCTRA="19 25 26.66",
        OBJCTDEC="+42 47 07.3",
        DATE_OBS="2026-09-25T22:07:45",
    )
    response = field_client.post("/api/camera/open-fits", json={"path": str(path)}, headers=AUTH)
    assert response.status_code == 200, response.text
    field = field_client.get("/api/field", headers=AUTH).json()
    assert field["state"] == "invalidated" and field["reason"] == "file_opened"
    wait_for(lambda: field_client.hub.field._frame.origin == "file")
    solve(field_client)
    field = field_client.get("/api/field", headers=AUTH).json()
    assert field["solution"]["hint"]["source"] == "header"
    argv = field_client.astap.calls()[-1]
    assert float(argv[argv.index("-ra") + 1]) == pytest.approx(19.42407, abs=1e-4)


def test_camera_frames_after_a_solved_file_invalidate_it(field_client, tmp_path):
    path = write_fits(tmp_path / "file.fits", np.full((120, 160), 700, np.uint16))
    field_client.post("/api/camera/open-fits", json={"path": str(path)}, headers=AUTH)
    wait_for(lambda: field_client.hub.field._frame.origin == "file")
    solve(field_client)
    take_frame(field_client)
    field = field_client.get("/api/field", headers=AUTH).json()
    assert field["state"] == "invalidated" and field["reason"] == "source_changed"
    assert field_client.get("/api/field/select", headers=AUTH).json()["selection"] is None


# -- A46, A47: catalogue and layers ------------------------------------------------


def test_the_catalogue_is_fetched_once_per_field_with_the_core_request(field_client):
    take_frame(field_client)
    solve(field_client)
    fake = field_client.hub.field.catalog_api
    catalog = field_client.get("/api/field/catalog", headers=AUTH).json()
    assert catalog["state"] == "ready"
    assert catalog["counts"] == {
        "variables": 1,
        "comparisons": 2,
        "field_stars": 3,
        "named_objects": 2,
        "exoplanet_hosts": 0,
    }
    ra_deg, dec_deg, radius_deg, fov = field_geometry(GREEN_WCS, GREEN_SHAPE)
    name, args, kwargs = fake.calls[0]
    assert name == "vsx" and args == pytest.approx((ra_deg, dec_deg, radius_deg))
    assert kwargs["mag_limit"] == 15.0 and kwargs["max_results"] == 250
    vsp = next(c for c in fake.calls if c[0] == "vsp")
    assert vsp[1] == pytest.approx((ra_deg, dec_deg, fov))
    gaia = next(c for c in fake.calls if c[0] == "gaia")
    assert gaia[2]["max_results"] == 280  # 70 % of the 400 budget
    count = len(fake.calls)
    solve(field_client)  # same field: the cached catalogue is reused
    assert len(fake.calls) == count
    assert "Catalog: 1 variable(s) in field" in log_messages(field_client)


def test_layers_are_the_core_projection_in_frame_px(field_client):
    take_frame(field_client)
    solve(field_client)
    layers = field_client.get("/api/field/layers", headers=AUTH).json()
    assert layers["available"] and layers["frame_shape"] == [120, 160]
    fake = field_client.hub.field.catalog_api
    v = fake.variables[0]
    gx, gy = project_points(GREEN_WCS, GREEN_SHAPE, [(v.ra_deg, v.dec_deg)])[0]
    marker = layers["layers"]["variables"][0]
    assert (marker["x"], marker["y"]) == pytest.approx(to_frame(gx, gy), abs=0.01)
    assert marker["label"] == "RR Lyr" and marker["key"] == "auid:000-BCD-123"
    stars = {m["label"] for m in layers["layers"]["stars"]}
    assert "HD 1001" in stars  # SIMBAD name on its Gaia source (one marker)
    # Gaia 1002 sits 2 green px from 1001: one marker within 8 px (imaging_page.py:1839-1856).
    assert [m["source_id"] for m in layers["layers"]["stars"]] == ["1001", "1003"]
    assert [m["label"] for m in layers["layers"]["galaxies"]] == ["NGC 9999"]
    rows = {r["auid"]: r for r in layers["candidates"]}
    assert rows["000-AAA-001"]["b_minus_v"] == pytest.approx(0.6)
    assert rows["000-AAA-002"]["b_minus_v"] is None
    # Gaia 1002 is 2 green px from AAA-001, 1.6 mag fainter than its counterpart 1001.
    aperture = layers["aperture_r_px"] / 2.0
    expected = 1 if aperture >= 2.0 else 0
    assert rows["000-AAA-001"]["neighbours_in_aperture"] == expected
    assert rows["000-AAA-002"]["neighbours_in_aperture"] == 0


def test_refetch_needs_a_solution_and_config_refetches(field_client):
    response = field_client.post("/api/field/catalog/refetch", headers=AUTH)
    assert response.status_code == 409 and response.json()["error"]["code"] == "not_solved"
    take_frame(field_client)
    solve(field_client)
    fake = field_client.hub.field.catalog_api
    vsx_calls = lambda: sum(1 for c in fake.calls if c[0] == "vsx")  # noqa: E731
    assert vsx_calls() == 1
    response = field_client.post("/api/field/catalog/refetch", headers=AUTH)
    assert response.status_code == 202
    settle(field_client)
    assert vsx_calls() == 2
    field_client.patch("/api/config", json={"catalog.mag_limit": 12.0}, headers=AUTH)
    wait_for(lambda: vsx_calls() == 3, timeout=5.0)
    settle(field_client)
    assert next(c for c in reversed(fake.calls) if c[0] == "vsx")[2]["mag_limit"] == 12.0


# -- A49: selection ------------------------------------------------------------------


def variable_xy(client) -> tuple[float, float]:
    marker = client.get("/api/field/layers", headers=AUTH).json()["layers"]["variables"][0]
    return marker["x"], marker["y"]


def test_without_a_solution_a_click_measures_and_roles_wait(field_client):
    from argos.core.imaging.metrics import detect_stars

    take_frame(field_client)
    raw = field_client.hub.field._frame.raw
    star = max(detect_stars(raw).stars, key=lambda s: s.flux)
    x, y = to_frame(star.x, star.y)
    event = field_client.post("/api/field/select", json={"x": x, "y": y}, headers=AUTH).json()
    selection = event["selection"]
    assert selection["kind"] == "measured" and selection["roles_enabled"] is False
    assert selection["roles_reason"] == "identify the field first"
    assert selection["ring"]["aperture"] == "star"
    assert selection["measurement"]["snr"] > 0
    outside = field_client.post("/api/field/select", json={"x": 500, "y": 5}, headers=AUTH)
    assert outside.status_code == 400


def test_a_selection_is_followed_from_frame_to_frame(field_client):
    from argos.core.imaging.metrics import detect_stars

    take_frame(field_client)
    raw = field_client.hub.field._frame.raw
    star = max(detect_stars(raw).stars, key=lambda s: s.flux)
    sid = field_client.post(
        "/api/field/select",
        json={"x": to_frame(star.x, star.y)[0], "y": 2 * star.y + 0.5},
        headers=AUTH,
    ).json()["id"]
    seq = take_frame(field_client)
    settle(field_client)
    event = field_client.get("/api/field/select", headers=AUTH).json()
    assert event["id"] == sid and event["state"] == "tracking"
    assert event["selection"]["seq"] == seq


def test_a_catalogue_click_and_a_role_write_the_qt_file(field_client):
    field_client.hub.field.catalog_api.comparisons = []  # no VSP: no automatic comparison
    take_frame(field_client)
    solve(field_client)
    x, y = variable_xy(field_client)
    event = field_client.post(
        "/api/field/select", json={"x": x + 1.0, "y": y - 1.0, "tol_px": 8}, headers=AUTH
    ).json()
    selection = event["selection"]
    assert selection["kind"] == "variable" and selection["title"] == "Variable · RR Lyr"
    assert selection["roles_enabled"] and not selection["removable"]
    targets = field_client.post(
        "/api/targets", json={"selection": event["id"], "role": "target"}, headers=AUTH
    ).json()
    assert targets["object_name"] == "RR Lyr"  # the empty object name took the star's
    path = Path(targets["path"])
    assert path == field_client.sessions_path / "targets" / "RR_Lyr.json"
    v = field_client.hub.field.catalog_api.variables[0]
    expected = TargetSet("RR Lyr")
    expected.set_role(
        TargetStar(
            role="target",
            ra_deg=v.ra_deg,
            dec_deg=v.dec_deg,
            auid=v.auid,
            name=v.name,
            source="vsx",
            mags={},
        )
    )
    assert path.read_text(encoding="utf-8") == json.dumps(expected.to_dict(), indent=2)
    star = targets["stars"][0]
    assert star["role"] == "target" and star["x"] == pytest.approx(x, abs=0.01)
    assert "Target: RR Lyr" in log_messages(field_client)
    # The card now offers Remove, and the layers carry the role.
    again = field_client.post("/api/field/select", json={"x": x, "y": y}, headers=AUTH).json()[
        "selection"
    ]
    assert again["kind"] == "target" and again["removable"] and again["role"] == "target"
    settle(field_client)
    selected = field_client.get("/api/field/layers", headers=AUTH).json()["layers"]["selected"]
    assert [m["role"] for m in selected] == ["target"]
    stale = field_client.post("/api/targets", json={"selection": 1, "role": "check"}, headers=AUTH)
    assert stale.status_code == 409


def test_roles_add_remove_undo_byte_for_byte(field_client):
    field_client.put("/api/observation", json={"object_name": "RR Lyr"}, headers=AUTH)
    stars = [
        {
            "ra_deg": 291.36621,
            "dec_deg": 42.78436,
            "auid": "000-BCD-123",
            "name": "RR Lyr",
            "source": "vsx",
            "mags": {},
        },
        {
            "ra_deg": 291.40,
            "dec_deg": 42.70,
            "auid": "000-AAA-001",
            "name": "110",
            "source": "vsp",
            "mags": {"V": 11.0, "B": 11.6},
            "chart_id": "X99",
        },
        {"ra_hours": 19.4, "dec_deg": 42.8, "source": "manual"},
    ]
    for star, role in zip(stars, ("target", "comparison", "check")):
        response = field_client.post(
            "/api/targets", json={"star": star, "role": role}, headers=AUTH
        )
        assert response.status_code == 200, response.text
    path = field_client.sessions_path / "targets" / "RR_Lyr.json"
    before = path.read_bytes()
    expected = TargetSet("RR Lyr")
    expected.set_role(TargetStar("target", 291.36621, 42.78436, "000-BCD-123", "RR Lyr", "vsx", {}))
    expected.set_role(
        TargetStar(
            "comparison",
            291.40,
            42.70,
            "000-AAA-001",
            "110",
            "vsp",
            {"V": 11.0, "B": 11.6},
            chart_id="X99",
        )
    )
    expected.set_role(TargetStar("check", 19.4 * 15.0, 42.8, source="manual"))
    assert before.decode() == json.dumps(expected.to_dict(), indent=2)
    key = expected.stars[2].key()
    removed = field_client.delete(f"/api/targets/{key}", headers=AUTH).json()
    assert [s["role"] for s in removed["stars"]] == ["target", "comparison"]
    assert removed["removed"]["key"] == key
    assert "Removed from target set: " + expected.stars[2].display_name in log_messages(
        field_client
    )
    undo = {
        k: removed["removed"][k]
        for k in ("ra_deg", "dec_deg", "auid", "name", "source", "mags", "chart_id")
    }
    field_client.post("/api/targets", json={"star": undo, "role": "check"}, headers=AUTH)
    assert path.read_bytes() == before
    missing = field_client.delete("/api/targets/auid:nope", headers=AUTH)
    assert missing.status_code == 404
    bad = field_client.post("/api/targets", json={"role": "target"}, headers=AUTH)
    assert bad.status_code == 400


def test_the_set_follows_the_object_name(field_client):
    with field_client.websocket_connect(f"/ws/events?token={TOKEN}") as events:
        field_client.put("/api/observation", json={"object_name": "XX Cyg"}, headers=AUTH)
        event = receive_until(
            events, lambda m: m["type"] == "targets" and m["object_name"] == "XX Cyg"
        )
    assert event["path"].endswith("targets/XX_Cyg.json") and event["stars"] == []


def test_a_variable_index_becomes_the_target_with_vsp_comparisons(field_client):
    take_frame(field_client)
    solve(field_client)
    response = field_client.post(
        "/api/targets", json={"variable_index": 0, "role": "target"}, headers=AUTH
    )
    stars = response.json()["stars"]
    assert stars[0]["source"] == "vsx" and stars[0]["role"] == "target"
    # _auto_select_comparisons (1348-1429): the field's VSP stars, never anything else.
    comps = [s for s in stars if s["role"] == "comparison"]
    assert {s["auid"] for s in comps} <= {"000-AAA-001", "000-AAA-002"}
    assert all(s["source"] in ("vsp", "vsp_auto") and s["chart_id"] == "X99" for s in comps)
    messages = log_messages(field_client)
    assert any("comparison" in m and m.startswith("Photometry:") for m in messages)
    assert (
        field_client.post(
            "/api/targets", json={"variable_index": 7, "role": "target"}, headers=AUTH
        ).status_code
        == 404
    )


def blank_spot(client) -> tuple[float, float]:
    """A frame position far from every catalogue marker."""
    return 150.0, 110.0


def test_point_identification_outcomes_and_supersession(field_client):
    take_frame(field_client)
    solve(field_client)
    hub = field_client.hub
    release = threading.Event()
    calls = []

    def identify(ra_deg, dec_deg, **kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            release.wait(5)
            return PointSourceIdentity(
                "TYC 1-2-3", ra_deg, dec_deg, "*", "Gaia DR3", (("G", 11.2),), 0.4, "777"
            )
        if len(calls) == 2:
            return None
        if len(calls) == 3:
            raise PointIdentityLookupError("SIMBAD is unreachable")
        return PointSourceIdentity(
            "TYC 4-5-6", ra_deg, dec_deg, "*", "Gaia DR3", (("G", 12.0),), 0.2, "888"
        )

    hub.field.identify_point = identify
    x, y = blank_spot(field_client)
    first = field_client.post("/api/field/select", json={"x": x, "y": y}, headers=AUTH).json()
    assert first["state"] == "identifying" and first["selection"]["identifying"]
    second = field_client.post("/api/field/select", json={"x": x, "y": y}, headers=AUTH).json()
    assert second["id"] > first["id"]
    settle_selection = lambda sid: wait_for(  # noqa: E731
        lambda: field_client.get("/api/field/select", headers=AUTH).json()["state"] != "identifying"
    )
    settle_selection(second["id"])
    release.set()
    settle(field_client)
    event = field_client.get("/api/field/select", headers=AUTH).json()
    assert event["id"] == second["id"] and event["state"] == "no_match"  # P21: first dropped
    assert calls[0]["allow_simbad_network"] is True
    third = field_client.post("/api/field/select", json={"x": x, "y": y}, headers=AUTH).json()
    wait_for(
        lambda: field_client.get("/api/field/select", headers=AUTH).json()["id"] == third["id"]
        and field_client.get("/api/field/select", headers=AUTH).json()["state"] == "failed"
    )
    fourth = field_client.post("/api/field/select", json={"x": x, "y": y}, headers=AUTH).json()
    wait_for(
        lambda: field_client.get("/api/field/select", headers=AUTH).json()["state"] == "resolved"
    )
    event = field_client.get("/api/field/select", headers=AUTH).json()
    assert event["id"] == fourth["id"]
    selection = event["selection"]
    assert selection["kind"] == "point_identity"
    assert selection["title"] == "Identified star · TYC 4-5-6"
    assert selection["pending_star"]["source"] == "point_catalogue"
    settle(field_client)
    labels = [
        m["label"]
        for m in field_client.get("/api/field/layers", headers=AUTH).json()["layers"]["stars"]
    ]
    assert "TYC 4-5-6" in labels
    assert field_client.delete("/api/field/select", headers=AUTH).json()["selection"] is None


# -- A32, A33: centre and sync ----------------------------------------------------------


def test_center_needs_a_solution_and_a_target(field_client):
    response = field_client.post("/api/mount/center", headers=AUTH)
    assert response.json()["error"]["code"] == "not_solved"
    take_frame(field_client)
    solve(field_client)
    response = field_client.post("/api/mount/center", headers=AUTH)
    assert response.status_code == 409 and response.json()["error"]["code"] == "no_target"
    assert field_client.get("/api/field", headers=AUTH).json()["center_available"] is False
    field_client.post("/api/targets", json={"variable_index": 0, "role": "target"}, headers=AUTH)
    wait_for(lambda: field_client.get("/api/field", headers=AUTH).json()["center_available"])
    assert field_client.get("/api/status", headers=AUTH).json()["mount"]["center_available"]
    response = field_client.post("/api/mount/center", headers=AUTH)
    assert response.status_code == 200, response.text
    v = field_client.hub.field.catalog_api.variables[0]
    assert response.json()["target"]["ra_hours"] == pytest.approx(v.ra_deg / 15.0)
    field = field_client.get("/api/field", headers=AUTH).json()
    assert field["state"] == "invalidated" and field["reason"] == "center"
    messages = log_messages(field_client)
    assert any(m.startswith("Center: synced solved field RA 19.4244h") for m in messages)
    assert any(m.startswith("Center: slewing to target RA") for m in messages)


def test_sync_to_the_solution_keeps_the_field(field_client):
    response = field_client.post("/api/mount/sync", json={"source": "solution"}, headers=AUTH)
    assert response.json()["error"]["code"] == "not_solved"
    take_frame(field_client)
    solve(field_client)
    response = field_client.post("/api/mount/sync", json={"source": "solution"}, headers=AUTH)
    assert response.status_code == 200, response.text
    mount = response.json()
    centre_ra, centre_dec = GREEN_WCS.pixel_to_radec(39.5, 29.5)
    assert mount["ra_hours"] == pytest.approx(centre_ra, abs=1e-3)
    assert mount["dec_deg"] == pytest.approx(centre_dec, abs=1e-3)
    import time

    time.sleep(0.6)  # two mount polls: the moved reading is the new reference
    assert field_client.get("/api/field", headers=AUTH).json()["state"] == "solved"
    assert any(m.startswith("Sync to plate solution") for m in log_messages(field_client))
    wrong = field_client.post("/api/mount/sync", json={"source": "mount"}, headers=AUTH)
    assert wrong.status_code == 400


def open_and_solve(client, tmp_path, frame: np.ndarray, name: str = "opened.fits") -> None:
    path = write_fits(tmp_path / name, frame)
    response = client.post("/api/camera/open-fits", json={"path": str(path)}, headers=AUTH)
    assert response.status_code == 200, response.text
    wait_for(
        lambda: client.hub.field._frame is not None and client.hub.field._frame.origin == "file"
    )
    solve(client)
    assert client.get("/api/field", headers=AUTH).json()["state"] == "solved"


def test_sync_and_centre_refuse_the_solution_of_an_opened_file(field_client, tmp_path):
    """The technical review's case: a file of another night must never sync the mount."""
    from tests.server.test_field_units import gaussian_frame

    stars = [(80.0, 80.0, 15000), (240.0, 70.0, 12000), (100.0, 170.0, 18000)]
    open_and_solve(field_client, tmp_path, gaussian_frame((240, 320), stars, sigma=2.0))
    field_client.post("/api/targets", json={"variable_index": 0, "role": "target"}, headers=AUTH)
    settle(field_client)
    field = field_client.get("/api/field", headers=AUTH).json()
    assert field["solution"]["frame_origin"] == "file"
    assert field["center_available"] is False
    before = field_client.get("/api/status", headers=AUTH).json()["mount"]
    for path, body in (("/api/mount/sync", {"source": "solution"}), ("/api/mount/center", None)):
        response = field_client.post(path, json=body, headers=AUTH)
        assert response.status_code == 409, response.text
        assert response.json()["error"]["code"] == "file_solution"
    after = field_client.get("/api/status", headers=AUTH).json()["mount"]
    assert (after["ra_hours"], after["dec_deg"]) == (before["ra_hours"], before["dec_deg"])


def test_a_target_beyond_the_tangent_plane_has_no_reticle_and_the_event_is_strict_json(
    field_client,
):
    """A GoTo target 90° or more from the field projects to NaN: no reticle, no NaN."""
    response = field_client.post(
        "/api/mount/goto", json={"ra_hours": 5.5, "dec_deg": 20.0}, headers=AUTH
    )
    assert response.status_code == 200, response.text
    wait_for(
        lambda: field_client.get("/api/status", headers=AUTH).json()["mount"]["state"]
        == "tracking",
        timeout=15.0,
    )
    take_frame(field_client)
    solve(field_client)
    field = field_client.get("/api/field", headers=AUTH).json()
    assert field["state"] == "solved" and field["target_reticle"] is None
    assert field["solution"]["delta_target_arcmin"] > 90 * 60

    def strict(text: str) -> dict:
        def refuse(constant: str):
            raise ValueError(f"non-JSON constant {constant}")

        return json.loads(text, parse_constant=refuse)

    with field_client.websocket_connect(f"/ws/events?token={TOKEN}") as events:
        for _ in range(400):
            message = strict(events.receive_text())
            if message["type"] == "field":
                assert message["state"] == "solved"
                break
        else:
            pytest.fail("no field snapshot")


def test_wire_json_turns_non_finite_numbers_into_null():
    from argos.server.app import wire_json

    text = wire_json({"a": float("nan"), "b": [1.0, float("inf")], "c": {"d": -float("inf")}})
    assert json.loads(text) == {"a": None, "b": [1.0, None], "c": {"d": None}}
    assert wire_json({"x": 1.5}) == '{"x":1.5}'


def test_an_error_after_astap_ends_the_attempt(field_client, monkeypatch):
    """The technical review's stuck ``solving``: an exception after ASTAP releases it."""
    import argos.server.field as field_module

    take_frame(field_client)

    def broken(*args, **kwargs):
        raise ValueError("singular CD matrix")

    monkeypatch.setattr(field_module, "overlay_for", broken)
    job = solve(field_client)
    assert job["state"] == "failed" and job["error"]["code"] == "not_solved"
    field = field_client.get("/api/field", headers=AUTH).json()
    assert field["state"] == "failed" and field["solving"] is None
    monkeypatch.undo()
    job = solve(field_client)
    assert job["state"] == "done"
    assert field_client.get("/api/field", headers=AUTH).json()["state"] == "solved"


def test_an_invalidation_releases_a_running_solve(field_client):
    take_frame(field_client)
    field_client.astap.set("slow", sleep=5.0)
    response = field_client.post("/api/field/solve", headers=AUTH)
    assert response.status_code == 202
    wait_for(lambda: field_client.get("/api/field", headers=AUTH).json()["state"] == "solving")
    field_client.hub.field.invalidate("geometry")
    field = field_client.get("/api/field", headers=AUTH).json()
    assert field["state"] == "invalidated" and field["solving"] is None
    job = wait_job(field_client, response.json()["job_id"])
    assert job["state"] in ("cancelled", "failed")
    # The late end of the released attempt never claims the field back.
    assert field_client.get("/api/field", headers=AUTH).json()["solving"] is None


# -- events ---------------------------------------------------------------------------


def test_a_new_client_gets_every_wave4_snapshot(field_client):
    take_frame(field_client)
    solve(field_client)
    wanted = {"field", "catalog", "field_layers", "field_transform", "selection", "targets"}
    seen: dict[str, dict] = {}
    with field_client.websocket_connect(f"/ws/events?token={TOKEN}") as events:
        receive_until(
            events,
            lambda m: (seen.setdefault(m["type"], m) and False) or wanted <= set(seen),
            timeout=10.0,
        )
    assert seen["field"]["state"] == "solved"
    assert seen["catalog"]["state"] == "ready"
    assert seen["field_layers"]["available"] is True


def test_tracking_follows_a_shifted_frame(field_client, tmp_path):
    from tests.server.test_field_units import gaussian_frame

    stars = [(80.0, 80.0, 15000), (240.0, 70.0, 12000), (100.0, 170.0, 18000), (230, 160, 9000)]
    ref = gaussian_frame((240, 320), stars, sigma=2.0)
    path = write_fits(tmp_path / "ref.fits", ref)
    assert (
        field_client.post(
            "/api/camera/open-fits", json={"path": str(path)}, headers=AUTH
        ).status_code
        == 200
    )
    wait_for(lambda: field_client.hub.field._frame.origin == "file")
    solve(field_client)
    shifted = gaussian_frame((240, 320), [(x + 2.0, y - 1.0, p) for x, y, p in stars], sigma=2.0)
    field_client.hub.field.on_frame(10_000, shifted, "file")
    settle(field_client)
    transform = field_client.get("/api/field/transform", headers=AUTH).json()
    assert transform["frame_seq"] == 10_000 and transform["anchor_source"] == "detected"
    assert transform["anchors"] >= 3
    assert transform["dx"] == pytest.approx(2.0, abs=0.3)
    assert transform["dy"] == pytest.approx(-1.0, abs=0.3)
    assert transform["rot_deg"] == 0.0  # the simulator is an EQ mount: translation only


TRACK_STARS = [
    (120.0, 110.0, 16000),
    (420.0, 90.0, 12000),
    (180.0, 300.0, 18000),
    (450.0, 320.0, 9000),
    (300.0, 200.0, 14000),
    (90.0, 220.0, 11000),
    (520.0, 210.0, 13000),
    (260.0, 90.0, 10000),
    (360.0, 330.0, 15000),
    (230.0, 250.0, 8000),
]


def shifted_frame(dx: float, dy: float, seed: int = 1) -> np.ndarray:
    from tests.server.test_field_units import gaussian_frame

    stars = [(x + dx, y + dy, peak) for x, y, peak in TRACK_STARS]
    return gaussian_frame((400, 600), stars, sigma=2.0, seed=seed)


def feed(client, seq: int, frame: np.ndarray) -> dict:
    client.hub.field.on_frame(seq, frame, "file")
    settle(client)
    transform = client.get("/api/field/transform", headers=AUTH).json()
    assert transform["frame_seq"] == seq
    return transform


def test_a_role_change_keeps_the_tracked_pose(field_client, tmp_path):
    """The science review's high finding: a role after a drift kept the identity."""
    open_and_solve(field_client, tmp_path, shifted_frame(0.0, 0.0))
    for step in range(1, 4):  # 10 frame px per frame (5 green px)
        transform = feed(field_client, 10_000 + step, shifted_frame(8.0 * step, -6.0 * step, step))
    assert transform["dx"] == pytest.approx(24.0, abs=0.3)
    # A comparison at the third synthetic star's reference position.
    ra_h, dec_deg = field_client.hub.field._wcs.pixel_to_radec(*to_green_xy(180.0, 300.0))
    star = {"ra_deg": ra_h * 15.0, "dec_deg": dec_deg, "name": "C1"}
    response = field_client.post(
        "/api/targets", json={"star": star, "role": "comparison"}, headers=AUTH
    )
    assert response.status_code == 200, response.text
    settle(field_client)
    transform = feed(field_client, 10_010, shifted_frame(32.0, -24.0, 9))
    assert transform["dx"] == pytest.approx(32.0, abs=0.3)
    assert transform["dy"] == pytest.approx(-24.0, abs=0.3)
    assert transform["tracking"] == "ok"


def to_green_xy(x: float, y: float) -> tuple[float, float]:
    from argos.server.field_solve import to_green

    return to_green(x, y)


def test_a_lost_lock_is_reported_and_found_again(field_client, tmp_path):
    """The science review's high finding: a loss was silent and permanent."""
    open_and_solve(field_client, tmp_path, shifted_frame(0.0, 0.0))
    transform = feed(field_client, 10_001, shifted_frame(4.0, 2.0, 2))
    assert transform["tracking"] == "ok" and transform["anchors"] >= 3
    from tests.server.test_field_units import gaussian_frame

    blank = gaussian_frame((400, 600), [], sigma=2.0, seed=3)
    for seq in (10_002, 10_003):
        transform = feed(field_client, seq, blank)
        assert transform["tracking"] == "lost" and transform["anchors"] == 0
    lost = [m for m in log_messages(field_client) if m.startswith("Tracking: no anchor star")]
    assert len(lost) == 1  # once per loss, not per frame
    # A jump far beyond the centroid windows (a Seestar re-centre): re-acquired.
    transform = feed(field_client, 10_004, shifted_frame(64.0, -46.0, 4))
    assert transform["tracking"] == "ok"
    assert transform["dx"] == pytest.approx(64.0, abs=0.3)
    assert transform["dy"] == pytest.approx(-46.0, abs=0.3)
    assert any(m.startswith("Tracking: field found again") for m in log_messages(field_client))


# -- a real frame with the installed ASTAP ------------------------------------------------


def _real_frame() -> Path | None:
    explicit = os.environ.get("ARGOS_TEST_REAL_FRAME")
    if explicit:
        return Path(explicit) if Path(explicit).is_file() else None
    root = Path.home() / "Argos" / "sessions"
    if not root.is_dir():
        return None
    return next(iter(sorted(root.glob("*/lights/*.fit"))), None)


@pytest.mark.skipif(find_astap() is None, reason="ASTAP is not installed")
def test_a_real_frame_is_solved_by_astap(make_client, tmp_path):
    source = _real_frame()
    if source is None:
        pytest.skip("no real raw frame (set ARGOS_TEST_REAL_FRAME or keep ~/Argos/sessions)")
    copy = tmp_path / "real.fit"
    shutil.copyfile(source, copy)  # read-only source, solved from a copy
    client = science_client(make_client, tmp_path)
    client.app.state.hub.field.catalog_api = FakeCatalog()
    client.patch("/api/config", json={"catalog.show_cached_exoplanets": False}, headers=AUTH)
    response = client.post("/api/camera/open-fits", json={"path": str(copy)}, headers=AUTH)
    assert response.status_code == 200, response.text
    wait_for(lambda: client.app.state.hub.field._frame is not None)
    response = client.post("/api/field/solve", headers=AUTH)
    job = wait_job(client, response.json()["job_id"], timeout=180.0)
    assert job["state"] == "done", job
    field = client.get("/api/field", headers=AUTH).json()
    solution = field["solution"]
    hint = solution["hint"]
    if hint is not None:  # the Seestar pointing is within a degree or two of the solve
        sep = math.degrees(
            math.acos(
                min(
                    1.0,
                    math.sin(math.radians(hint["dec_deg"]))
                    * math.sin(math.radians(solution["dec_deg"]))
                    + math.cos(math.radians(hint["dec_deg"]))
                    * math.cos(math.radians(solution["dec_deg"]))
                    * math.cos(math.radians(15 * (hint["ra_hours"] - solution["ra_hours"]))),
                )
            )
        )
        assert sep < 3.0
    assert 1.0 < solution["scale_arcsec_px"] < 10.0
    assert field["wcs"]["frame_shape"] == solution["frame_shape"]
    _ = SimpleNamespace  # keep the import used when this test is skipped
