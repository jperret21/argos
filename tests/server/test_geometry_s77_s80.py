"""Release S77-S80 and the server's geometry leftovers (wave 7, 2026-11-16).

S77 proper motion, S78 each star's own airmass, S79 a crowded comparison, S80 every
inconsistent anchor rejected; the web overlay tracker on the core's converged centroid;
S68's chart backfill in ``TargetService``. GUARD: the core functions arrive with the
merge of release/0.5.0; until then these tests are skipped.
"""

from __future__ import annotations

import json
import math
from datetime import timedelta

import numpy as np
import pytest
from astropy.io import fits

from argos.core.catalog import targets as core_targets
from argos.core.catalog.targets import TargetSet, TargetStar
from argos.core.imaging.sky_geometry import compute_airmass, horizontal_at
from argos.core.photometry.airmass import airmass_at, julian_date
from argos.server import rerun as rerun_module

pytestmark = pytest.mark.skipif(
    not hasattr(core_targets, "crowded_stars"),
    reason="GUARD: needs release/0.5.0's core (S77-S80)",
)

#: A synthetic Gaia DR3 source for the test set's target (000-AAA-001 at 291.300,
#: 42.780, J2000.0): 2"/yr, so 26.7 years move it 53" (14.8 green px at 3.6"/px).
_PM = (-1000.0, -1700.0)


def _gaia_target():
    from argos.core.catalog.gaia import GaiaStar

    years = 16.0
    dec = 42.780 + _PM[1] * years / 3.6e6
    ra = 291.300 + _PM[0] * years / 3.6e6 / math.cos(math.radians(42.780))
    return GaiaStar("1", ra, dec, g_mag=9.0, pmra_mas_yr=_PM[0], pmdec_mas_yr=_PM[1])


def _site_frames(session, n: int = 4, step_min: float = 4.0):
    """test_rerun's frames 4 minutes apart with the headers Argos writes: where the mount
    pointed from test_review_sessions.SITE (the Settings site of the request is another)."""
    from tests.server import test_rerun as tr
    from tests.server.test_review_sessions import SITE, START

    paths = []
    for i in range(n):
        path = session / "lights" / f"XX_Test_ir_light_{i + 1:05d}.fit"
        tr._write(path, i)
        with fits.open(path, mode="update") as hdul:
            h = hdul[0].header
            when = START + timedelta(minutes=step_min * i)
            h["DATE-OBS"] = when.isoformat(timespec="milliseconds").replace("+00:00", "")
            ra_h, dec = tr.TARGET.ra_deg / 15.0, tr.TARGET.dec_deg
            alt, az = horizontal_at(julian_date(when), ra_h, dec, *SITE)
            h["RA"], h["DEC"] = ra_h, dec
            h["ALTITUDE"], h["AZIMUTH"] = alt, az
            h["AIRMASS"] = round(compute_airmass(alt), 4)
            h["SITELAT"], h["SITELONG"] = (SITE[0] + 20.0, SITE[1])
            h["SOFTWARE"] = "Argos v0.4.2"
        paths.append(path)
    return paths


