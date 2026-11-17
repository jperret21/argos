"""Wave 7, Review: sessions, curves, CSV import and the live source (rows A67-A70).

Synthetic sessions in a temporary sessions folder; the Qt reader's own results
(``argos.core.session.review``, which needs PyQt6) are the parity reference where
PyQt6 is installed.
"""

from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest

from argos.core.catalog.targets import TargetSet, TargetStar
from argos.core.imaging.sky_geometry import horizontal_at
from argos.core.photometry.airmass import julian_date
from argos.core.photometry.lightcurve import LcPoint, LightCurve, write_curves_csv
from argos.server import review as review_module
from tests.server.conftest import AUTH, wait_for

START = datetime(2026, 9, 25, 20, 4, 56, 567000, tzinfo=timezone.utc)
CADENCE_S = 22.0
EXPTIME = 10.0
#: A made-up site and pointing (never the owner's).
SITE = (12.0, 34.0)
RA_H, DEC = 19.42, 42.78
TARGET = TargetStar("target", 291.3, 42.78, auid="000-AAA-001", name="XX Test", source="vsx")
COMP = TargetStar(
    "comparison", 291.35, 42.8, auid="000-AAA-002", name="111", source="vsp", chart_id="X1"
)
CHECK = TargetStar(
    "check", 291.32, 42.7, auid="000-AAA-003", name="123", source="vsp", mags={"V": 12.3}
)


def _write_fits(path: Path, when: datetime, *, filt: str, site=SITE, altaz=None, airmass=1.2):
    from astropy.io import fits

    rng = np.random.default_rng(int(when.timestamp()) % 1000)
    data = rng.normal(1000, 5, size=(120, 160)).clip(0, 65535).astype(np.uint16)
    jd = julian_date(when)
    alt, az = altaz or horizontal_at(jd, RA_H, DEC, *site)
    header = fits.Header()
    header["DATE-OBS"] = when.isoformat(timespec="milliseconds").replace("+00:00", "")
    header["EXPTIME"] = EXPTIME
    header["FILTER"] = filt
    header["IMAGETYP"] = "Light Frame"
    header["OBJECT"] = "XX Test"
    header["RA"] = RA_H
    header["DEC"] = DEC
    header["ALTITUDE"] = alt
    header["AZIMUTH"] = az
    header["AIRMASS"] = airmass
    header["SITELAT"] = site[0]
    header["SITELONG"] = site[1]
    header["SOFTWARE"] = "Argos v0.5.0"
    header["BAYERPAT"] = "GRBG"
    header["CCD-TEMP"] = 19.5
    fits.PrimaryHDU(data=data, header=header).writeto(path)


def make_session(
    root: Path,
    folder: str = "20260925T200453Z_XX_Test",
    *,
    filters: tuple[str, ...] = ("V", "V", "V", "V"),
    names: str = "s49",
    header_site=SITE,
    with_dark: bool = True,
    recorder: bool = True,
) -> Path:
    """A session of len(filters) lights (+ a dark), its curves, targets and recorder."""
    path = root / folder
    lights = path / "lights"
    lights.mkdir(parents=True)
    frames = []
    times = [START + timedelta(seconds=CADENCE_S * i) for i in range(len(filters))]
    for i, (when, filt) in enumerate(zip(times, filters)):
        name = f"XX_Test_{filt.lower()}_light_{i + 1:05d}.fit"
        # The mount's direction for the TRUE site; the header site may be another.
        altaz = horizontal_at(julian_date(when), RA_H, DEC, *SITE)
        _write_fits(lights / name, when, filt=filt, site=header_site, altaz=altaz)
        frames.append(
            {
                "filename": name,
                "image_type": "Light Frame",
                "filter_name": filt,
                "exposure_s": EXPTIME,
                "gain": 80,
                "timestamp": when.isoformat(),
                "hfd": 3.1,
                "fwhm": 2.1,
                "star_count": 100,
                "sky_adu": 1000.0,
                "peak_adu": 4000,
                "eccentricity": 0.2,
            }
        )
    if with_dark:
        frames.append(
            {
                "filename": "XX_Test_dark_00001.fit",
                "image_type": "Dark Frame",
                "filter_name": "Dark",
                "exposure_s": EXPTIME,
                "gain": 80,
                "timestamp": (times[-1] + timedelta(seconds=60)).isoformat(),
            }
        )
        _write_fits(lights / "XX_Test_dark_00001.fit", times[-1], filt="Dark")
    document = {
        "schema": 1,
        "object": "XX Test",
        "software": "Argos v0.5.0",
        "started_utc": START.isoformat(),
        "observer": "Test Observer",
        "summary": {"frame_count": len(frames)},
        "frames": frames,
    }
    (path / "session.json").write_text(json.dumps(document), encoding="utf-8")
    tset = TargetSet(object_name="XX Test")
    for star in (TARGET, COMP, CHECK):
        tset.set_role(star)
    tset.save(path / "targets.json")
    (path / "observation.json").write_text(json.dumps({"kind": "transit_or_var"}))

    photometry = path / "photometry"
    photometry.mkdir()
    curves: dict[tuple[str, str], LightCurve] = {}
    for i, (when, filt) in enumerate(zip(times, filters)):
        mid = when + timedelta(seconds=EXPTIME / 2)
        jd = julian_date(mid)
        for star, base in ((TARGET, 7.3), (COMP, 9.1), (CHECK, 10.2)):
            lc = curves.setdefault(
                (star.role, filt),
                LightCurve(auid=star.auid, name=star.display_name, role=star.role),
            )
            lc.append(
                LcPoint(
                    jd_utc=jd,
                    mag=base + 0.01 * i,
                    mag_err=0.02,
                    bjd_tdb=None if i == 0 else jd + 0.002,
                    airmass=1.5 + 0.01 * i,
                    fwhm=2.16,
                    sky_adu=1000.0,
                    comps_used=1,
                    suspect=(star is TARGET and i == 1),
                    formal_mag_err=0.012,
                    sigma_syst=0.016,
                    relative_flux=0.5,
                    relative_flux_err=0.001,
                    relative_comps_used=1,
                )
            )
    for (role, filt), lc in curves.items():
        star = {"target": TARGET, "comparison": COMP, "check": CHECK}[role]
        if names == "s49":
            name = f"{role}_XX_Test_{filt.lower()}_{star.auid}.csv"
        else:
            name = f"{role}_XX_Test_{star.auid}.csv"
        lc.to_csv(photometry / name)
    if recorder:
        _write_recorder(path / "diagnostics" / "XX_Test_live_diagnostics.jsonl", times)
    return path


