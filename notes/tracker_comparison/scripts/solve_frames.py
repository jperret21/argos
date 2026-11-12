"""Plate-solve every frame of a folder independently with ASTAP.

Each frame's green plane (the plane Argos measures and solves) is solved on its
own through Argos's ``solve_array``, hinted at the target set's target.

``--mode truth`` (the ground truth): solved at downsample 2, 1 and 3 (5 degree
radius, no scale hint); the frame's solution is kept only when two of them
agree (every corner and the centre of the frame within 1 green px), else the
frame has no truth (``consensus: false``). Example: XX Cyg 2026-09-07 045156Z
frame 1, whose solves did not agree (the one recorded, 6.89″/px, is not used);
Argos's live settings solved that frame at 7.093″/px, 3.4 % off the run's 7.34.
``--mode argos``: one solve with the settings Argos's auto-solve uses
(``build_solve_settings(live=True)`` with the shipped defaults and the target
as the mount hint): what the live sequence path would have received.

One JSON line per frame: the WCS (CRVAL, CRPIX, CD), the solve time and the
exposure midpoint (DATE-OBS + EXPTIME/2). Nothing else of the header is copied
(no site, no observer).

    PYTHONPATH=<argos tree> python solve_frames.py <frames dir> <targets.json> <out.jsonl>
        [--astap /path/to/astap_cli] [--mode truth|argos] [--first N] [--count M]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

from argos.core.imaging.astrometry_session import build_solve_settings, wcs_from_result
from argos.core.imaging.green import green_plane
from argos.core.imaging.platesolve import SolveSettings, solve_array
from argos.workers.photometry_batch_worker import PhotometryBatchWorker, discover_light_frames


def _corners(wcs, shape):
    h, w = shape
    pts = [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1), (w / 2, h / 2)]
    return [wcs.pixel_to_world_deg(x, y) for x, y in pts], pts


def consensus_solve(plane, settings, shape):
    """Solve at downsample 2, 1, 3; the first two that agree within 1 green px."""
    from dataclasses import replace

    found = []
    last = None
    for down in (2, 1, 3):
        result = solve_array(plane, replace(settings, downsample=down))
        last = result
        wcs = wcs_from_result(result, shape) if result.solved else None
        if wcs is None:
            continue
        for other in found:
            sky, pix = _corners(other, shape)
            worst = 0.0
            for (ra, dec), (x, y) in zip(sky, pix):
                px, py = wcs.world_to_pixel_deg(ra, dec)
                worst = max(worst, float(np.hypot(float(px) - x, float(py) - y)))
            if worst < 1.0:
                return other, True, result
        found.append(wcs)
    return (found[0] if found else None), False, last


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("frames")
    ap.add_argument("targets")
    ap.add_argument("out")
    ap.add_argument("--astap", default="")
    ap.add_argument("--first", type=int, default=0)
    ap.add_argument("--count", type=int, default=0)
    ap.add_argument("--mode", default="truth", choices=("truth", "argos"))
    args = ap.parse_args(argv)

    tset = json.loads(Path(args.targets).read_text())
    target = next(s for s in tset["stars"] if s["role"] == "target")
    paths = discover_light_frames(Path(args.frames))
    paths = paths[args.first : (args.first + args.count) if args.count else None]
    settings = SolveSettings(
        astap_path=args.astap,
        search_radius_deg=5.0,
        downsample=2,
        ra_hint_hours=target["ra_deg"] / 15.0,
        dec_hint_deg=target["dec_deg"],
        timeout_s=60.0,
        allow_blind_retry=False,
    )
    with open(args.out, "w") as out:
        for index, path in enumerate(paths, start=args.first):
            raw, jd, _egain = PhotometryBatchWorker._read_frame(path)
            green = green_plane(raw)
            plane = np.clip(green, 0, 65535).astype(np.uint16)
            t0 = time.monotonic()
            if args.mode == "argos":
                live = build_solve_settings(
                    lambda key, default: args.astap if key == "astrometry.astap_path" else default,
                    green.shape,
                    live=True,
                    mount_radec=(target["ra_deg"] / 15.0, target["dec_deg"]),
                )
                result = solve_array(plane, live)
                wcs = wcs_from_result(result, green.shape) if result.solved else None
                consensus = None
            else:
                wcs, consensus, result = consensus_solve(plane, settings, green.shape)
            dt = time.monotonic() - t0
            row = {"frame": index, "file": path.name, "jd_mid": jd, "solve_s": round(dt, 3)}
            if consensus is not None:
                row["consensus"] = consensus
            if wcs is not None:
                row.update(crval=[wcs.crval1, wcs.crval2], crpix=[wcs.crpix1, wcs.crpix2])
                row["cd"] = list(wcs.cd)
            else:
                row["error"] = result.message
            out.write(json.dumps(row) + "\n")
            out.flush()
            print(f"{index:4d} {path.name} {'ok' if wcs else 'FAIL'} {dt:.2f}s", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