def test_the_re_run_port_moves_the_target_and_gives_each_star_its_airmass_s77_s78(tmp_path):
    """S77 and S78 in the server's re-run, against the fixed Qt worker: the target with
    a proper motion is measured at each frame's date (14.8 green px from its J2000.0
    position here), a comparison or check star's airmass is its own for the site
    fitted to the headers (the request's Settings site is 20° away), and both write the
    same bytes (CSVs, targets.json with the motion, flight-recorder records)."""
    from tests.server import test_rerun as tr
    from tests.server.test_review_sessions import SITE

    session = tmp_path / "session"
    (session / "lights").mkdir(parents=True)
    paths = _site_frames(session)

    def request(out):
        req = tr._request(paths, out)
        req.site = (SITE[0] + 20.0, SITE[1], 0.0)
        req.proper_motions = lambda _ts: [_gaia_target()]
        return req

    server = rerun_module.BatchRun(request(tmp_path / "server")).run()
    assert server.ok
    records = [json.loads(line) for line in next((tmp_path / "server").glob("*.jsonl")).open()]
    placed = [(r["x"], r["y"]) for r in records if r["kind"] == "star" and r["role"] == "target"]
    x0, y0 = (float(v) for v in tr.WCS.world_to_pixel_deg(291.300, 42.780))
    assert placed and all(14.0 < math.hypot(x - x0, y - y0) < 15.5 for x, y in placed)
    stars = {s.auid: s for s in tr.target_set().stars}
    for lc in server.curves.values():
        if lc.role == "target":
            continue
        star = stars[lc.auid]
        own = [airmass_at(p.jd_utc, star.ra_deg, star.dec_deg, *SITE) for p in lc.points]
        assert all(abs(p.airmass - a) < 2e-4 for p, a in zip(lc.points, own))
    assert TargetSet.load(tmp_path / "server" / "targets.json").stars[0].has_proper_motion

    pytest.importorskip("PyQt6")
    from PyQt6.QtWidgets import QApplication

    from argos.workers import photometry_batch_worker as qt_worker

    tr._QT.append(QApplication.instance() or QApplication([]))
    box: list = []
    qt = qt_worker.PhotometryBatchWorker(tr.qt_request(qt_worker, request(tmp_path / "qt")))
    qt.finished_batch.connect(box.append)
    qt.run()
    names = sorted(p.name for p in (tmp_path / "qt").glob("*.csv")) + ["targets.json"]
    assert names[:-1] == sorted(p.name for p in (tmp_path / "server").glob("*.csv"))
    for name in names:
        assert (tmp_path / "server" / name).read_bytes() == (tmp_path / "qt" / name).read_bytes()

    def body(path):
        return [{k: v for k, v in json.loads(line).items() if k != "t"} for line in path.open()]

    (q,) = (tmp_path / "qt").glob("*.jsonl")
    (s,) = (tmp_path / "server").glob("*.jsonl")
    assert body(q) == body(s)


def test_a_short_re_run_at_a_wrong_site_keeps_the_header_airmass_s78(tmp_path):
    """S78 amended (validation F1), the server's port against the fixed Qt worker: 4
    frames over 3 minutes fit no site and the request's Settings site (20° away) does
    not reproduce the mount's pointing, so every star keeps its frame's header AIRMASS
    (RR Lyr 2026-09-25 195307Z: 4.0-4.9 for 1.03 before); the same bytes as Qt."""
    from tests.server import test_rerun as tr
    from tests.server.test_review_sessions import SITE

    from argos.server.review import core_rules

    if not hasattr(core_rules(), "settings_site_reproduces"):
        pytest.skip("GUARD: needs release/0.5.0's settings_site_reproduces")
    session = tmp_path / "session"
    (session / "lights").mkdir(parents=True)
    paths = _site_frames(session, step_min=1.0)
    header = [fits.getheader(path)["AIRMASS"] for path in paths]

    def request(out):
        req = tr._request(paths, out)
        req.site = (SITE[0] + 20.0, SITE[1], 0.0)
        return req

    server = rerun_module.BatchRun(request(tmp_path / "server")).run()
    assert server.ok
    for lc in server.curves.values():
        assert [p.airmass for p in lc.points] == header[: len(lc.points)]

    pytest.importorskip("PyQt6")
    from PyQt6.QtWidgets import QApplication

    from argos.workers import photometry_batch_worker as qt_worker

    tr._QT.append(QApplication.instance() or QApplication([]))
    qt = qt_worker.PhotometryBatchWorker(tr.qt_request(qt_worker, request(tmp_path / "qt")))
    qt.run()
    for path in sorted((tmp_path / "qt").glob("*.csv")):
        assert (tmp_path / "server" / path.name).read_bytes() == path.read_bytes()


