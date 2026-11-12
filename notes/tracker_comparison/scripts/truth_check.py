"""Check the truth against the image: each star's centroid near its truth position.

For every frame with a truth solve, the green-plane centroid (core's
``refine_centroid``, the tracker's own centroiding) is taken within 6 green px of
the star's truth position, and its distance is reported to:

- ``catalogue``: the J2000.0 catalogue position through the frame's solve (the
  truth of the study before the science review of 2026-11-12);
- ``truth``: the position the study now uses (``common.truth_xy``: the catalogue
  position moved to the frame's date by the star's proper motion, when
  ``proper_motions.json`` gives one).

Only centroids with a star in the window are kept (``refine_centroid`` returns
None otherwise). Output: ``<notes dir>/truth_check.json``.

    PYTHONPATH=<release tree> python truth_check.py <copies dir> <study dir> <notes dir>
"""

from __future__ import annotations

import json
import math
import statistics
import sys
from pathlib import Path

import numpy as np
from astropy.io import fits

sys.path.insert(0, str(Path(__file__).resolve().parent))

from argos.core.imaging.green import green_plane  # noqa: E402
from argos.core.photometry.tracking import refine_centroid  # noqa: E402
from argos.workers.photometry_batch_worker import discover_light_frames  # noqa: E402
from common import PROPER_MOTIONS, load_solutions, load_target_set, truth_xy  # noqa: E402

SEARCH_PX = 6.0


def pct(values, q):
    if not values:
        return None
    s = sorted(values)
    return s[min(len(s) - 1, int(round(q * (len(s) - 1))))]


def summary(values):
    return {
        "n": len(values),
        "median_px": round(statistics.median(values), 2) if values else None,
        "p95_px": round(pct(values, 0.95), 2) if values else None,
        "max_px": round(max(values), 2) if values else None,
    }


def check_run(frames_dir: Path, targets: Path, solves: Path) -> dict:
    solutions = load_solutions(solves)
    tset, _check = load_target_set(targets, "none")
    paths = discover_light_frames(frames_dir)
    out = {"target": {"catalogue": [], "truth": []}, "comparison": {"catalogue": [], "truth": []}}
    for index, path in enumerate(paths):
        wcs = solutions.get(index)
        if wcs is None:
            continue
        green = green_plane(np.asarray(fits.getdata(path)))
        green = np.nan_to_num(green.astype(np.float32))
        for star in tset.stars:
            role = "target" if star.role == "target" else "comparison"
            truth = truth_xy(solutions, index, star)
            cat = tuple(float(v) for v in wcs.world_to_pixel_deg(star.ra_deg, star.dec_deg))
            if truth is None:
                continue
            centre = refine_centroid(green, truth[0], truth[1], SEARCH_PX)
            if centre is None:
                continue
            out[role]["catalogue"].append(math.hypot(cat[0] - centre[0], cat[1] - centre[1]))
            out[role]["truth"].append(math.hypot(truth[0] - centre[0], truth[1] - centre[1]))
    return {role: {k: summary(v) for k, v in d.items()} for role, d in out.items()}


def main(argv):
    data, study, notes = Path(argv[0]), Path(argv[1]), Path(argv[2])
    result = {
        "search_px": SEARCH_PX,
        "proper_motions_applied": sorted(PROPER_MOTIONS),
        "runs": {},
    }
    for run_dir in sorted(p for p in data.iterdir() if (p / "targets.json").exists()):
        run = run_dir.name
        solves = study / "solves" / f"{run}.jsonl"
        if not solves.exists():
            continue
        result["runs"][run] = check_run(run_dir / "lights", run_dir / "targets.json", solves)
        print(run, json.dumps(result["runs"][run]["target"]))
    (notes / "truth_check.json").write_text(json.dumps(result, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
