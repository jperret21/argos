"""Level 1 — Validate Alpaca telescope + camera communication.

Works with:
  - ASCOM Alpaca Simulator (localhost:32323, free download)
  - Real Seestar S30 Pro (any IP / port)

Download simulator:
  https://github.com/ASCOMInitiative/ASCOM.Alpaca.Simulators/releases
  → start it → it listens on localhost:32323

Usage:
    # Against simulator (default)
    .venv/bin/python scripts/validate_alpaca.py

    # Against real Seestar
    .venv/bin/python scripts/validate_alpaca.py 192.168.1.X 4700
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# ---------------------------------------------------------------------------

_failures: list[str] = []


def check(label: str, fn):
    """Run fn(), print OK or FAIL with value."""
    try:
        val = fn()
        print(f"  OK   {label}: {val}")
        return val
    except Exception as exc:
        print(f"  FAIL {label}: {exc}")
        _failures.append(label)
        return None


def section(title: str) -> None:
    print(f"\n{'─' * 55}")
    print(f"  {title}")
    print(f"{'─' * 55}")


# ---------------------------------------------------------------------------

def main() -> None:
    host = sys.argv[1] if len(sys.argv) > 1 else "localhost"
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 32323

    print(f"\nSeerControl — Alpaca validation  ({host}:{port})")

    # ── 0. Reachability ──────────────────────────────────────────────────
    section("0. Reachability")
    import requests
    try:
        r = requests.get(
            f"http://{host}:{port}/api/v1/telescope/0/connected",
            params={"ClientID": 1, "ClientTransactionID": 1},
            timeout=3,
        )
        print(f"  OK   HTTP probe: status={r.status_code}")
    except Exception as exc:
        print(f"  FAIL HTTP probe: {exc}")
        print("\nSeestar/simulator unreachable — cannot continue.")
        sys.exit(1)

    # ── 1. Telescope ──────────────────────────────────────────────────────
    section("1. Telescope (Alpaca)")
    from seercontrol.core.alpaca.telescope import Telescope
    scope = Telescope(host, port)

    name = check("connect", scope.connect)
    if name is None:
        print("  Telescope connection failed — stopping.")
        sys.exit(1)

    pos = check("get_position", scope.get_position)
    if pos:
        print(f"       RA={pos.ra_str()}  Dec={pos.dec_str()}"
              f"  Alt={pos.alt_str()}  Az={pos.az_str()}"
              f"  Tracking={pos.tracking}  Slewing={pos.slewing}")
        assert 0.0 <= pos.ra < 24.0,  f"RA out of range: {pos.ra}"
        assert -90.0 <= pos.dec <= 90.0, f"Dec out of range: {pos.dec}"
        print("  OK   RA/Dec range check passed")

    check("set_tracking ON",  lambda: scope.set_tracking(True))
    check("set_tracking OFF", lambda: scope.set_tracking(False))
    check("abort_slew",       scope.abort_slew)
    check("disconnect",       scope.disconnect)

    # ── 2. Camera ─────────────────────────────────────────────────────────
    section("2. Camera (Alpaca)")
    from seercontrol.core.alpaca.camera import Camera, BAYER_PATTERN, FOCAL_LENGTH

    print(f"  INFO Constants: BAYER_PATTERN={BAYER_PATTERN}  FOCAL_LENGTH={FOCAL_LENGTH}mm")
    assert BAYER_PATTERN == "GRBG", f"BAYER_PATTERN wrong: {BAYER_PATTERN} (expected GRBG)"
    assert FOCAL_LENGTH == 160,    f"FOCAL_LENGTH wrong: {FOCAL_LENGTH} (expected 160)"
    print("  OK   Constants are correct (GRBG, 160mm)")

    cam = Camera(host, port)
    cam_name = check("connect", cam.connect)
    if cam_name is None:
        print("  Camera connection failed — skipping exposure test.")
        return

    print(f"       Sensor: {cam.width}×{cam.height}  gain {cam.gain_min}–{cam.gain_max}")

    # Short 0.1s test exposure
    check("set_gain(80)", lambda: cam.set_gain(80))
    check("start_exposure(0.1s)", lambda: cam.start_exposure(0.1, light=True))

    print("  ...  Waiting for image (polling imageready)…")
    t0 = time.time()
    deadline = t0 + 30.0
    image_ok = False
    while not cam.is_image_ready():
        if time.time() > deadline:
            print("  FAIL imageready timeout after 30s")
            _failures.append("imageready")
            break
        time.sleep(0.2)
    else:
        elapsed = time.time() - t0
        print(f"  OK   imageready in {elapsed:.2f}s")
        image_ok = True

    if image_ok:
        arr = check("get_image_array", cam.get_image_array)
        if arr is not None:
            print(f"       shape={arr.shape}  dtype={arr.dtype}  "
                  f"min={arr.min()}  max={arr.max()}")
            assert arr.ndim == 2,                   f"Expected 2D array, got {arr.ndim}D"
            assert arr.dtype.kind in ('u', 'i', 'f'), f"Unexpected dtype: {arr.dtype}"
            print("  OK   Image shape and dtype valid")

    check("disconnect", cam.disconnect)

    # ── 3. FITS writer constants ───────────────────────────────────────────
    section("3. FITS writer constants")
    import numpy as np
    from datetime import datetime, timezone
    from seercontrol.core.imaging.fits_writer import FITSWriter
    import tempfile, pathlib

    dummy = np.zeros((100, 100), dtype=np.uint16)
    now   = datetime.now(timezone.utc)
    with tempfile.TemporaryDirectory() as tmp:
        path = pathlib.Path(tmp) / "test.fits"
        check("write FITS", lambda: FITSWriter.write(
            arr=dummy,
            path=path,
            exposure_start=now,
            exposure_end=now,
            exposure_time=0.1,
            gain=80,
            image_type="Light Frame",
            ra=5.575,
            dec=-5.39,
            altitude=42.0,
            azimuth=180.0,
            object_name="TEST",
            filter_name="LRGB",
            observer="Test",
            site_lat=48.8,
            site_lon=2.3,
            site_elev=100.0,
        ))

        if path.exists():
            from astropy.io import fits as astropy_fits
            with astropy_fits.open(path) as hdul:
                hdr = hdul[0].header
                bayer = hdr.get("BAYERPAT", "MISSING")
                foclen = hdr.get("FOCALLEN", "MISSING")
                print(f"  OK   BAYERPAT={bayer}  FOCALLEN={foclen}")
                assert bayer == "GRBG", f"BAYERPAT wrong in FITS: {bayer}"
                assert foclen == 160,   f"FOCALLEN wrong in FITS: {foclen}"
                print("  OK   FITS headers correct")

    # ── Done ──────────────────────────────────────────────────────────────
    print(f"\n{'═' * 55}")
    if _failures:
        print(f"  ÉCHEC — {len(_failures)} check(s) failed: {', '.join(_failures)}")
        sys.exit(1)
    else:
        print("  TOUT OK — communication Alpaca validée.")
    print(f"{'═' * 55}\n")


if __name__ == "__main__":
    main()
