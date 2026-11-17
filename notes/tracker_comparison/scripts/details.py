"""Numbers the study quotes beyond the tables: jump frames, lag, a wrong solve, timings.

    python details.py <study dir> <out.json> [<copies dir>]

Reads run_all.sh output only (no frames). Sections:
- ``jumps``: RR Lyr frames whose target moved more than the tracker's search
  radius since the previous frame (truth), and each arm's state and placement
  error there;
- ``lag``: for each live arm re-solved per frame, the target's placement error
  against the frame-to-frame motion of the field (least-squares slope through 0,
  and the median error for motions under and over 4 px): a centroid window
  centred on the prediction lags a moving star; ``lag_comparisons``: the same on
  the comparison stars (the target's error carries RR Lyr's proper motion);
- ``wrong_solve``: every star of the frame measured through the one wrong
  solution found (20260907T045156Z XX Cyg, frame 2 through frame 1's solve);
- ``solve_s``: solve times, truth (2-3 solves per frame) and Argos settings;
- ``first80``: the S43 evidence, RR Lyr frames 0-79 through frame 0's solve
  with the owner's target set (``run_all.sh``), frames 52-79, before and with S43;
- ``solo_qt_after_jump``: Qt's tracker with one solve, the kept frames after 52;
- ``owner_live``: with ``<copies dir>`` holding a copy of the wrong-solve run's
  ``diagnostics/`` and ``photometry/`` (the owner's live run): the target's
  aperture on frame 2 by its live flight recorder, against the frame's truth,
  and the first rows of its live target CSV.
"""

from __future__ import annotations

import json
import math
import statistics
import sys
from pathlib import Path

RR = "20260925T200453Z_RR_Lyr"
WRONG = ("20260907T045156Z_XX_Cyg", 2)


def rows(study, run, suffix):
    out = [
        json.loads(x) for x in (study / "runs" / f"{run}_{suffix}.jsonl").read_text().splitlines()
    ]
    return [r for r in out if not r.get("summary")]


def err(r):
    if r.get("x") is None or r.get("tx") is None:
        return None
    return math.hypot(r["x"] - r["tx"], r["y"] - r["ty"])


def lag_stats(seq, steps, arm, role):
    """Placement error against the frame-to-frame motion, kept frames, jumps excluded."""
    pairs = []
    for r in seq:
        if r["arm"] == arm and r["role"] == role and r["state"] == "kept":
            e, d = err(r), steps.get(r["frame"])
            if e is not None and d is not None and d < 15.0:
                pairs.append((d, e))
    slope = sum(d * e for d, e in pairs) / sum(d * d for d, e in pairs)
    return {
        "points": len(pairs),
        "slope_px_per_px": round(slope, 3),
        "median_err_motion_lt_4px": round(statistics.median(e for d, e in pairs if d < 4), 2),
        "median_err_motion_ge_4px": round(statistics.median(e for d, e in pairs if d >= 4), 2),
        "n_lt_4px": sum(1 for d, _e in pairs if d < 4),
        "median_motion_px": round(statistics.median(d for d, _e in pairs), 2),
    }


