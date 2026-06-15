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

from seercontrol.core.alpaca.camera import Camera  # noqa: E402
from seercontrol.core.alpaca.filterwheel import FilterWheel  # noqa: E402
from seercontrol.core.imaging.fits_writer import FrameContext  # noqa: E402
from seercontrol.core.imaging.sequencer import SequencePlan, SequenceStep  # noqa: E402
from seercontrol.core.imaging.session_log import SESSION_FILENAME  # noqa: E402
from seercontrol.workers.sequence_worker import SequenceWorker  # noqa: E402
from tests.conftest import SIMULATOR_HOST, SIMULATOR_PORT, simulator_required  # noqa: E402


def _context_provider(object_name: str, filter_name: str) -> FrameContext:
    return FrameContext(
        object_name=object_name,
        filter_name=filter_name,
        software="SeerControl test",
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

    # FITS subs exist under the Siril session tree.
    fits_files = list(tmp_path.glob("sessions/**/*.fits"))
    assert len(fits_files) == 2

    # Per-frame QA headers are present.
    with fits.open(fits_files[0]) as hdul:
        hdr = hdul[0].header
        assert "NSTARS" in hdr
        assert "SKYLEVEL" in hdr
        assert hdr["IMAGETYP"] == "Light Frame"

    # session.json is valid and rolls up both frames.
    session_files = list(tmp_path.glob("sessions/**/" + SESSION_FILENAME))
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
    assert len(list(tmp_path.glob("sessions/**/*.fits"))) == 2
    # The wheel ended on the last requested filter (LP = position 2).
    assert final_pos == 2
