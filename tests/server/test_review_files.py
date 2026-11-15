"""Wave 7, Review: the frame inspector's file routes (rows A71-A75).

The frame is a synthetic 160 x 120 raw with stars at known green positions; the
solve runs the fake ASTAP of the field tests (its WCS fits this geometry) and the
catalogue the injected fake queries: no network, no real ASTAP.
"""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path

import numpy as np
import pytest

from argos.core.catalog.targets import TargetSet, TargetStar
from argos.core.imaging.metrics import TRACK_SNAP_SEARCH, measure_star_at
from argos.server import files as files_module
from argos.server.field_solve import SolveCancelled, to_frame
from tests.server.conftest import AUTH, decode_frame, wait_for
from tests.server.test_field import GREEN_WCS, FakeAstap, FakeCatalog

#: Stars at green-plane positions (x, y) with peak amplitudes.
STARS = ((20.0, 15.0, 9000.0), (62.0, 45.0, 5000.0), (40.3, 30.6, 20000.0))


def _raw_frame(seed: int = 3) -> np.ndarray:
    rng = np.random.default_rng(seed)
    raw = rng.normal(1200.0, 6.0, size=(120, 160))
    yy, xx = np.mgrid[0:120, 0:160]
    for gx, gy, amp in STARS:
        fx, fy = to_frame(gx, gy)
        raw += amp * np.exp(-((xx - fx) ** 2 + (yy - fy) ** 2) / (2 * 2.2**2))
    return raw.clip(0, 65535).astype(np.uint16)


def write_frame(path: Path, data: np.ndarray | None = None, **cards) -> Path:
    from astropy.io import fits

    header = fits.Header()
    header["DATE-OBS"] = "2026-09-25T20:04:56.567"
    header["EXPTIME"] = 10.0
    header["FILTER"] = "IR"
    header["IMAGETYP"] = "Light Frame"
    header["OBJECT"] = "XX Test"
    header["SOFTWARE"] = "Argos v0.5.0"
    header["BAYERPAT"] = "GRBG"
    header["OBJCTRA"] = "19 25 27.9"
    header["OBJCTDEC"] = "+42 47 03"
    for key, value in cards.items():
        header[key.replace("_", "-")] = value
    path.parent.mkdir(parents=True, exist_ok=True)
    fits.PrimaryHDU(data=_raw_frame() if data is None else data, header=header).writeto(path)
    return path


@pytest.fixture
def files_client(client, tmp_path):
    root = tmp_path / "sessions"
    root.mkdir()
    astap = FakeAstap(tmp_path / "astap")
    db = tmp_path / "astap-db"
    db.mkdir()
    response = client.patch(
        "/api/config",
        json={
            "sessions_path": str(root),
            "astrometry.astap_path": str(astap.path),
            "astrometry.database": "D50",
            "astrometry.database_path": str(db),
            "catalog.show_cached_exoplanets": False,
            "catalog.display_mag_limit": 12.0,
            "catalog.field_stars_mag_limit": 18.0,
        },
        headers=AUTH,
    )
    assert response.status_code == 200, response.text
    hub = client.app.state.hub
    hub.files.catalog_api = FakeCatalog()
    client.root = root  # type: ignore[attr-defined]
    client.hub = hub  # type: ignore[attr-defined]
    client.astap = astap  # type: ignore[attr-defined]
    return client


def _job(client, response, timeout: float = 15.0) -> dict:
    assert response.status_code == 202, response.text
    job_id = response.json()["job_id"]
    return wait_for(
        lambda: (
            job
            if (job := client.get(f"/api/jobs/{job_id}", headers=AUTH).json())["state"]
            in ("done", "failed", "cancelled")
            else None
        ),
        timeout=timeout,
    )


# ---------------------------------------------------------------------------
# A71
# ---------------------------------------------------------------------------