def _write_recorder(
    path: Path,
    times: list[datetime],
    blank: int = 2,
    few_anchors: int | None = None,
    comp_snr: float | None = None,
) -> None:
    """Frame *blank* measured on blank sky: target SNR 1.5, zero point 5 mag off.

    Two more comparisons steer the tracker (records only, no curve): every frame has 3
    anchors at SNR 10 or more, except *few_anchors*, where they read SNR 6 (S56's rule).
    *comp_snr*: every comparison at that SNR instead (S71's faint ensemble).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for i, when in enumerate(times):
        jd = round(julian_date(when + timedelta(seconds=EXPTIME / 2)), 4)
        snr_t = 1.5 if i == blank else 120.0
        extra = 6.0 if i == few_anchors else (comp_snr or 80.0)
        for auid in ("000-AAA-004", "000-AAA-005"):
            lines.append(
                {"kind": "star", "frame": i, "auid": auid, "name": auid, "role": "comparison"}
                | {"snr": extra, "saturated": False, "measured": True}
            )
        comp = 2.0 if i == 3 else (comp_snr or 90.0)
        for star, snr in ((TARGET, snr_t), (COMP, comp), (CHECK, 60.0)):
            lines.append(
                {
                    "kind": "star",
                    "frame": i,
                    "auid": star.auid,
                    "name": star.display_name,
                    "role": star.role,
                    "snr": snr,
                    "measured": True,
                }
            )
        lines.append({"kind": "frame", "frame": i, "jd_utc": jd, "airmass": 1.1, "fwhm": 2.16})
        for star in (TARGET, CHECK):
            zp = 14.4 if (i == blank and star is TARGET) else 19.4 + 0.01 * i
            lines.append(
                {
                    "kind": "ensemble",
                    "frame": i,
                    "target": star.auid,
                    "zp": zp,
                    "zp_rms": 0.01,
                    "comps_used": 1,
                }
            )
    path.write_text("".join(json.dumps(line) + "\n" for line in lines))


@pytest.fixture
def review_client(client, tmp_path):
    root = tmp_path / "sessions"
    root.mkdir()
    response = client.patch("/api/config", json={"sessions_path": str(root)}, headers=AUTH)
    assert response.status_code == 200, response.text
    client.root = root  # type: ignore[attr-defined]
    client.hub = client.app.state.hub  # type: ignore[attr-defined]
    return client


def run_job(client, response, timeout: float = 10.0) -> dict:
    assert response.status_code == 202, response.text
    job_id = response.json()["job_id"]

    def finished():
        job = client.get(f"/api/jobs/{job_id}", headers=AUTH).json()
        return job if job["state"] in ("done", "failed", "cancelled") else None

    return wait_for(finished, timeout=timeout)


# ---------------------------------------------------------------------------
# A68: open
# ---------------------------------------------------------------------------


def test_open_job_reads_session_headers_and_checks(review_client):
    path = make_session(review_client.root)
    job = run_job(
        review_client,
        review_client.post("/api/review/session", json={"path": str(path)}, headers=AUTH),
    )
    assert job["state"] == "done", job
    assert job["kind"] == "session_open"
    # The job's result names the open (it travels in every job event); the record is
    # read from the cache the open filled.
    summary = job["result"]
    assert set(summary) == {"path", "folder", "object", "revision", "counts", "readiness"}
    record = review_client.get(
        "/api/review/session", params={"path": str(path)}, headers=AUTH
    ).json()
    assert summary["revision"] == record["revision"] and summary["path"] == record["path"]
    assert summary["readiness"] == record["readiness"]
    assert record["object"] == "XX Test"
    assert record["source"] == {"kind": "session", "path": str(path)}
    assert record["counts"]["frames"] == 5 and record["counts"]["lights"] == 4
    assert record["counts"]["image_types"] == {"Light Frame": 4, "Dark Frame": 1}
    assert record["metadata"] == {"kind": "transit_or_var"}
    assert record["summary"] == {"frame_count": 5}
    first = record["frames"][0]
    assert first["path"].endswith(first["filename"])
    assert first["ccd_temp"] == 19.5
    assert first["filter"] == "v" and first["light"] is True
    assert first["header"]["airmass"] == 1.2
    mid = START + timedelta(seconds=EXPTIME / 2)
    assert first["header"]["jd_mid"] == pytest.approx(julian_date(mid), abs=1e-9)
    assert record["targets"]["chart_id"] == "X1"
    assert {s["role"] for s in record["targets"]["stars"]} == {"target", "comparison", "check"}
    assert record["site_check"]["state"] == "ok"
    assert record["airmass_source"] == "csv"
    assert record["diagnostics"] == {"file": "XX_Test_live_diagnostics.jsonl", "frames": 4}
    codes = [i["code"] for i in record["readiness"]["issues"]]
    assert codes == ["flagged_points"]
    assert record["readiness"]["state"] == "warnings"
    # A GET serves the same open (cached) without a new job.
    again = review_client.get("/api/review/session", params={"path": str(path)}, headers=AUTH)
    assert again.status_code == 200
    assert again.json()["opened_utc"] == record["opened_utc"]
    # session.json given instead of the folder
    via_file = review_client.get(
        "/api/review/session", params={"path": str(path / "session.json")}, headers=AUTH
    )
    assert via_file.json()["path"] == str(path)


def test_open_progress_reports_headers(review_client, monkeypatch):
    path = make_session(review_client.root)
    seen = []
    real = review_module.read_frame_header

    def slow(p):
        time.sleep(0.15)
        return real(p)

    monkeypatch.setattr(review_module, "read_frame_header", slow)
    response = review_client.post("/api/review/session", json={"path": str(path)}, headers=AUTH)
    job_id = response.json()["job_id"]

    def sample():
        job = review_client.get(f"/api/jobs/{job_id}", headers=AUTH).json()
        seen.append((job["stage"], job["done"], job["total"]))
        return job["state"] == "done"

    wait_for(sample, timeout=10, interval=0.05)
    assert ("headers", 5, 5) in seen or any(s[0] == "headers" and s[2] == 5 for s in seen)


def test_open_cancel_and_busy(review_client, monkeypatch):
    path = make_session(review_client.root)
    gate = threading.Event()
    real = review_module.read_frame_header

    def blocking(p):
        gate.wait(5)
        return real(p)

    monkeypatch.setattr(review_module, "read_frame_header", blocking)
    first = review_client.post("/api/review/session", json={"path": str(path)}, headers=AUTH)
    assert first.status_code == 202
    busy = review_client.post("/api/review/session", json={"path": str(path)}, headers=AUTH)
    assert busy.status_code == 409
    assert busy.json()["error"]["code"] == "busy"
    assert busy.json()["error"]["owner"] == first.json()["job_id"]
    review_client.delete(f"/api/jobs/{first.json()['job_id']}", headers=AUTH)
    gate.set()
    job = wait_for(
        lambda: (
            j
            if (j := review_client.get(f"/api/jobs/{first.json()['job_id']}", headers=AUTH).json())[
                "state"
            ]
            in ("cancelled", "done", "failed")
            else None
        )
    )
    assert job["state"] == "cancelled" and job["result"] is None


def test_open_errors(review_client, tmp_path):
    root = review_client.root
    relative = review_client.get("/api/review/session", params={"path": "x/y"}, headers=AUTH)
    assert relative.status_code == 400 and relative.json()["error"]["code"] == "invalid_argument"
    outside = review_client.get("/api/review/session", params={"path": "/etc"}, headers=AUTH)
    assert outside.status_code == 403 and outside.json()["error"]["code"] == "forbidden_path"
    missing = review_client.get(
        "/api/review/session", params={"path": str(root / "nope")}, headers=AUTH
    )
    assert missing.status_code == 404
    empty = root / "empty"
    empty.mkdir()
    bad = review_client.get("/api/review/session", params={"path": str(empty)}, headers=AUTH)
    assert bad.status_code == 400 and bad.json()["error"]["code"] == "session_invalid"
    assert bad.json()["error"]["message"].startswith("No session.json in")
    job = run_job(
        review_client,
        review_client.post("/api/review/session", json={"path": str(empty)}, headers=AUTH),
    )
    assert job["state"] == "failed" and job["error"]["code"] == "session_invalid"
    broken = root / "broken"
    broken.mkdir()
    (broken / "session.json").write_text("{not json")
    answer = review_client.get("/api/review/session", params={"path": str(broken)}, headers=AUTH)
    assert answer.json()["error"]["message"].startswith("Could not read session.json:")
    strict = review_client.post("/api/review/session", json={"path": 3}, headers=AUTH)
    assert strict.status_code == 400


def test_readiness_blocked_without_lights_and_missing_frames(review_client):
    path = make_session(review_client.root, recorder=False)
    document = json.loads((path / "session.json").read_text())
    document["frames"] = [f for f in document["frames"] if f["image_type"] != "Light Frame"]
    document["frames"].append(dict(document["frames"][0], filename="gone.fit"))
    (path / "session.json").write_text(json.dumps(document))
    record = review_client.get(
        "/api/review/session", params={"path": str(path)}, headers=AUTH
    ).json()
    issues = record["readiness"]["issues"]
    assert {
        "code": "session_warning",
        "level": "warn",
        "message": "Missing FITS frame: gone.fit",
    } in issues
    assert {
        "code": "no_lights",
        "level": "error",
        "message": "No light frames were recorded.",
    } in issues
    assert record["readiness"]["state"] == "blocked"
    assert record["counts"]["missing_frames"] == 1


def test_cache_follows_file_changes(review_client):
    path = make_session(review_client.root, recorder=False)
    first = review_client.get("/api/review/session", params={"path": str(path)}, headers=AUTH)
    target_csv = next((path / "photometry").glob("target_*.csv"))
    lines = target_csv.read_text().splitlines()
    target_csv.write_text("\n".join(lines[:-1]) + "\n")
    second = review_client.get("/api/review/session", params={"path": str(path)}, headers=AUTH)
    assert second.json()["revision"] != first.json()["revision"]
    n = {c["role"]: c["n"] for c in second.json()["curves"]}
    assert n["target"] == 3


# ---------------------------------------------------------------------------
# A69: curves
# ---------------------------------------------------------------------------


def _curves(client, path) -> dict:
    response = client.get("/api/review/session/curves", params={"path": str(path)}, headers=AUTH)
    assert response.status_code == 200, response.text
    return response.json()


def test_curves_roles_keys_filters_and_columns(review_client):
    path = make_session(review_client.root)
    record = _curves(review_client, path)
    curves = {c["key"]: c for c in record["curves"]}
    assert set(curves) == {"000-AAA-001@v", "000-AAA-002@v", "000-AAA-003@v"}
    check = curves["000-AAA-003@v"]
    assert check["role"] == "check"  # S9: never a second target
    assert check["role_source"] == "prefix"
    assert check["catalogue_v"] == 12.3
    target = curves["000-AAA-001@v"]
    assert target["name"] == "XX Test" and target["auid"] == "000-AAA-001"
    assert target["filter"] == "v" and target["filter_source"] == "name"
    assert target["exportable"] is True and target["problem"] is None
    assert record["filters"] == ["v"] and record["multi_filter"] is False
    cols = target["columns"]
    assert target["n"] == 4
    assert all(len(cols[name]) == 4 for name in cols)
    assert cols["bjd_tdb"][0] is None and cols["bjd_tdb"][1] is not None
    # Frame 2 is blank sky in the recorder: suspect too once the core applies S67 (GUARD).
    blank = review_module.core_rules() is not None
    assert cols["suspect"] == [False, True, blank, False]
    assert cols["saturated"] == [False] * 4
    assert cols["comps_used"] == [1] * 4
    assert cols["frame"] == [0, 1, 2, 3]
    assert all(abs(dt) < 0.01 for dt in cols["frame_dt_s"])
    assert cols["header_airmass"] == [1.2] * 4
    assert cols["snr"] == [120.0, 120.0, 1.5, 120.0]
    assert cols["zero_point"][2] == 14.4
    assert target["sigma_syst"] == 0.016
    assert target["csv"].endswith("target_XX_Test_v_000-AAA-001.csv")
    assert record["targets"]["object_name"] == "XX Test"


def test_flags_from_the_flight_recorder(review_client):
    path = make_session(review_client.root)
    curves = {c["role"]: c for c in _curves(review_client, path)["curves"]}
    # S67 (GUARD: the merged core): every point of a no-detection frame is flagged too.
    nd = ["no_detection"] if review_module.core_rules() is not None else []
    # Frame 2: the target's zero point is 5 mag off: every star of that frame.
    assert curves["target"]["columns"]["flags"] == [[], [], ["zp_outlier", "low_snr", *nd], []]
    assert curves["check"]["columns"]["flags"][2] == ["zp_outlier", *nd]
    # Frame 3: the comparison's own SNR is 2: its point only.
    assert curves["comparison"]["columns"]["flags"] == [[], [], ["zp_outlier", *nd], ["low_snr"]]
    record = review_client.get(
        "/api/review/session", params={"path": str(path)}, headers=AUTH
    ).json()
    flagged = [i for i in record["readiness"]["issues"] if i["code"] == "flagged_points"]
    assert flagged and flagged[0]["count"] == 1


def test_s71_a_faint_ensemble_is_named_in_readiness(review_client):
    """S71: comparisons whose median SNR is below 10 make a noisy zero point (XX Cyg
    2026-08-29: 1.7). Readiness says so; a bright ensemble (80-90) says nothing."""
    path = make_session(review_client.root)
    record = review_client.get(
        "/api/review/session", params={"path": str(path)}, headers=AUTH
    ).json()
    assert "faint_comparisons" not in {i["code"] for i in record["readiness"]["issues"]}
    rec = path / "diagnostics" / "XX_Test_live_diagnostics.jsonl"
    times = [START + timedelta(seconds=CADENCE_S * i) for i in range(4)]
    _write_recorder(rec, times, comp_snr=6.0)
    record = review_client.get(
        "/api/review/session", params={"path": str(path)}, headers=AUTH
    ).json()
    by_code = {i["code"]: i for i in record["readiness"]["issues"]}
    assert by_code["faint_comparisons"]["level"] == "warn"
    assert by_code["faint_comparisons"]["median_snr"] == 6.0
    assert "S71" in by_code["faint_comparisons"]["message"]


def test_s56_old_file_rule_flags_an_unverified_lock(review_client):
    """notes/release_0_5_0.md, "Check your old files" (S56): a sub on which fewer than 3
    comparison or check stars reached SNR 10 unsaturated was measured through a lock
    nothing verified. Review flags it (``few_anchors``) and says so, separately from the
    no-detection flags; the AAVSO preview names the point (an owner decision keeps it
    written, as the fixed Qt writes it)."""
    path = make_session(review_client.root)
    rec = path / "diagnostics" / "XX_Test_live_diagnostics.jsonl"
    rec.unlink()
    times = [START + timedelta(seconds=CADENCE_S * i) for i in range(4)]
    _write_recorder(rec, times, few_anchors=3)
    curves = {c["role"]: c for c in _curves(review_client, path)["curves"]}
    rules = review_module.core_rules() is not None  # GUARD: S67 in the merged core
    nd = ["no_detection"] if rules else []
    assert curves["target"]["columns"]["flags"] == [
        [],
        [],
        ["zp_outlier", "low_snr", *nd],
        ["few_anchors"],
    ]
    assert curves["check"]["columns"]["flags"][3] == ["few_anchors"]
    record = review_client.get(
        "/api/review/session", params={"path": str(path)}, headers=AUTH
    ).json()
    by_code = {i["code"]: i for i in record["readiness"]["issues"]}
    assert by_code["flagged_points"]["count"] == 1
    assert by_code["unverified_lock"]["count"] == 1
    preview = review_client.post(
        "/api/export/aavso/preview",
        json={"source": {"kind": "session", "path": str(path)}},
        headers=AUTH,
    ).json()
    if rules:  # S67: the no-detection point is left out; the S56 point stays, named
        assert preview["unverified_lock"] == 1 and preview["recorder_flagged"] == 0
        assert {w["code"] for w in preview["warnings"]} == {"unverified_lock"}
        assert "S58" in preview["warnings"][0]["message"]
        assert sorted(p["index"] for p in preview["flagged_points"]) == [3]
    else:
        assert preview["unverified_lock"] == 1 and preview["recorder_flagged"] == 1
        assert {w["code"] for w in preview["warnings"]} == {"recorder_flagged", "unverified_lock"}
        assert sorted(p["index"] for p in preview["flagged_points"]) == [2, 3]


def test_no_recorder_no_flags_and_far_point(review_client):
    path = make_session(review_client.root, recorder=False)
    csv_path = next((path / "photometry").glob("target_*.csv"))
    text = csv_path.read_text().splitlines()
    far = text[1].split(",")
    far[0] = repr(float(far[0]) + 0.5)  # 12 h later: no frame
    csv_path.write_text("\n".join([*text, ",".join(far)]) + "\n")
    target = next(c for c in _curves(review_client, path)["curves"] if c["role"] == "target")
    cols = target["columns"]
    assert cols["flags"][:4] == [[], [], [], []]
    assert cols["flags"][4] == ["no_frame"] and cols["frame"][4] is None
    assert cols["snr"] == [None] * 5


def test_pre_050_names_take_the_session_filter(review_client):
    path = make_session(review_client.root, names="old", recorder=False)
    record = _curves(review_client, path)
    assert {c["key"] for c in record["curves"]} == {
        "000-AAA-001@v",
        "000-AAA-002@v",
        "000-AAA-003@v",
    }
    assert {c["filter_source"] for c in record["curves"]} == {"session"}


def test_pre_050_names_with_two_filters_say_nothing(review_client):
    path = make_session(
        review_client.root, filters=("V", "B", "V", "B"), names="old", recorder=False
    )
    # The old names gave one file per star for both bands (written last wins here).
    record = _curves(review_client, path)
    assert {c["filter"] for c in record["curves"]} == {""}
    assert {c["key"] for c in record["curves"]} == {
        "000-AAA-001@",
        "000-AAA-002@",
        "000-AAA-003@",
    }


def test_two_filters_s49(review_client):
    path = make_session(review_client.root, filters=("V", "B", "V", "B"), recorder=False)
    record = _curves(review_client, path)
    keys = {c["key"] for c in record["curves"]}
    assert keys == {f"000-AAA-00{i}@{t}" for i in (1, 2, 3) for t in ("v", "b")}
    assert record["filters"] == ["b", "v"] and record["multi_filter"] is True
    target_b = next(c for c in record["curves"] if c["key"] == "000-AAA-001@b")
    assert target_b["columns"]["frame"] == [1, 3]


def test_site_mismatch_takes_the_header_airmass(review_client):
    far_site = (-30.0, 150.0)  # the Settings site of another trip
    path = make_session(review_client.root, header_site=far_site, recorder=False)
    record = review_client.get(
        "/api/review/session", params={"path": str(path)}, headers=AUTH
    ).json()
    assert record["site_check"]["state"] == "mismatch"
    assert record["site_check"]["median_deg"] > 5.0
    assert record["airmass_source"] == "header"
    assert any(i["code"] == "site_mismatch" for i in record["readiness"]["issues"])
    curves = _curves(review_client, path)
    assert curves["airmass_source"] == "header"
    # S66 (GUARD: the merged core): the column itself is each frame's header AIRMASS.
    rules = review_module.core_rules() is not None
    assert curves["airmass_column"] == ("header" if rules else "csv")
    target = next(c for c in curves["curves"] if c["role"] == "target")
    expected = target["columns"]["header_airmass"] if rules else [1.5, 1.51, 1.52, 1.53]
    assert target["columns"]["airmass"] == expected


def test_unidentified_curve_is_not_exportable(review_client):
    path = make_session(review_client.root, recorder=False)
    stray = path / "photometry" / "comparison_XX_Test_v_000-ZZZ-999.csv"
    stray.write_text(next((path / "photometry").glob("comparison_*.csv")).read_text())
    record = _curves(review_client, path)
    curve = next(c for c in record["curves"] if c["file_name"] == stray.name)
    assert curve["exportable"] is False
    assert "star unknown" in curve["problem"]
    assert curve["role"] == "comparison"
    session = review_client.get(
        "/api/review/session", params={"path": str(path)}, headers=AUTH
    ).json()
    assert any(i["code"] == "unidentified_curve" for i in session["readiness"]["issues"])


def test_curves_equal_the_qt_reader(review_client):
    pytest.importorskip("PyQt6.QtCore")
    from argos.core.session import review as qt_review

    for filters, names in ((("V",) * 4, "s49"), (("V", "B", "V", "B"), "s49"), (("V",) * 4, "old")):
        folder = f"20260925T2004{len(filters)}{names}{''.join(filters)}"
        path = make_session(review_client.root, folder, filters=filters, names=names)
        assert_curves_equal_qt(review_client.hub.review.session(str(path)).curves, path)
        session = qt_review.load_session(path, read_temperature=True)
        ours = review_client.hub.review.session(str(path)).record
        assert ours["warnings"] == session.warnings
        assert [f["ccd_temp"] for f in ours["frames"]] == [f.ccd_temp for f in session.frames]


def assert_curves_equal_qt(curve_set, path: Path) -> None:
    """Every curve of Qt's ``load_session_curves``, point for point, and its frame link."""
    from argos.core.session import review as qt_review

    session = qt_review.load_session(path, read_temperature=False)
    qt_curves = qt_review.load_session_curves(session)
    ours = {c.identity: c for c in curve_set.curves}
    assert set(ours) == set(qt_curves)
    for identity, qt_lc in qt_curves.items():
        mine = ours[identity]
        assert (mine.lc.role, mine.lc.name, mine.lc.auid, mine.lc.filter_name) == (
            qt_lc.role,
            qt_lc.name,
            qt_lc.auid,
            qt_lc.filter_name,
        )
        assert len(mine.lc.points) == len(qt_lc.points)
        for a, b in zip(mine.lc.points, qt_lc.points):
            assert a == b  # LcPoint dataclass equality: every field
        for point, index in zip(qt_lc.points, mine.frame):
            frame = session.nearest_light_frame(point.jd_utc)
            if index is not None:
                assert frame is not None and frame.filename == session.frames[index].filename