def test_the_target_record_names_a_crowded_comparison_s79(client):
    """S79: XX Cyg 2026-09-07 040723Z paired 000-BJV-173 with 000-BJV-169, 1.47 mag
    brighter and 6.8 green px away, and nothing said so. The targets record names it
    (``crowding``, and the star's ``crowded``), as Qt's Comparison stars tab does."""
    hub = client.app.state.hub
    tset, path = hub.targets._current()
    TargetSet(
        object_name=tset.object_name,
        stars=[
            TargetStar("target", 300.81517, 58.95458, auid="000-BCK-301", source="vsx"),
            TargetStar(
                "comparison",
                300.65291666666667,
                58.89161111111111,
                auid="000-BJV-173",
                source="vsp_auto",
                mags={"V": 11.757},
            ),
            TargetStar(
                "check",
                300.6277083333334,
                58.88630555555555,
                auid="000-BJV-169",
                source="vsp_auto",
                mags={"V": 10.283},
            ),
        ],
    ).save(path)
    hub.targets.reload()
    record = hub.targets.record()
    crowded = {s["auid"]: s["crowded"] for s in record["stars"]}
    assert crowded["000-BJV-169"] is None and crowded["000-BCK-301"] is None
    assert crowded["000-BJV-173"]["neighbour"] == "000-BJV-169"
    assert crowded["000-BJV-173"]["delta_mag"] == -1.474
    assert len(record["crowding"]) == 1 and "1.47 mag brighter in V" in record["crowding"][0]
    # Qt's one WARN per newly crowded star (technical review: the server logged none).
    from tests.server.conftest import log_messages

    hub.targets.publish()
    hub.targets.publish()
    warned = [m for m in log_messages(client) if m.startswith("Comparison crowded")]
    assert len(warned) == 1 and "000-BJV-173" in warned[0]


def test_a_gaia_answer_gives_the_set_its_proper_motions_s77(client):
    """S77: the field catalogue's Gaia DR3 answer gives the set's VSX/VSP stars their
    proper motion (``TargetService.backfill_proper_motions``, as Qt's ``_on_catalog``):
    saved in the object's set and on the wire."""
    hub = client.app.state.hub
    tset, path = hub.targets._current()
    TargetSet(
        object_name=tset.object_name,
        stars=[TargetStar("target", 291.300, 42.780, auid="000-AAA-001", source="vsx")],
    ).save(path)
    hub.targets.reload()

    assert hub.targets.backfill_proper_motions([_gaia_target()]) == 1

    assert TargetSet.load(path).stars[0].pm_ra_mas_yr == _PM[0]
    (star,) = hub.targets.record()["stars"]
    assert star["proper_motion"]["pm_dec_mas_yr"] == _PM[1]
    assert star["proper_motion"]["epoch"] == 2016.0
    assert hub.targets.backfill_proper_motions([_gaia_target()]) == 0


def _rotating_field(positions, rng, shape=(420, 420)):
    yy, xx = np.mgrid[0 : shape[0], 0 : shape[1]]
    g = np.full(shape, 1000.0, dtype=np.float32)
    for (cx, cy), peak in positions:
        g += peak * np.exp(-((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * 0.93**2))
    return g + rng.normal(0.0, 20.0, shape).astype(np.float32)


def test_the_overlay_tracker_keeps_up_with_a_field_rotating_0_7_deg_per_sub():
    """The web overlay tracker centroided each anchor in two passes, the second window
    centred on the first: on XX Cyg 2026-09-07 040723Z (0.7° per sub) it ended 0.31° behind
    ASTAP (field_track_lag.py). It now takes the core's converged centroid (S69): within
    0.1° after 24 subs here."""
    from argos.server.field_track import FieldTracker

    center = (210.0, 210.0)
    anchors = [(270.0, 210.0), (210.0, 100.0), (110.0, 230.0), (300.0, 320.0), (150.0, 330.0)]
    anchors.append((330.0, 120.0))
    peaks = [2000.0, 1500.0, 1200.0, 900.0, 700.0, 500.0]
    rng = np.random.default_rng(69)

    def turned(deg):
        a = math.radians(deg)
        return [
            (
                center[0] + math.cos(a) * (x - center[0]) - math.sin(a) * (y - center[1]),
                center[1] + math.sin(a) * (x - center[0]) + math.cos(a) * (y - center[1]),
            )
            for x, y in anchors
        ]

    reference = _rotating_field(list(zip(anchors, peaks)), rng)
    tracker = FieldTracker(anchors, center, search_r=15.0, reference_green=reference)
    for k in range(1, 25):
        tracker.update(_rotating_field(list(zip(turned(0.7 * k), peaks)), rng))
    assert abs(tracker.transform.rotation_deg - 0.7 * 24) < 0.1
