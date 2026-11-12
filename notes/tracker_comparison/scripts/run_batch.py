"""Run Qt's batch re-run (PhotometryBatchWorker) on copies and record every aperture.

The worker is the one on ``PYTHONPATH`` (run it once on the code before S43 and
once after). The reference solution is one frame's own ASTAP solve, as when
the observer solves one frame and re-runs the folder. With ``--solver`` the
S43 re-solve is given a solver: ``astap`` is the page's solver
(``batch_frame_solver``: the shipped live settings near the reference centre),
``cached`` returns that frame's solution from
``solve_frames.py`` output (the same ASTAP solve, without the 0.2-0.5 s).

Output: one JSON line per (frame, star) with the aperture centre the worker
used (its flight recorder), the frame's own solution of the star (truth), the
point it wrote (mag, err, suspect) and the frame's tracking state; then one
``summary`` line (frames done, the result's tracking summary).

    PYTHONPATH=<release tree> python run_batch.py <frames dir> <targets.json>
        <solves.jsonl> <out.jsonl> [--first N] [--count M] [--reference K]
        [--check nearest|none|AUID] [--solver none|astap|cached] [--astap PATH]
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import math
import sys
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import load_solutions, load_target_set, star_key, truth_xy  # noqa: E402

from argos.core.photometry.params import PhotometryParams  # noqa: E402
from argos.workers.photometry_batch_worker import (  # noqa: E402
    BatchRequest,
    PhotometryBatchWorker,
    discover_light_frames,
)


def make_solver(kind: str, reference, solutions, frame_of_green, astap: str):
    if kind == "none":
        return None
    if kind == "cached":
        return lambda green: solutions.get(frame_of_green(green))
    # The page's solver (imaging_page.py ``_on_rerun_subs``): the shipped settings,
    # ASTAP at ``astap``, near the reference solve's centre.
    from argos.core.imaging.astrometry_session import batch_frame_solver

    cfg = lambda key, default: astap if key == "astrometry.astap_path" else default  # noqa: E731
    return batch_frame_solver(cfg, (reference.crval1 / 15.0 % 24.0, reference.crval2))


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("frames")
    ap.add_argument("targets")
    ap.add_argument("solves")
    ap.add_argument("out")
    ap.add_argument("--first", type=int, default=0)
    ap.add_argument("--count", type=int, default=0)
    ap.add_argument("--reference", type=int, default=None, help="frame whose solve is used")
    ap.add_argument("--check", default="nearest")
    ap.add_argument("--solver", default="none", choices=("none", "astap", "cached"))
    ap.add_argument("--astap", default="")
    args = ap.parse_args(argv)

    solutions = load_solutions(Path(args.solves))
    jd_of = {
        json.loads(line)["frame"]: json.loads(line)["jd_mid"]
        for line in Path(args.solves).read_text().splitlines()
    }
    paths = discover_light_frames(Path(args.frames))
    end = (args.first + args.count) if args.count else len(paths)
    indices = list(range(args.first, end))
    paths = paths[args.first : end]
    reference = solutions[args.reference if args.reference is not None else args.first]
    tset, check = load_target_set(Path(args.targets), args.check)
    stars = {star_key(s): s for s in tset.stars}

    # The green plane of each frame, to tell the cached solver which frame it got.
    frame_by_sum: dict[float, int] = {}

    def frame_of_green(green) -> int | None:
        return frame_by_sum.get(float(np.sum(green[::64, ::64], dtype=np.float64)))

    if args.solver == "cached":
        from argos.core.imaging.green import green_plane

        for index, path in zip(indices, paths):
            raw, _jd, _g = PhotometryBatchWorker._read_frame(path)
            frame_by_sum[float(np.sum(green_plane(raw)[::64, ::64], dtype=np.float64))] = index
    solver = make_solver(args.solver, reference, solutions, frame_of_green, args.astap)

    params = PhotometryParams.from_config(lambda _key, default: default)
    out_dir = Path(tempfile.mkdtemp(prefix="batch_"))
    request = BatchRequest(
        fits_paths=paths,
        wcs=reference,
        target_set=tset,
        params=params,
        out_dir=out_dir,
        object_name=tset.object_name or "run",
        diagnostics=True,
        egain_table={},
    )
    names = {f.name for f in dataclasses.fields(BatchRequest)}
    if solver is not None:
        if "solver" not in names:
            raise SystemExit("this worker has no solver (the code before S43)")
        request.solver = solver
    from PyQt6.QtCore import QCoreApplication

    _app = QCoreApplication.instance() or QCoreApplication([])  # noqa: F841
    worker = PhotometryBatchWorker(request)
    results = []
    worker.finished_batch.connect(results.append)
    worker.run()
    result = results[0]

    diag_file = next(out_dir.glob("*_diagnostics.jsonl"))
    docs = [json.loads(line) for line in diag_file.read_text().splitlines()]
    # The recorder numbers measured frames 0..n-1; map them back to frame indices.
    measured = [d for d in docs if d["kind"] == "frame"]
    by_file = {p.name: i for i, p in zip(indices, paths)}
    frame_index = {d["frame"]: by_file[d["file"]] for d in measured}
    tracking = {frame_index[d["frame"]]: d for d in docs if d["kind"] == "tracking"}
    events: dict[int, list[str]] = {}
    for d in docs:
        if d["kind"] == "event" and "frame" in d and d["frame"] in frame_index:
            events.setdefault(frame_index[d["frame"]], []).append(d["what"])
    points: dict[tuple[int, str], object] = {}
    frame_of_jd = {round(jd_of[i], 9): i for i in indices if jd_of.get(i) is not None}
    for key, curve in result.curves.items():
        for p in curve.points:
            points[(frame_of_jd[round(p.jd_utc, 9)], key)] = p

    with open(args.out, "w") as out:
        for d in docs:
            if d["kind"] != "star":
                continue
            frame = frame_index[d["frame"]]
            key = d.get("auid") or d.get("name")
            star = stars.get(key)
            truth = truth_xy(solutions, frame, star) if star is not None else None
            p = points.get((frame, key))
            row = {
                "frame": frame,
                "key": key,
                "role": d.get("role"),
                "x": d.get("x"),
                "y": d.get("y"),
                "tx": truth[0] if truth else None,
                "ty": truth[1] if truth else None,
                "snr": d.get("snr"),
                "inst_mag": d.get("inst_mag") if p is not None else None,
                "inst_err": d.get("inst_mag_err") if p is not None else None,
                "point": p is not None,
                "mag": p.mag if p is not None and math.isfinite(p.mag) else None,
                "mag_err": p.mag_err if p is not None and math.isfinite(p.mag_err) else None,
                "formal_err": p.formal_mag_err if p is not None else None,
                "suspect": bool(p.suspect) if p is not None else None,
                "anchors": tracking.get(frame, {}).get("anchors"),
                "frames_lost": tracking.get(frame, {}).get("frames_lost"),
                "events": events.get(frame, []),
            }
            out.write(json.dumps(row) + "\n")
        summary = {
            "summary": True,
            "check": check,
            "frames": len(paths),
            "frames_done": result.frames_done,
            "frames_skipped": result.frames_skipped,
            "rotation_deg": result.rotation_deg,
            "shift_px": result.shift_px,
        }
        for extra in ("frames_resolved", "frames_unanchored", "tracked"):
            if hasattr(result, extra):
                summary[extra] = getattr(result, extra)
        out.write(json.dumps(summary) + "\n")
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