# ---------------------------------------------------------------------------
# A70: import
# ---------------------------------------------------------------------------


def test_import_one_star_csv_takes_role_and_star(review_client):
    path = make_session(review_client.root, recorder=False)
    csv_path = path / "photometry" / "comparison_XX_Test_v_000-AAA-002.csv"
    record = review_client.post(
        "/api/review/import-csv", json={"path": str(csv_path)}, headers=AUTH
    ).json()
    assert record["source"] == {"kind": "import", "path": str(csv_path)}
    (curve,) = record["curves"]
    assert curve["role"] == "comparison"  # S10: never the target named after the file
    assert curve["key"] == "000-AAA-002@v" and curve["role_source"] == "prefix"
    assert curve["exportable"] is True
    assert record["targets"]["chart_id"] == "X1"
    assert curve["columns"]["frame"] == [None] * 4


def test_import_pre_050_name_in_a_session_takes_its_filter(review_client):
    path = make_session(review_client.root, names="old", recorder=False)
    csv_path = path / "photometry" / "check_XX_Test_000-AAA-003.csv"
    record = review_client.post(
        "/api/review/import-csv", json={"path": str(csv_path)}, headers=AUTH
    ).json()
    (curve,) = record["curves"]
    assert (curve["key"], curve["role"], curve["filter_source"]) == (
        "000-AAA-003@v",
        "check",
        "session",
    )