def main(argv):
    study, out = Path(argv[0]), Path(argv[1])
    result = {}
    seq = rows(study, RR, "seq")
    solo = rows(study, RR, "solo")
    truth = {r["frame"]: r for r in seq if r["arm"] == "truth" and r["role"] == "target"}
    steps = {}
    for f, r in truth.items():
        p = truth.get(f - 1)
        if p is not None:
            steps[f] = math.hypot(r["tx"] - p["tx"], r["ty"] - p["ty"])
    jumps = sorted(f for f, d in steps.items() if d > 15.0)
    result["jumps"] = {}
    batch = {
        name: {r["frame"]: r for r in rows(study, RR, name) if r["role"] == "target"}
        for name in ("batch_before", "batch_s43")
    }
    for f in jumps:
        entry = {"step_px": round(steps[f], 1)}
        for label, data in (("seq", seq), ("solo", solo)):
            for r in data:
                if r["frame"] == f and r["role"] == "target" and r["arm"] in ("qt", "web"):
                    e = err(r)
                    entry[f"{label}_{r['arm']}"] = {
                        "state": r["state"],
                        "point": r["point"],
                        "err_px": round(e, 2) if e is not None else None,
                        "anchors": r["anchors"],
                        "health": r.get("health"),
                    }
        for name, data in batch.items():
            r = data.get(f)
            if r is not None:
                e = err(r)
                entry[name] = {
                    "point": r["point"],
                    "suspect": r.get("suspect"),
                    "err_px": round(e, 2) if e is not None else None,
                    "events": r.get("events"),
                }
        result["jumps"][str(f)] = entry
    # The target's error includes RR Lyr's proper motion (0.8 px, applied to the truth,
    # not by the apps); the comparison stars (none applied) show the tracker alone.
    for key, role in (("lag", "target"), ("lag_comparisons", "comparison")):
        result[key] = {}
        for arm in ("qt", "web"):
            result[key][arm] = lag_stats(seq, steps, arm, role)
    run, frame = WRONG
    wrong = rows(study, run, "seq")
    result["wrong_solve"] = [
        {
            "arm": r["arm"],
            "star": r["key"],
            "role": r["role"],
            "err_px": round(err(r), 1) if err(r) is not None else None,
            "point": r["point"],
            "mag": round(r["mag"], 3) if r.get("mag") is not None else None,
            "snr": round(r["snr"], 1) if r.get("snr") is not None else None,
            "anchors": r["anchors"],
            "health": r.get("health"),
        }
        for r in wrong
        if r["frame"] == frame
    ]
    times = {"truth": [], "argos": []}
    for path in (study / "solves").glob("*.jsonl"):
        kind = "argos" if path.stem.endswith("_argos") else "truth"
        times[kind] += [json.loads(x)["solve_s"] for x in path.read_text().splitlines()]
    result["solve_s"] = {
        k: {"n": len(v), "median": round(statistics.median(v), 2), "max": round(max(v), 2)}
        for k, v in times.items()
    }
    result["first80"] = {}
    for name in ("before", "s43"):
        path = study / "runs" / f"{RR}_first80_batch_{name}.jsonl"
        if not path.exists():
            continue
        tgt = [
            r
            for r in rows(study, RR, f"first80_batch_{name}")
            if r["role"] == "target" and r["frame"] >= 52
        ]
        good = [r for r in tgt if r["point"] and not r.get("suspect")]
        errs = [err(r) for r in good if err(r) is not None]
        mags = [r["mag"] for r in good if r.get("mag") is not None]
        result["first80"][name] = {
            "frames": len(tgt),
            "unflagged_points": len(good),
            "flagged_points": sum(1 for r in tgt if r["point"] and r.get("suspect")),
            "no_point": sum(1 for r in tgt if not r["point"]),
            "err_px": [round(min(errs), 1), round(max(errs), 1)] if errs else None,
            "mag": [round(min(mags), 2), round(max(mags), 2)] if mags else None,
        }
    kept = [
        r
        for r in solo
        if r["arm"] == "qt" and r["role"] == "target" and r["frame"] > 52 and r["point"]
    ]
    with_truth = [err(r) for r in kept if err(r) is not None]
    result["solo_qt_after_jump"] = {
        "kept": len(kept),
        "within_2px": sum(1 for e in with_truth if e < 2.0),
        "without_truth": len(kept) - len(with_truth),
        "max_err_px": round(max(with_truth), 1),
    }
    if len(argv) > 2:
        copy = Path(argv[2]) / run
        diag = next((copy / "diagnostics").glob("*_live_diagnostics.jsonl"))
        live = [json.loads(x) for x in diag.read_text().splitlines()]
        star = next(
            d for d in live if d["kind"] == "star" and d["frame"] == frame and d["role"] == "target"
        )
        truth2 = next(
            r
            for r in wrong
            if r["arm"] == "truth" and r["frame"] == frame and r["role"] == "target"
        )
        csv = next((copy / "photometry").glob("target_*.csv")).read_text().splitlines()
        head = csv[0].split(",")
        first = [dict(zip(head, line.split(","))) for line in csv[1:4]]
        result["owner_live"] = {
            "frame": frame,
            "snr": star["snr"],
            "offset_px": round(math.hypot(star["x"] - truth2["tx"], star["y"] - truth2["ty"]), 1),
            "csv_first_rows": [(row["mag"], row["mag_err"]) for row in first],
        }
    out.write_text(json.dumps(result, indent=1) + "\n")
    print(json.dumps(result, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