def test_frame_binary_layout_and_header(files_client):
    path = write_frame(files_client.root / "s" / "lights" / "f_00001.fit")
    response = files_client.get("/api/files/frame", params={"path": str(path)}, headers=AUTH)
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/octet-stream"
    header, pixels = decode_frame(response.content)
    assert np.array_equal(pixels, _raw_frame())
    assert header["source"] == "file" and header["origin"] == "file"
    assert header["path"] == str(path) and header["file_name"] == "f_00001.fit"
    assert header["exposure_s"] == 10.0
    assert header["date_obs"] == "2026-09-25T20:04:56.567"
    assert header["epoch_utc"] == "2026-09-25T20:05:01.567Z"  # DATE-OBS + EXPTIME/2
    assert header["bayer"] == "GRBG" and header["raw"] is True
    assert header["green_shape"] == [60, 80]
    assert header["filter"] == "IR" and header["image_type"] == "Light Frame"
    second = files_client.get("/api/files/frame", params={"path": str(path)}, headers=AUTH)
    assert decode_frame(second.content)[0]["seq"] == header["seq"] + 1


def test_frame_not_on_ws_frames(files_client):
    path = write_frame(files_client.root / "f.fits")
    bus = files_client.hub.bus
    assert bus._latest_frame is None
    assert files_client.get("/api/files/frame", params={"path": str(path)}, headers=AUTH).is_success
    assert bus._latest_frame is None  # the live image (and every /ws/frames client) untouched


def test_frame_float_file_is_displayed_not_raw(files_client):
    data = (_raw_frame().astype(np.float32) / 65535.0).astype(np.float32)
    path = write_frame(files_client.root / "calibrated.fits", data=data)
    header, pixels = decode_frame(
        files_client.get("/api/files/frame", params={"path": str(path)}, headers=AUTH).content
    )
    assert header["raw"] is False
    assert abs(int(pixels.max()) - int(_raw_frame().max())) <= 1


def test_frame_errors(files_client):
    path = write_frame(files_client.root / "f.fit")
    bad_view = files_client.get(
        "/api/files/frame", params={"path": str(path), "view": "colour"}, headers=AUTH
    )
    assert bad_view.status_code == 400
    junk = files_client.root / "junk.fits"
    junk.write_bytes(b"not a fits file at all")
    answer = files_client.get("/api/files/frame", params={"path": str(junk)}, headers=AUTH)
    assert answer.status_code == 400 and answer.json()["error"]["code"] == "invalid_fits"
    txt = files_client.root / "a.txt"
    txt.write_text("x")
    assert (
        files_client.get("/api/files/frame", params={"path": str(txt)}, headers=AUTH).status_code
        == 400
    )
    missing = files_client.get(
        "/api/files/frame", params={"path": str(files_client.root / "no.fit")}, headers=AUTH
    )
    assert missing.status_code == 404
    outside = files_client.get("/api/files/frame", params={"path": "/etc/x.fit"}, headers=AUTH)
    assert outside.status_code == 403


# ---------------------------------------------------------------------------
# A72
# ---------------------------------------------------------------------------


def test_fits_header(files_client):
    path = write_frame(files_client.root / "f.fit", CCD_TEMP=19.5, AIRMASS=1.03)
    record = files_client.get(
        "/api/files/fits-header", params={"path": str(path)}, headers=AUTH
    ).json()
    lines = record["text"].splitlines()
    assert lines[0].startswith("SIMPLE  =")
    assert all(len(line) <= 80 for line in lines)
    cards = {c["key"]: c for c in record["cards"]}
    assert cards["EXPTIME"]["value"] == 10.0 and cards["NAXIS1"]["value"] == 160
    assert record["keywords"]["OBJECT"] == "XX Test"
    assert record["keywords"]["CCD-TEMP"] == "19.5"
    assert "SOFTWARE" not in record["keywords"]  # not one of read_fits_meta's keys


def test_fits_header_equals_qt(files_client):
    pytest.importorskip("PyQt6.QtWidgets")
    from argos.ui.analysis_window import read_fits_header_text, read_fits_meta

    path = write_frame(files_client.root / "f.fit", CCD_TEMP=19.5, AIRMASS=1.03, ORIGIN="Test")
    record = files_client.get(
        "/api/files/fits-header", params={"path": str(path)}, headers=AUTH
    ).json()
    assert record["keywords"] == read_fits_meta(str(path))
    assert record["text"].replace("\n", "") == read_fits_header_text(str(path)).rstrip()


# ---------------------------------------------------------------------------
# A73
# ---------------------------------------------------------------------------