def test_import_multi_curve_export_keeps_its_columns(review_client, tmp_path):
    out = review_client.root / "export.csv"
    target = LightCurve(auid="000-AAA-001", name="XX Test", role="target")
    check = LightCurve(auid="000-AAA-003", name="123", role="check")
    for lc in (target, check):
        lc.append(LcPoint(jd_utc=2461309.5, mag=7.1, mag_err=0.01))
    write_curves_csv(out, [target, check])
    record = review_client.post(
        "/api/review/import-csv", json={"path": str(out)}, headers=AUTH
    ).json()
    roles = {c["key"]: (c["role"], c["role_source"]) for c in record["curves"]}
    assert roles == {
        "000-AAA-001@": ("target", "column"),
        "000-AAA-003@": ("check", "column"),
    }


def test_import_unknown_star_not_exportable(review_client):
    lonely = review_client.root / "lonely"
    lonely.mkdir()
    csv_path = lonely / "mystery.csv"
    csv_path.write_text("jd_utc,mag,mag_err\n2461309.5,7.1,0.01\n")
    record = review_client.post(
        "/api/review/import-csv", json={"path": str(csv_path)}, headers=AUTH
    ).json()
    (curve,) = record["curves"]
    assert curve["exportable"] is False and curve["role_source"] == "default"
    assert "role unknown" in curve["problem"]


