"""End-to-end sequence run against the ASCOM Alpaca simulator (§7).

Runs a tiny :class:`SequenceWorker` plan through the real camera and asserts the
science outputs an astrophotographer relies on:

  * FITS subs land in the Siril-compatible session folder,
  * each carries per-frame QA headers (NSTARS / SKYLEVEL …),
  * a valid ``session.json`` rolls up the frame metrics.

The worker is a QThread; we run ``run()`` synchronously on the test thread so
signal slots fire by direct connection (no event loop needed). Auto-skipped
when the simulator is down.
"""

from __future__ import annotations

import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from astropy.io import fits  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from argos.core.alpaca.camera import Camera  # noqa: E402
from argos.core.alpaca.filterwheel import FilterWheel  # noqa: E402
from argos.core.imaging.fits_writer import FrameContext  # noqa: E402
from argos.core.imaging.sequencer import SequencePlan, SequenceStep  # noqa: E402
from argos.core.imaging.session_log import SESSION_FILENAME  # noqa: E402
from argos.workers.sequence_worker import SequenceWorker  # noqa: E402
from tests.conftest import SIMULATOR_HOST, SIMULATOR_PORT, simulator_required  # noqa: E402


def _context_provider(object_name: str, filter_name: str) -> FrameContext:
    return FrameContext(
        object_name=object_name,
        filter_name=filter_name,
        software="Argos test",
    )


@simulator_required
def test_sequence_writes_fits_and_session_json(tmp_path) -> None:
    _app = QApplication.instance() or QApplication(["test"])  # noqa: F841 (kept alive)

    cam = Camera(SIMULATOR_HOST, SIMULATOR_PORT)
    cam.connect()

    plan = SequencePlan(
        steps=[SequenceStep(frame_type="Light", exposure_s=0.5, gain=80, count=2)],
        object_name="SimTarget",
    )
    worker = SequenceWorker(
        camera=cam,
        telescope=None,
        filterwheel=None,
        plan=plan,
        frame_context_provider=_context_provider,
        base_dir=tmp_path,
    )

    saved: list = []
    finished: list = []
    worker.frame_saved.connect(lambda path, rec: saved.append((path, rec)))
    worker.finished.connect(lambda ok: finished.append(ok))

    try:
        worker.run()  # synchronous: direct-connected slots fire inline
    finally:
        cam.disconnect()

    # Completed cleanly and produced 2 frames.
    assert finished == [True]
    assert len(saved) == 2

    # FITS subs exist under the Siril-ready session tree.
    fits_files = list(tmp_path.glob("**/*.fit"))
    assert len(fits_files) == 2

    # Per-frame QA headers are present.
    with fits.open(fits_files[0]) as hdul:
        hdr = hdul[0].header
        assert "NSTARS" in hdr
        assert "SKYLEVEL" in hdr
        assert hdr["IMAGETYP"] == "Light Frame"

    # session.json is valid and rolls up both frames.
    session_files = list(tmp_path.glob("**/" + SESSION_FILENAME))
    assert len(session_files) == 1
    doc = json.loads(session_files[0].read_text())
    assert doc["object"] == "SimTarget"
    assert len(doc["frames"]) == 2
    assert doc["summary"]["frame_count"] == 2
    for frame in doc["frames"]:
        assert frame["image_type"] == "Light Frame"
        assert frame["sky_adu"] is not None
        assert frame["star_count"] is not None


@simulator_required
def test_sequence_record_carries_metrics(tmp_path) -> None:
    _app = QApplication.instance() or QApplication(["test"])  # noqa: F841

    cam = Camera(SIMULATOR_HOST, SIMULATOR_PORT)
    cam.connect()
    plan = SequencePlan(
        steps=[SequenceStep(frame_type="Light", exposure_s=0.5, gain=80, count=1)],
        object_name="SimTarget",
    )
    worker = SequenceWorker(
        camera=cam,
        telescope=None,
        filterwheel=None,
        plan=plan,
        frame_context_provider=_context_provider,
        base_dir=tmp_path,
    )
    records: list = []
    worker.frame_saved.connect(lambda path, rec: records.append(rec))
    try:
        worker.run()
    finally:
        cam.disconnect()

    assert len(records) == 1
    rec = records[0]
    assert rec is not None
    assert rec.star_count is not None
    assert rec.sky_adu is not None
    assert rec.exposure_s == 0.5