def test_measure_star_equals_the_core(files_client):
    path = write_frame(files_client.root / "f.fit")
    fx, fy = to_frame(40.0, 31.0)
    record = files_client.post(
        "/api/files/measure-star", json={"path": str(path), "x": fx, "y": fy}, headers=AUTH
    ).json()
    assert record["found"] is True
    arr = files_module.read_fits_2d(path)
    core = measure_star_at(arr, 40.0, 31.0, 5)
    assert record["x_green"] == core.x and record["y_green"] == core.y
    assert record["fwhm_px"] == 2.0 * core.fwhm and record["hfd_px"] == 2.0 * core.hfd
    assert record["snr"] == core.snr and record["peak_adu"] == core.peak_adu
    assert record["sky_adu"] == core.sky_adu and record["eccentricity"] == core.eccentricity
    assert record["flux"] == core.flux and record["radius_green_px"] == 5
    assert (record["x"], record["y"]) == tuple(round(v, 2) for v in to_frame(core.x, core.y))
    assert record["scale_source"] == "profile" and record["ra_hours"] is None
    # snap false: the tracking search radius; a custom radius
    near = files_client.post(
        "/api/files/measure-star",
        json={"path": str(path), "x": fx, "y": fy, "radius": 4, "snap": False},
        headers=AUTH,
    ).json()
    core2 = measure_star_at(arr, 40.0, 31.0, 4, search=TRACK_SNAP_SEARCH)
    assert near["x_green"] == core2.x and near["hfd_px"] == 2.0 * core2.hfd


def test_measure_star_nothing_and_outside(files_client):
    path = write_frame(files_client.root / "f.fit", data=np.full((120, 160), 1000, np.uint16))
    empty = files_client.post(
        "/api/files/measure-star", json={"path": str(path), "x": 50, "y": 50}, headers=AUTH
    )
    assert empty.status_code == 200
    assert empty.json() == {"found": False, "message": "No star near (50, 50)."}
    outside = files_client.post(
        "/api/files/measure-star", json={"path": str(path), "x": 500.0, "y": 5.0}, headers=AUTH
    )
    assert outside.status_code == 400
    bad = files_client.post(
        "/api/files/measure-star", json={"path": str(path), "x": "1", "y": 5.0}, headers=AUTH
    )
    assert bad.status_code == 400


def test_read_fits_2d_equals_qt(files_client):
    pytest.importorskip("PyQt6.QtWidgets")
    from argos.ui.analysis_window import read_fits_2d as qt_read

    for data in (_raw_frame(), _raw_frame().astype(np.float32) / 65535.0):
        path = write_frame(files_client.root / f"f{data.dtype}.fits", data=data)
        assert np.array_equal(files_module.read_fits_2d(path), qt_read(str(path)))


# ---------------------------------------------------------------------------
# A74, A75
# ---------------------------------------------------------------------------


def _session_frame(client) -> Path:
    session = client.root / "20260925T200453Z_XX_Test"
    path = write_frame(session / "lights" / "f_00001.fit")
    (session / "session.json").write_text('{"frames": []}')
    tset = TargetSet(object_name="XX Test")
    ra, dec = GREEN_WCS.pixel_to_world_deg(40.0, 30.0)
    tset.set_role(TargetStar("target", float(ra), float(dec), auid="000-BCD-123", name="RR Lyr"))
    tset.save(session / "targets.json")
    return path