@pytest.mark.parametrize(
    "content, reason",
    [
        (b"", "No valid photometry rows in"),
        (b"jd_utc,mag\n1,2\n", "has no 'mag_err' column"),
        (b"jd_utc,mag,mag_err\nx,y,z\n", "No valid photometry rows in"),
        (b"\xff\xfe\x00bad", "is not UTF-8 text"),
    ],
)
def test_import_refuses_unusable_csv(review_client, content, reason):
    csv_path = review_client.root / "bad.csv"
    csv_path.write_bytes(content)
    answer = review_client.post(
        "/api/review/import-csv", json={"path": str(csv_path)}, headers=AUTH
    )
    assert answer.status_code == 422
    assert answer.json()["error"]["code"] == "invalid_csv"
    assert reason in answer.json()["error"]["message"]


def test_import_path_errors(review_client):
    txt = review_client.root / "notes.txt"
    txt.write_text("x")
    wrong = review_client.post("/api/review/import-csv", json={"path": str(txt)}, headers=AUTH)
    assert wrong.status_code == 400
    missing = review_client.post(
        "/api/review/import-csv", json={"path": str(review_client.root / "none.csv")}, headers=AUTH
    )
    assert missing.status_code == 404


# ---------------------------------------------------------------------------
# Live source, the source model, the scan job
# ---------------------------------------------------------------------------


