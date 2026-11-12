"""How much a sub-pixel aperture shift moves a noisy run's differential magnitude.

    PYTHONPATH=<release tree> python ensemble_sensitivity.py <frames dir> <targets.json>
        <solves.jsonl> [--frame 0] [--shift 0.3]

Measures one frame through its own solution, then with every aperture moved by
+shift and -shift green px in x, and prints the target's and check's magnitude,
formal error, comparisons used and the ensemble note (one aperture: the series
FWHM of the first frame, the frame's EGAIN, the nearest comparison as check).
"""

from __future__ import annotations

import argparse
import dataclasses
import sys
from pathlib import Path

import numpy as np
from astropy.io import fits

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import load_solutions, load_target_set, star_key  # noqa: E402

from argos.core.imaging.green import green_plane  # noqa: E402
from argos.core.imaging.metrics import detect_stars  # noqa: E402
from argos.core.photometry.params import PhotometryParams, frame_egain, measure_frame  # noqa: E402
from argos.workers.photometry_batch_worker import discover_light_frames  # noqa: E402


class Shifted:
    def __init__(self, wcs, dx):
        self._wcs, self._dx = wcs, dx

    def world_to_pixel_deg(self, ra, dec):
        x, y = self._wcs.world_to_pixel_deg(ra, dec)
        return float(x) + self._dx, float(y)


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("frames")
    ap.add_argument("targets")
    ap.add_argument("solves")
    ap.add_argument("--frame", type=int, default=0)
    ap.add_argument("--shift", type=float, default=0.3)
    args = ap.parse_args(argv)
    paths = discover_light_frames(Path(args.frames))
    tset, _check = load_target_set(Path(args.targets))
    wcs = load_solutions(Path(args.solves))[args.frame]
    raw0 = np.asarray(fits.getdata(paths[0]), dtype=np.float32)
    fwhm = detect_stars(np.nan_to_num(raw0)).mean_fwhm
    raw, header = fits.getdata(paths[args.frame], header=True)
    params = PhotometryParams.from_config(lambda _key, default: default)
    params = dataclasses.replace(params, egain=frame_egain(header, {}) or params.egain)
    green = green_plane(np.asarray(raw, dtype=np.float32))
    for dx in (0.0, args.shift, -args.shift):
        for r in measure_frame(green, Shifted(wcs, dx), tset, params, fwhm=fwhm):
            if r.star.role in ("target", "check") and r.diff is not None:
                print(
                    f"shift {dx:+.1f} px  {r.star.role:6s} {star_key(r.star)}  "
                    f"mag {r.diff.mag:.4f}  err {r.diff.mag_err:.4f}  "
                    f"comps {r.diff.comps_used}  {r.diff.note or ''}"
                )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
