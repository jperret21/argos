"""POST /api/camera/open-fits: accepted formats, orientation, refusals."""

from __future__ import annotations

import numpy as np
import pytest
from astropy.io import fits

from tests.server.conftest import AUTH, TOKEN, decode_frame, receive_bytes


def _write(path, data, **header):
    hdu = fits.PrimaryHDU(data=data)
    for key, value in header.items():
        hdu.header[key.replace("_", "-")] = value
    hdu.writeto(path)
    return path


def _open(client, path):
    return client.post("/api/camera/open-fits", json={"path": str(path)}, headers=AUTH)


def test_uint16_fits_is_published_unflipped(client, tmp_path):
    data = np.arange(12 * 10, dtype=np.uint16).reshape(12, 10) * 500
    data[0, 0] = 65535  # FITS row 0 must come out as frame row 0
    path = _write(tmp_path / "m42.fits", data, EXPTIME=12.5, DATE_OBS="2026-10-31T22:15:00.5")
    with client.websocket_connect(f"/ws/frames?token={TOKEN}") as frames:
        response = _open(client, path)  # no connection needed: offline replay
        assert response.status_code == 200, response.text
        header, pixels = decode_frame(receive_bytes(frames))
    np.testing.assert_array_equal(pixels, data)
    assert header["source"] == "file"
    assert header["exposure_s"] == 12.5
    assert header["timestamp"] == "2026-10-31T22:15:00.500Z"
    assert response.json()["last_frame_seq"] == header["seq"]


@pytest.mark.parametrize("suffix", [".fit", ".fts", ".FITS"])
def test_all_fits_suffixes_are_accepted(client, tmp_path, suffix):
    path = _write(tmp_path / f"frame{suffix}", np.ones((4, 4), np.uint16))
    assert _open(client, path).status_code == 200


def test_integral_float_fits_is_raw_counts(client, tmp_path):
    """S4 (``_raw_adu``): whole numbers 0…65535 are raw counts whatever the stored type."""
    data = np.array([[0.0, 1234.0], [65535.0, 7.0]], dtype=np.float32)
    path = _write(tmp_path / "integral.fit", data)
    with client.websocket_connect(f"/ws/frames?token={TOKEN}") as frames:
        assert _open(client, path).status_code == 200
        _, pixels = decode_frame(receive_bytes(frames))
    assert pixels.tolist() == [[0, 1234], [65535, 7]]


@pytest.mark.parametrize(
    "data, reason",
    [
        # Siril's 32-bit [0, 1] output, a calibrated or stacked frame: not raw counts.
        (np.array([[0.0, 0.5], [1.0, 0.25]], dtype=np.float32), "floating-point"),
        (np.array([[0.0, 1.0], [2.0, np.nan]], dtype=np.float32), "floating-point"),
        (np.array([[100.0, np.inf], [0.0, 2.0]], dtype=np.float32), "floating-point"),
        # A dark-subtracted frame: a uint16 cast would wrap -5 to 65531.
        (np.array([[-5, 10], [20, 30]], dtype=np.int32), "do not fit"),
        (np.array([[70000, 10], [20, 30]], dtype=np.int32), "do not fit"),
    ],
)
def test_non_raw_data_is_refused_and_the_frame_kept(client, tmp_path, data, reason):
    """A27 / S4: the live pipeline takes raw 16-bit counts only; nothing is published."""
    good = _write(tmp_path / "good.fits", np.full((4, 4), 1000, np.uint16))
    assert _open(client, good).status_code == 200
    before = client.get("/api/status", headers=AUTH).json()["camera"]["last_frame_seq"]
    response = _open(client, _write(tmp_path / "calibrated.fits", data))
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "invalid_fits" and reason in error["message"]
    assert "open the raw .fit frame instead" in error["message"]
    after = client.get("/api/status", headers=AUTH).json()["camera"]["last_frame_seq"]
    assert after == before  # the current frame, its time and its metrics are untouched


def test_rgb_cube_is_refused(client, tmp_path):
    cube = np.zeros((3, 2, 2), np.uint16)
    response = _open(client, _write(tmp_path / "rgb.fits", cube))
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_fits"
    assert "2-D raw image" in response.json()["error"]["message"]


def test_single_plane_cube_is_a_2d_image(client, tmp_path):
    cube = np.full((1, 3, 4), 42, np.uint16)
    assert _open(client, _write(tmp_path / "plane.fits", cube)).status_code == 200


def test_text_file_is_rejected(client, tmp_path):
    path = tmp_path / "notes.txt"
    path.write_text("not an image")
    response = _open(client, path)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_argument"


def test_relative_path_is_rejected(client):
    response = client.post("/api/camera/open-fits", json={"path": "frame.fits"}, headers=AUTH)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_argument"


def test_missing_file_is_404(client, tmp_path):
    response = _open(client, tmp_path / "missing.fits")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_corrupt_fits_is_reported(client, tmp_path):
    path = tmp_path / "broken.fits"
    path.write_bytes(b"SIMPLE  = garbage" * 10)
    response = _open(client, path)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_fits"


def test_open_fits_stops_live_view_first(connected, tmp_path):
    """Q-O11: the opened frame must not be replaced by the next live frame."""
    path = _write(tmp_path / "frame.fits", np.ones((4, 4), np.uint16))
    connected.post("/api/camera/live", json={"exposure_s": 0.05, "gain": 80}, headers=AUTH)
    response = _open(connected, path)
    assert response.status_code == 200, response.text
    camera = connected.get("/api/status", headers=AUTH).json()["camera"]
    assert camera["state"] == "idle" and camera["owner"] == "idle"
    messages = [e["message"] for e in connected.get("/api/logs", headers=AUTH).json()["entries"]]
    assert "Live view stopped to open frame.fits." in messages


def test_open_fits_refused_during_a_single_capture(connected, tmp_path):
    path = _write(tmp_path / "frame.fits", np.ones((4, 4), np.uint16))
    connected.post("/api/camera/capture", json={"exposure_s": 5.0, "gain": 80}, headers=AUTH)
    response = _open(connected, path)
    assert response.status_code == 409 and response.json()["error"]["code"] == "busy"
    connected.post("/api/camera/stop", headers=AUTH)


def test_oversized_image_is_refused_from_its_header(client, tmp_path):
    # 20000 px wide is past any GPU texture limit (16384): refused before loading.
    path = _write(tmp_path / "mosaic.fits", np.zeros((2, 20000), np.uint8))
    response = _open(client, path)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_fits"
    assert "too large" in response.json()["error"]["message"]


def test_unreadable_path_is_a_400_not_a_crash(client, tmp_path):
    path = tmp_path / ("a" * 300 + ".fits")  # ENAMETOOLONG from the OS
    response = _open(client, path)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_argument"