@simulator_required
def test_sequence_drives_filter_wheel(tmp_path) -> None:
    _app = QApplication.instance() or QApplication(["test"])  # noqa: F841

    cam = Camera(SIMULATOR_HOST, SIMULATOR_PORT)
    cam.connect()
    fw = FilterWheel(SIMULATOR_HOST, SIMULATOR_PORT)
    fw.connect()

    # Two light steps on different Seestar filters → the worker must move the wheel.
    plan = SequencePlan(
        steps=[
            SequenceStep(frame_type="Light", filter_name="IR", exposure_s=0.5, count=1),
            SequenceStep(frame_type="Light", filter_name="LP", exposure_s=0.5, count=1),
        ],
        object_name="SimTarget",
    )
    worker = SequenceWorker(
        camera=cam,
        telescope=None,
        filterwheel=fw,
        plan=plan,
        frame_context_provider=_context_provider,
        base_dir=tmp_path,
    )
    finished: list = []
    worker.finished.connect(lambda ok: finished.append(ok))
    final_pos = -1
    try:
        worker.run()
        final_pos = fw.get_position()  # read before disconnecting
    finally:
        cam.disconnect()
        fw.disconnect()

    assert finished == [True]
    assert len(list(tmp_path.glob("**/*.fit"))) == 2
    # The wheel ended on the last requested filter (LP = position 2).
    assert final_pos == 2


@simulator_required
def test_headers_record_the_actual_wheel_position(tmp_path) -> None:
    """P1 header truthfulness: a plan naming a filter the wheel doesn't have
    must NOT put that name in FILTER — the header records where the wheel
    really sits (this exact lie shipped a frame shot through IR labelled
    'LRGB' during the 2026-07-11 review session)."""
    _app = QApplication.instance() or QApplication(["test"])  # noqa: F841

    cam = Camera(SIMULATOR_HOST, SIMULATOR_PORT)
    cam.connect()
    fw = FilterWheel(SIMULATOR_HOST, SIMULATOR_PORT)
    fw.connect()

    plan = SequencePlan(
        steps=[SequenceStep(frame_type="Light", filter_name="LRGB", exposure_s=0.5, count=1)],
        object_name="SimTarget",
    )
    worker = SequenceWorker(
        camera=cam,
        telescope=None,
        filterwheel=fw,
        plan=plan,
        frame_context_provider=_context_provider,
        base_dir=tmp_path,
    )
    actual_name = ""
    try:
        worker.run()
        actual_name = fw.position_name()
    finally:
        cam.disconnect()
        fw.disconnect()

    (fits_path,) = list(tmp_path.glob("**/*.fit"))
    with fits.open(fits_path) as hdul:
        assert hdul[0].header["FILTER"] == actual_name
        assert hdul[0].header["FILTER"] != "LRGB"

    # session.json tells the same truth.
    (session_path,) = list(tmp_path.glob("**/" + SESSION_FILENAME))
    doc = json.loads(session_path.read_text())
    assert doc["frames"][0]["filter_name"] == actual_name


@simulator_required
def test_calibration_frames_land_typed_and_foldered(tmp_path) -> None:
    """P10 contract with postprod: a mixed plan puts each frame type in its
    Siril folder with a truthful IMAGETYP, the flat keeps the shutter open
    (is_light) and carries the actual wheel filter."""
    _app = QApplication.instance() or QApplication(["test"])  # noqa: F841

    cam = Camera(SIMULATOR_HOST, SIMULATOR_PORT)
    cam.connect()
    fw = FilterWheel(SIMULATOR_HOST, SIMULATOR_PORT)
    fw.connect()

    plan = SequencePlan(
        steps=[
            SequenceStep(frame_type="Light", filter_name="IR", exposure_s=0.5, count=1),
            SequenceStep(frame_type="Dark", exposure_s=0.5, count=1),
            SequenceStep(frame_type="Flat", filter_name="LP", exposure_s=0.3, count=1),
            SequenceStep(frame_type="Bias", exposure_s=0.1, count=1),
        ],
        object_name="CalTarget",
    )
    worker = SequenceWorker(
        camera=cam,
        telescope=None,
        filterwheel=fw,
        plan=plan,
        frame_context_provider=_context_provider,
        base_dir=tmp_path,
    )
    finished: list = []
    worker.finished.connect(lambda ok: finished.append(ok))
    try:
        worker.run()
    finally:
        cam.disconnect()
        fw.disconnect()

    assert finished == [True]
    root = next(tmp_path.iterdir())
    by_type = {
        "lights": "Light Frame",
        "darks": "Dark Frame",
        "flats": "Flat Frame",
        "biases": "Bias Frame",
    }
    for folder, imagetyp in by_type.items():
        matches = list(root.glob(f"{folder}/*.fit"))
        assert len(matches) == 1, f"expected one frame under {folder}/"
        with fits.open(matches[0]) as hdul:
            assert hdul[0].header["IMAGETYP"] == imagetyp

    # The flat records the wheel's real position (P1 read-back), i.e. LP.
    (flat,) = list(root.glob("flats/*.fit"))
    with fits.open(flat) as hdul:
        assert hdul[0].header["FILTER"] == "LP"