def test_solve_then_measure_and_catalogue(files_client):
    path = _session_frame(files_client)
    none = files_client.get("/api/files/solution", params={"path": str(path)}, headers=AUTH)
    assert none.status_code == 404
    not_solved = files_client.post("/api/files/catalogue", json={"path": str(path)}, headers=AUTH)
    assert not_solved.status_code == 409 and not_solved.json()["error"]["code"] == "not_solved"
    job = _job(
        files_client, files_client.post("/api/files/solve", json={"path": str(path)}, headers=AUTH)
    )
    assert job["state"] == "done", job
    assert job["kind"] == "file_solve"
    result = job["result"]
    solution = result["solution"]
    assert solution["frame_shape"] == [120, 160]
    assert solution["hint"]["source"] == "header"
    assert solution["summary"].startswith("Field identified — RA")
    assert result["wcs"]["crpix"] == [2 * 40.5 - 0.5, 2 * 30.5 - 0.5]
    # ASTAP was hinted by OBJCTRA / OBJCTDEC
    call = files_client.astap.calls()[-1]
    assert "-ra" in call and "-spd" in call
    assert (
        files_client.get("/api/files/solution", params={"path": str(path)}, headers=AUTH).json()
        == result
    )
    # A73 now gives RA / Dec and the solved scale
    fx, fy = to_frame(40.0, 31.0)
    meas = files_client.post(
        "/api/files/measure-star", json={"path": str(path), "x": fx, "y": fy}, headers=AUTH
    ).json()
    assert meas["scale_source"] == "solution"
    assert meas["scale_arcsec_px"] == pytest.approx(7.35 / 2.0)
    ra, dec = GREEN_WCS.pixel_to_radec(meas["x_green"], meas["y_green"])
    assert meas["ra_hours"] == pytest.approx(ra) and meas["dec_deg"] == pytest.approx(dec)
    # A75
    cat = _job(
        files_client,
        files_client.post("/api/files/catalogue", json={"path": str(path)}, headers=AUTH),
    )
    assert cat["state"] == "done", cat
    layers = cat["result"]["layers"]
    assert {m["id"] for m in layers["vsp"]} == {"vsp:0", "vsp:1"}
    # Every fetched Gaia star (G 11.0 merged into G 9.4 within 8 green px, Qt's rule);
    # the count applies the display limit 12 (G 12.5 left out), the markers do not.
    assert sorted(m["g_mag"] for m in layers["stars"]) == [9.4, 12.5]
    assert cat["result"]["counts"]["stars"] == 1
    assert [m["role"] for m in layers["selected"]] == ["target"]
    assert cat["result"]["catalog"]["counts"]["variables"] == 1
    vsp_call = next(c for c in files_client.hub.files.catalog_api.calls if c[0] == "vsp")
    assert vsp_call[2]["target_name"] == "RR Lyr"
    # the file changed: its solution is gone
    os.utime(path, ns=(time.time_ns(), time.time_ns() + 10_000_000))
    gone = files_client.get("/api/files/solution", params={"path": str(path)}, headers=AUTH)
    assert gone.status_code == 404


def test_solve_failure_and_cancel_kills_astap(files_client):
    path = write_frame(files_client.root / "f.fit")
    files_client.astap.set("fail")
    job = _job(
        files_client, files_client.post("/api/files/solve", json={"path": str(path)}, headers=AUTH)
    )
    assert job["state"] == "failed"
    assert job["error"] == {"code": "not_solved", "message": "No solution found"}
    files_client.astap.set("solve", sleep=30)
    started = files_client.post("/api/files/solve", json={"path": str(path)}, headers=AUTH)
    job_id = started.json()["job_id"]
    wait_for(
        lambda: files_client.get(f"/api/jobs/{job_id}", headers=AUTH).json()["stage"] == "ASTAP"
    )
    busy = files_client.post("/api/files/solve", json={"path": str(path)}, headers=AUTH)
    assert busy.status_code == 409 and busy.json()["error"]["owner"] == job_id
    t0 = time.monotonic()
    files_client.delete(f"/api/jobs/{job_id}", headers=AUTH)
    job = wait_for(
        lambda: (
            j
            if (j := files_client.get(f"/api/jobs/{job_id}", headers=AUTH).json())["state"]
            != "running"
            else None
        ),
        timeout=5,
    )
    assert job["state"] == "cancelled"
    assert time.monotonic() - t0 < 3.0  # killed, not waited for (30 s)


def test_solve_cancel_before_astap(files_client, monkeypatch):
    path = write_frame(files_client.root / "f.fit")

    def fake(green, settings, cancel, progress=None):
        cancel.wait(5)
        raise SolveCancelled()

    monkeypatch.setattr(files_module, "solve_green", fake)
    started = files_client.post("/api/files/solve", json={"path": str(path)}, headers=AUTH)
    files_client.delete(f"/api/jobs/{started.json()['job_id']}", headers=AUTH)
    job = _job(files_client, started)
    assert job["state"] == "cancelled"


def test_solve_cancel_as_astap_ends_keeps_nothing(files_client, monkeypatch):
    """A cancel that lands after ASTAP answered (a hinted solve takes 0.1 s on the owner's
    frames) still ends ``cancelled`` and keeps no solution (smoke run, 2026-11-15)."""
    path = write_frame(files_client.root / "f.fit")
    real = files_module.solve_green

    def late(green, settings, cancel, progress=None):
        result = real(green, settings, cancel, progress)
        cancel.set()  # the DELETE arrives now, ASTAP already gone
        return result

    monkeypatch.setattr(files_module, "solve_green", late)
    job = _job(
        files_client, files_client.post("/api/files/solve", json={"path": str(path)}, headers=AUTH)
    )
    assert job["state"] == "cancelled" and job["result"] is None
    gone = files_client.get("/api/files/solution", params={"path": str(path)}, headers=AUTH)
    assert gone.status_code == 404


