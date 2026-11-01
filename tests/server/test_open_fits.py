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


def test_float_fits_normalised_to_one_is_scaled(client, tmp_path):
    data = np.array([[0.0, 0.5], [1.0, np.nan]], dtype=np.float32)
    path = _write(tmp_path / "siril.fit", data)
    with client.websocket_connect(f"/ws/frames?token={TOKEN}") as frames:
        _open(client, path)
        _, pixels = decode_frame(receive_bytes(frames))
    assert pixels.tolist() == [[0, 32768], [65535, 0]]


def test_rgb_cube_becomes_interleaved_channels(client, tmp_path):
    cube = np.zeros((3, 2, 2), np.uint16)
    cube[0], cube[1], cube[2] = 10, 20, 30
    path = _write(tmp_path / "rgb.fits", cube)
    with client.websocket_connect(f"/ws/frames?token={TOKEN}") as frames:
        _open(client, path)
        header, pixels = decode_frame(receive_bytes(frames))
    assert header["channels"] == 3
    assert pixels[0, 0].tolist() == [10, 20, 30]


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


def test_open_fits_refused_during_live_view(connected, tmp_path):
    path = _write(tmp_path / "frame.fits", np.ones((4, 4), np.uint16))
    connected.post("/api/camera/live", json={"exposure_s": 0.05, "gain": 80}, headers=AUTH)
    response = _open(connected, path)
    assert response.status_code == 409 and response.json()["error"]["code"] == "busy"
    connected.post("/api/camera/stop", headers=AUTH)


def test_plus_infinity_is_saturated_not_black(client, tmp_path):
    data = np.array([[100.0, np.inf], [-np.inf, 2000.0]], dtype=np.float32)
    path = _write(tmp_path / "sat.fits", data)
    with client.websocket_connect(f"/ws/frames?token={TOKEN}") as frames:
        _open(client, path)
        _, pixels = decode_frame(receive_bytes(frames))
    assert pixels.tolist() == [[100, 65535], [0, 2000]]


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
