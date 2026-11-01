"""ImagingPage's batch re-run entry point, on a stand-in page (no widgets).

The batch worker and the progress dialog are replaced by recorders: these
tests check which frames, and which output folder, the request carries.
"""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest
from astropy.io import fits

from argos.core.catalog.targets import ROLE_COMPARISON, ROLE_TARGET, TargetSet, TargetStar


class _Sig:
    def connect(self, _slot) -> None:
        pass


class _Recorder:
    """Stands in for PhotometryBatchWorker and QProgressDialog alike."""

    requests: list = []

    def __init__(self, request=None, *args, **kwargs) -> None:
        if request is not None and hasattr(request, "fits_paths"):
            _Recorder.requests.append(request)
        self.progress = self.finished_batch = self.canceled = _Sig()

    def __getattr__(self, _name):
        return lambda *a, **k: None


def _fits(path, imagetyp: str, date_obs: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    hdu = fits.PrimaryHDU(np.zeros((4, 4), dtype=np.uint16))
    hdu.header["IMAGETYP"] = imagetyp
    hdu.header["DATE-OBS"] = date_obs
    hdu.writeto(path)


@pytest.fixture
def rerun(tmp_path, monkeypatch):
    """Run ImagingPage._on_rerun_subs on ``folder``; return (requests, messages)."""
    import argos.ui.pages.imaging_page as ip
    import argos.workers.photometry_batch_worker as bw

    _Recorder.requests = []
    messages: list[str] = []
    monkeypatch.setattr(bw, "PhotometryBatchWorker", _Recorder)
    monkeypatch.setattr(ip, "QProgressDialog", _Recorder)
    monkeypatch.setattr(
        ip.QMessageBox,
        "information",
        staticmethod(lambda _parent, _title, text, *a, **k: messages.append(str(text))),
    )
    tset = TargetSet(object_name="SS Cyg")
    tset.set_role(TargetStar(role=ROLE_TARGET, ra_deg=1.0, dec_deg=1.0, auid="T"))
    tset.set_role(TargetStar(role=ROLE_COMPARISON, ra_deg=2.0, dec_deg=2.0, auid="C1"))

    def run(folder):
        monkeypatch.setattr(
            ip.QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: str(folder))
        )
        page = SimpleNamespace(
            _batch_worker=None,
            _astrometry=SimpleNamespace(wcs=object()),
            _engine=SimpleNamespace(target_set=lambda: tset, last_sequence_dir=None),
            _config=SimpleNamespace(sessions_path=tmp_path / "sessions"),
            _cfg=lambda key, default: default,
            _engine_egain=lambda: 1.723,
            _on_batch_done=lambda result: None,
        )
        ip.ImagingPage._on_rerun_subs(page)
        return _Recorder.requests, messages

    return run


def test_rerun_finds_the_light_frames_of_an_argos_session(tmp_path, rerun) -> None:
    """S12: an Argos lights/ folder of '.fit' frames gave 'No FITS files'."""
    run = tmp_path / "sessions" / "20261101T200000Z_SS_Cyg"
    (run / "session.json").parent.mkdir(parents=True)
    (run / "session.json").write_text("{}")
    first = run / "lights" / "SS_Cyg_ir_light_e010000ms_g080_00001.fit"
    second = run / "lights" / "SS_Cyg_ir_light_e010000ms_g080_00002.fit"
    _fits(second, "Light Frame", "2026-11-01T20:00:20")
    _fits(first, "Light Frame", "2026-11-01T20:00:00")
    _fits(run / "darks" / "SS_Cyg_dark_e010000ms_g080_00001.fit", "Dark Frame", "2026-11-01T21:00")

    requests, messages = rerun(run / "lights")
    assert messages == []
    assert [path.name for path in requests[-1].fits_paths] == [first.name, second.name]

    requests, messages = rerun(run)  # the session root: the darks are left out
    assert [path.name for path in requests[-1].fits_paths] == [first.name, second.name]
