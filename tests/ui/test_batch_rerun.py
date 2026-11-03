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


def _or_default(value, default):
    """ImagingPage._cfg: a stored None reads as the default."""
    return default if value is None else value


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

    def run(folder, site=None):
        from argos.core.config import _DEFAULTS, Config

        monkeypatch.setattr(
            ip.QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: str(folder))
        )
        config = Config({"site": dict(_DEFAULTS["site"], **(site or {}))})
        page = SimpleNamespace(
            _batch_worker=None,
            _astrometry=SimpleNamespace(wcs=object()),
            _engine=SimpleNamespace(target_set=lambda: tset, last_sequence_dir=None),
            _config=SimpleNamespace(sessions_path=tmp_path / "sessions", get=config.get),
            _cfg=lambda key, default: _or_default(config.get(key, default), default),
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


def test_rerun_writes_into_a_new_folder_of_the_session(tmp_path, rerun) -> None:
    """S13: the output went to <sessions>/../targets/, the same for every run."""
    run = tmp_path / "sessions" / "20261101T200000Z_SS_Cyg"
    _fits(run / "lights" / "a.fit", "Light Frame", "2026-11-01T20:00:00")
    (run / "session.json").write_text("{}")

    requests, _messages = rerun(run / "lights")

    out_dir = requests[-1].out_dir
    assert out_dir.parent == run and out_dir.name.startswith("photometry_rerun_")


def test_rerun_without_a_site_computes_no_airmass_at_latitude_0_longitude_0(
    tmp_path, rerun
) -> None:
    """The re-run got the config's 0/0 defaults as its site: every point's
    airmass (CSV, AAVSO AMASS) and BJD_TDB were computed for 0/0."""
    run = tmp_path / "sessions" / "20261101T200000Z_SS_Cyg"
    _fits(run / "lights" / "a.fit", "Light Frame", "2026-11-01T20:00:00")

    requests, _messages = rerun(run / "lights")
    assert requests[-1].site == (None, None, 0.0)

    requests, _messages = rerun(
        run / "lights",
        site={"name": "Paris", "latitude": 48.85, "longitude": 2.35, "elevation": 35.0},
    )
    assert requests[-1].site == (48.85, 2.35, 35.0)


def test_cancelled_batch_is_reported_and_not_adopted() -> None:
    """S13: a cancelled run was announced as a success and its partial
    curves replaced the live ones."""
    import argos.ui.pages.imaging_page as ip
    from argos.core.photometry.lightcurve import LcPoint, LightCurve
    from argos.workers.photometry_batch_worker import BatchResult

    logs: list[tuple[str, str]] = []
    adopted: list = []
    page = SimpleNamespace(
        _batch_dialog=None,
        _batch_worker=object(),
        _batch_total=3,
        log_message=SimpleNamespace(emit=lambda level, msg: logs.append((level, msg))),
        _engine=SimpleNamespace(adopt_curves=adopted.append),
        _open_photometry=lambda: None,
        _cfg=lambda key, default: default,
    )
    partial = LightCurve(auid="T", name="T", role="target")
    partial.append(LcPoint(jd_utc=2461315.5, mag=12.0, mag_err=0.02))
    ip.ImagingPage._on_batch_done(
        page, BatchResult(curves={"T": partial}, frames_done=1, cancelled=True)
    )

    assert adopted == []
    assert any("cancelled" in msg for _level, msg in logs), logs
    assert not any(level == "OK" for level, _msg in logs), logs