def test_catalogue_cancel_and_failure(files_client):
    path = _session_frame(files_client)
    assert (
        _job(
            files_client,
            files_client.post("/api/files/solve", json={"path": str(path)}, headers=AUTH),
        )["state"]
        == "done"
    )
    api = files_client.hub.files.catalog_api
    gate = threading.Event()
    real = api.vsx_cone_search

    def slow(*args, **kwargs):
        gate.wait(10)
        return real(*args, **kwargs)

    api.vsx_cone_search = slow
    started = files_client.post("/api/files/catalogue", json={"path": str(path)}, headers=AUTH)
    t0 = time.monotonic()
    files_client.delete(f"/api/jobs/{started.json()['job_id']}", headers=AUTH)
    job = _job(files_client, started, timeout=5)
    assert job["state"] == "cancelled" and time.monotonic() - t0 < 2.0
    gate.set()
    from argos.core.catalog import CatalogError

    def broken(*args, **kwargs):
        raise CatalogError("VSX unreachable")

    api.vsx_cone_search = broken
    failed = _job(
        files_client,
        files_client.post("/api/files/catalogue", json={"path": str(path)}, headers=AUTH),
    )
    assert failed["state"] == "failed"
    assert failed["error"] == {"code": "lookup_failed", "message": "VSX unreachable"}


# ---------------------------------------------------------------------------
# W7 technical review: size before pixels, counts of a [0, 1] frame, truncated files
# ---------------------------------------------------------------------------


def _huge_header_only(path: Path) -> Path:
    """A FITS whose header announces 20 000 × 20 000 pixels and holds none of them."""
    from astropy.io import fits

    header = fits.Header()
    header["SIMPLE"] = True
    header["BITPIX"] = 16
    header["NAXIS"] = 2
    header["NAXIS1"] = 20000
    header["NAXIS2"] = 20000
    path.write_bytes(header.tostring().encode("ascii"))
    return path


def test_read_fits_2d_refuses_a_huge_frame_from_its_header(tmp_path):
    """read_fits_2d chose the HDU with ``getattr(h, "data")``, which reads every pixel
    before the size check (a 578 MB frame took 400 MB of RSS before the refusal)."""
    from argos.server.fits_source import FitsReadError

    path = _huge_header_only(tmp_path / "huge.fit")
    with pytest.raises(FitsReadError, match="too large"):
        files_module.read_fits_2d(path)


def test_measure_star_on_a_frame_in_0_1_reads_counts(files_client):
    """A calibrated float frame in [0, 1] (Siril's r_light) gave SNR 0 and peak 0: it is
    scaled by 65535 as the display and the solve are (Qt: S65), and the answer says so."""
    raw = _raw_frame().astype(np.float32)
    counts = write_frame(files_client.root / "counts.fit", data=raw)
    unit = write_frame(files_client.root / "unit.fit", data=raw / np.float32(65535.0))
    fx, fy = to_frame(40.0, 31.0)
    a = files_client.post(
        "/api/files/measure-star", json={"path": str(counts), "x": fx, "y": fy}, headers=AUTH
    ).json()
    b = files_client.post(
        "/api/files/measure-star", json={"path": str(unit), "x": fx, "y": fy}, headers=AUTH
    ).json()
    assert a["scale"] == "raw" and b["scale"] == "converted"
    assert b["snr"] > 100 and b["snr"] == pytest.approx(a["snr"], rel=0.01)
    assert abs(b["peak_adu"] - a["peak_adu"]) <= 1


def test_solve_of_a_truncated_file_is_invalid_fits(files_client):
    """A74 caught FitsReadError only: astropy's ValueError on a truncated file ended the
    job as internal_error, against the documented invalid_fits."""
    path = write_frame(files_client.root / "f.fit")
    data = path.read_bytes()
    path.write_bytes(data[: len(data) // 2])
    job = _job(
        files_client, files_client.post("/api/files/solve", json={"path": str(path)}, headers=AUTH)
    )
    assert job["state"] == "failed" and job["error"]["code"] == "invalid_fits", job
