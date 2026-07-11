"""PhotometryBatchWorker — offline re-run over a folder of synthetic FITS (WS7).

Guards the batch path's contract: it uses the shared measurement core (so comps
get their catalog mags), emits progress, honours cancel, and writes the
canonical 9-column CSVs that Analyze reloads. Runs the QThread synchronously via
``run()`` to keep the test deterministic (no event loop needed).
"""

from __future__ import annotations

import numpy as np
import pytest
from astropy.io import fits

from argos.core.catalog.targets import ROLE_COMPARISON, ROLE_TARGET, TargetSet, TargetStar
from argos.core.photometry.lightcurve import LightCurve
from argos.core.photometry.params import PhotometryParams
from argos.workers.photometry_batch_worker import (
    BatchRequest,
    BatchResult,
    PhotometryBatchWorker,
)


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    from PyQt6.QtCore import QCoreApplication

    app = QCoreApplication.instance() or QCoreApplication([])
    yield app


class _FakeWCS:
    """Maps (ra_deg, dec_deg) → a preset green-px (x, y)."""

    def __init__(self, mapping):
        self._m = mapping

    def world_to_pixel_deg(self, ra_deg, dec_deg):
        return self._m[(ra_deg, dec_deg)]


def _raw_with_green_stars(green_positions_peaks, sky=200.0, sigma=1.5, green_shape=(60, 60)):
    """Build a raw GRBG frame whose green plane has stars at the given px.

    ``green_plane`` averages G1=raw[0::2,0::2] and G2=raw[1::2,1::2] → a green px
    (gx, gy) maps to raw (2*gx, 2*gy). We paint both greens with the same PSF.
    """
    gh, gw = green_shape
    raw = np.full((gh * 2, gw * 2), sky, dtype=np.float32)
    yy, xx = np.mgrid[0:gh, 0:gw]
    plane = np.zeros((gh, gw), dtype=np.float32)
    for (cx, cy), peak in green_positions_peaks:
        plane += peak * np.exp(-((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * sigma**2))
    raw[0::2, 0::2] += plane  # G1
    raw[1::2, 1::2] += plane  # G2
    return raw


def _write_fits(path, raw, date_obs):
    hdu = fits.PrimaryHDU(np.clip(raw, 0, 65535).astype(np.uint16))
    hdu.header["DATE-OBS"] = date_obs
    hdu.header["OBJECT"] = "TST Tau"
    hdu.writeto(path)


@pytest.fixture
def _scene(tmp_path):
    wcs = _FakeWCS(
        {
            (1.0, 1.0): (30.0, 30.0),  # target
            (2.0, 2.0): (10.0, 10.0),  # comp 1
            (3.0, 3.0): (50.0, 50.0),  # comp 2
        }
    )
    ts = TargetSet(object_name="TST Tau")
    ts.set_role(TargetStar(role=ROLE_TARGET, ra_deg=1.0, dec_deg=1.0, auid="T"))
    ts.set_role(
        TargetStar(role=ROLE_COMPARISON, ra_deg=2.0, dec_deg=2.0, auid="C1", mags={"V": 11.0})
    )
    ts.set_role(
        TargetStar(role=ROLE_COMPARISON, ra_deg=3.0, dec_deg=3.0, auid="C2", mags={"V": 11.0})
    )
    stars = [((30.0, 30.0), 20000.0), ((10.0, 10.0), 8000.0), ((50.0, 50.0), 8000.0)]
    paths = []
    for i in range(3):
        raw = _raw_with_green_stars(stars)
        p = tmp_path / f"sub_{i:03d}.fits"
        _write_fits(p, raw, f"2026-07-05T0{i}:00:00")
        paths.append(p)
    out_dir = tmp_path / "targets"
    params = PhotometryParams.from_config(lambda k, d: d)  # all config defaults
    req = BatchRequest(
        fits_paths=paths,
        wcs=wcs,
        target_set=ts,
        params=params,
        out_dir=out_dir,
        object_name="TST Tau",
    )
    return req, out_dir


def test_batch_measures_and_writes_9col_csv(_scene) -> None:
    req, out_dir = _scene
    seen = []
    worker = PhotometryBatchWorker(req)
    worker.point.connect(lambda pt: seen.append(pt))
    result_box = []
    worker.finished_batch.connect(result_box.append)
    worker.run()  # synchronous — no event loop

    assert result_box and isinstance(result_box[0], BatchResult)
    result = result_box[0]
    assert result.ok
    assert result.frames_done == 3
    # One target curve (comps aren't emitted as targets), 3 points.
    assert len(result.curves) == 1
    curve = next(iter(result.curves.values()))
    assert len(curve.points) == 3
    assert len(seen) == 3  # a point signal per frame for the one target
    # The target is brighter than the V=11 comps → calibrated mag < 11.
    assert curve.points[0].mag < 11.0

    # Canonical 9-column CSV written and reloadable.
    csvs = list(out_dir.glob("*.csv"))
    assert len(csvs) == 1
    header = csvs[0].read_text().splitlines()[0]
    assert header == "jd_utc,bjd_tdb,mag,mag_err,airmass,fwhm,sky_adu,comps_used,saturated"
    reloaded = LightCurve.from_csv(csvs[0])
    assert len(reloaded.points) == 3


def test_batch_cancel_stops_early(_scene) -> None:
    req, _ = _scene
    worker = PhotometryBatchWorker(req)
    worker.cancel()  # cancel before running → no frames processed
    result_box = []
    worker.finished_batch.connect(result_box.append)
    worker.run()
    assert result_box[0].ok
    assert result_box[0].frames_done == 0
    assert result_box[0].curves == {}


def test_batch_reports_progress(_scene) -> None:
    req, _ = _scene
    worker = PhotometryBatchWorker(req)
    steps = []
    worker.progress.connect(lambda done, total: steps.append((done, total)))
    worker.run()
    assert steps == [(1, 3), (2, 3), (3, 3)]