def test_live_curves_and_curve_set(review_client):
    hub = review_client.hub
    service = hub.photometry
    lc = LightCurve(auid="000-AAA-001", name="XX Test", role="target", filter_name="v")
    lc.append(LcPoint(jd_utc=2461309.5, mag=7.1, mag_err=0.01, suspect=True))
    with service._lock:
        service._curves["000-AAA-001@v"] = lc
    record = review_client.get("/api/review/live/curves", headers=AUTH).json()
    assert record["source"] == {"kind": "live"}
    (curve,) = record["curves"]
    assert curve["key"] == "000-AAA-001@v" and curve["filter_source"] == "live"
    assert curve["columns"]["suspect"] == [True]
    data = hub.review.curve_set({"kind": "live"})
    assert data.curves[0].lc is not lc  # a copy: later points never change it
    assert data.curves[0].lc.points == lc.points
    path = make_session(review_client.root, recorder=False)
    session_set = hub.review.curve_set({"kind": "session", "path": str(path)})
    assert {c.lc.role for c in session_set.curves} == {"target", "comparison", "check"}
    csv_path = next((path / "photometry").glob("target_*.csv"))
    assert hub.review.curve_set({"kind": "import", "path": str(csv_path)}).curves[0].key == (
        "000-AAA-001@v"
    )
    from argos.server.errors import ApiError

    with pytest.raises(ApiError):
        hub.review.curve_set({"kind": "other"})


def test_sessions_scan_job(review_client):
    make_session(review_client.root, "20260925T200453Z_XX_Test", recorder=False)
    make_session(review_client.root, "20260926T200453Z_XX_Test", recorder=False)
    (review_client.root / "not_a_session").mkdir()
    job = run_job(review_client, review_client.post("/api/sessions/scan", headers=AUTH))
    assert job["state"] == "done" and job["kind"] == "sessions_scan"
    assert job["result"]["total"] == 2 and job["total"] == 2
    page = review_client.get("/api/sessions", headers=AUTH).json()
    assert page["total"] == 2


def test_quality_files_with_and_without_the_filter_key(review_client):
    path = make_session(review_client.root, filters=("V", "B", "V", "B"), recorder=False)
    report = {"comparisons": [], "verdict": "ok"}
    (path / "photometry_quality.json").write_text(json.dumps({**report, "filter": "v"}))
    (path / "photometry_quality_b.json").write_text(json.dumps({**report, "filter": "b"}))
    quality = review_client.get(
        "/api/review/session", params={"path": str(path)}, headers=AUTH
    ).json()["quality"]
    assert quality["default_filter"] == "v"  # S57
    assert set(quality["by_filter"]) == {"b"}
    assert quality["default"]["verdict"] == "ok"
    (path / "photometry_quality.json").write_text(json.dumps(report))  # before 0.5.0
    (path / "photometry_quality_b.json").unlink()
    quality = review_client.get(
        "/api/review/session", params={"path": str(path)}, headers=AUTH
    ).json()["quality"]
    assert quality["default_filter"] is None and quality["by_filter"] == {}


# ---------------------------------------------------------------------------
# W7 technical review: linking cost and cancellation of session_open
# ---------------------------------------------------------------------------


def test_nearest_light_by_bisection_equals_the_linear_min():
    """nearest_light_index was a linear min() per point (O(points × frames): 33 s on a
    6000-frame session). The bisection gives the same index, ties to the earliest in list
    order as min() does, on unsorted lights with duplicate times."""
    import random
    from types import SimpleNamespace

    rng = random.Random(7)
    base = datetime(2026, 9, 25, 20, 0, tzinfo=timezone.utc)
    secs = [rng.choice([0, 10, 10, 20, 35, 35, 50]) + 60 * rng.randint(0, 40) for _ in range(300)]
    light = [
        (i * 2, SimpleNamespace(timestamp=base + timedelta(seconds=s))) for i, s in enumerate(secs)
    ]

    def linear(jd: float) -> int:
        seconds = (jd - 2_440_587.5) * 86_400.0
        return min(light, key=lambda item: abs(item[1].timestamp.timestamp() - seconds))[0]

    find = review_module._light_finder(light)
    jd0 = julian_date(base)
    for k in range(2000):
        jd = jd0 + rng.uniform(-120, 2600) / 86_400.0
        if k % 3 == 0:  # exactly between two distinct times, and on a time
            jd = jd0 + (rng.choice(secs) + rng.choice([0.0, 5.0, 7.5])) / 86_400.0
        assert find(jd) == linear(jd)
    assert review_module._light_finder([])(jd0) is None


def test_open_is_cancelled_while_linking_the_curves(review_client, monkeypatch):
    """session_open checked the cancel flag only while reading headers: a DELETE during
    the 'curves' stage was ignored and the job ended 'done'."""
    from argos.server.jobs import JobCancelled

    path = make_session(review_client.root)
    cancelled = threading.Event()

    class Ctx:
        def check(self):
            if cancelled.is_set():
                raise JobCancelled()

        def progress(self, done=None, **kw):
            pass

    real = review_module._link_points

    def link_then_cancel(*args, **kwargs):
        real(*args, **kwargs)
        cancelled.set()  # the observer pressed Cancel while the curves were being linked

    monkeypatch.setattr(review_module, "_link_points", link_then_cancel)
    with pytest.raises(JobCancelled):
        review_module.open_session(path, Ctx())


def test_session_list_says_what_the_open_will_flag(review_client):
    """R0's Issues said "–" where R1's badge said "2 issues" (W7 design review): the list
    carries the cheap readiness lines (the site check on the first light's header, the
    recorder's flagged frames) and the vetting verdict."""
    far_site = (-30.0, 150.0)
    path = make_session(review_client.root, header_site=far_site)  # recorder: frame 2 blank
    (path / "photometry_quality.json").write_text(
        json.dumps(
            {
                "comparison_stars": [
                    {"name": "a", "status": "stable"},
                    {"name": "b", "status": "variable_or_noisy"},
                ]
            }
        )
    )
    job = run_job(review_client, review_client.post("/api/sessions/scan", headers=AUTH))
    assert job["state"] == "done"
    (row,) = review_client.get("/api/sessions", headers=AUTH).json()["sessions"]
    assert row["quality"] == {"stable": 1, "total": 2}
    issues = row["issues"]
    assert any("site in Settings was not where the telescope was" in i for i in issues)
    assert any(i.startswith("1 frame flagged by the flight recorder") for i in issues)
    record = review_client.get(
        "/api/review/session", params={"path": str(path)}, headers=AUTH
    ).json()
    codes = {i["code"] for i in record["readiness"]["issues"]}
    assert {"site_mismatch", "flagged_points"} <= codes
