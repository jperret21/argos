"""Tables and SVG figures of the tracker comparison, from replay.py and run_batch.py output.

    PYTHONPATH=<release tree> python analyze.py <copies dir> <study dir> <notes dir>

<copies dir>/<run>/targets.json, <study dir>/solves/ and <study dir>/runs/<run>_{seq,solo,batch_before,batch_s43}.jsonl (run_all.sh) ->
<notes dir>/results.json (every number of the study), <notes dir>/tables.md and
<notes dir>/*.svg. Pure Python (no plotting library is installed or added).

Definitions (all positions in green px, the plane Argos measures):
- placement error: distance between the aperture centre an arm used and the
  star's position by the frame's own ASTAP solution (truth), the star moved to
  the frame's date by its proper motion when proper_motions.json gives one
  (RR Lyr: 0.8 px since J2000.0; both apps place apertures at the catalogue
  position, so that offset is part of every arm's error);
- kept: a point written unflagged; flagged: written with ``suspect`` (the S43
  batch); lost: no point (S35 skip, or no magnitude);
- off-star point: a kept target point whose aperture is more than 2 px from the
  truth (the aperture radius is 5.5-7.5 px);
- dmag: arm magnitude minus truth magnitude on the same frame (mmag); dinst:
  the same for the target's instrumental magnitude (placement alone, without
  the ensemble).
"""

from __future__ import annotations

import json
import math
import statistics
import sys
from pathlib import Path

ARMS = {
    # key: (label, file suffix, arm name inside the file)
    "seq_qt": ("Qt sequence path (re-solve per frame)", "seq", "qt"),
    "seq_web": ("Web FieldTracker (re-solve per frame)", "seq", "web"),
    "solo_qt": ("Qt ApertureTracker + S35 (one solve)", "solo", "qt"),
    "solo_web": ("Web FieldTracker (one solve)", "solo", "web"),
    "batch_before": ("Qt batch before S43 (one solve)", "batch_before", None),
    "batch_s43": ("Qt batch with S43 (one solve + re-solve on loss)", "batch_s43", None),
}
OFF_STAR_PX = 2.0
COLORS = {  # dataviz reference categorical order, validated (light surface)
    "qt": "#2a78d6",
    "web": "#eb6834",
    "batch_s43": "#1baf7a",
    "batch_before": "#eda100",
    "truth": "#52514e",
}


def load(path: Path):
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    return [r for r in rows if not r.get("summary")], next(r for r in rows if r.get("summary"))


def pct(values, q):
    v = sorted(values)
    if not v:
        return None
    k = (len(v) - 1) * q
    lo, hi = math.floor(k), math.ceil(k)
    return v[lo] + (v[hi] - v[lo]) * (k - lo)


def err(r):
    if r.get("x") is None or r.get("tx") is None:
        return None
    return math.hypot(r["x"] - r["tx"], r["y"] - r["ty"])


def arm_rows(study: Path, run: str, arm: str):
    _label, suffix, inner = ARMS[arm]
    path = study / "runs" / f"{run}_{suffix}.jsonl"
    rows, summary = load(path)
    if inner is not None:
        rows = [r for r in rows if r["arm"] == inner]
    else:
        for r in rows:
            r["state"] = "lost" if not r["point"] else ("flagged" if r.get("suspect") else "kept")
            r["point"] = r["point"] and not r.get("suspect")
    return rows, summary


def target_star(data: Path, run: str):
    """The run's target, from the copy's ``targets.json``."""
    from argos.core.catalog.targets import TargetSet

    return TargetSet.load(data / run / "targets.json").by_role("target")[0]


def night_of(run: str) -> str:
    """``<object>_<YYYYMMDD>`` of a run folder ``<UTC stamp>_<object>``."""
    return run.split("_", 1)[1] + "_" + run[:8]


def group_rows(study: Path, runs, arm: str):
    """One arm's rows of several runs, frames numbered on through the night."""
    out, offset = [], 0
    for run in runs:
        rows, _ = arm_rows(study, run, arm)
        _truth, summary = truth_rows(study, run)
        out += [dict(r, frame=r["frame"] + offset, run=run) for r in rows]
        offset += summary["frames"]
    return out


def group_truth(study: Path, runs):
    out, offset = {}, 0
    for run in runs:
        truth, summary = truth_rows(study, run)
        out.update({(f + offset, k): dict(r, frame=f + offset) for (f, k), r in truth.items()})
        offset += summary["frames"]
    return out


def truth_rows(study: Path, run: str):
    rows, summary = load(study / "runs" / f"{run}_seq.jsonl")
    return {(r["frame"], r["key"]): r for r in rows if r["arm"] == "truth"}, summary


def stats(rows, truth, role):
    sel = [r for r in rows if r["role"] == role]
    frames = sorted({r["frame"] for r in sel})
    kept = [r for r in sel if r["state"] == "kept" and r.get("mag") is not None]
    flagged = [r for r in sel if r["state"] == "flagged"]
    errs = [e for e in (err(r) for r in sel) if e is not None]
    kept_errs = [e for e in (err(r) for r in kept) if e is not None]
    dmag, dinst = [], []
    for r in kept:
        t = truth.get((r["frame"], r["key"]))
        if t is None:
            continue
        if t.get("mag") is not None:
            dmag.append(1000.0 * (r["mag"] - t["mag"]))
        if r.get("inst_mag") is not None and t.get("inst_mag") is not None:
            dinst.append(1000.0 * (r["inst_mag"] - t["inst_mag"]))
    mags = [r["mag"] for r in kept]
    ferr = [r["formal_err"] for r in kept if r.get("formal_err") is not None]

    def rnd(x, n=2):
        return None if x is None else round(x, n)

    return {
        "frames": len(frames),
        "kept": len(kept),
        "flagged": len(flagged),
        "lost": len(frames) - len(kept) - len(flagged),
        "err_median": rnd(pct(errs, 0.5)),
        "err_p95": rnd(pct(errs, 0.95)),
        "err_max": rnd(max(errs) if errs else None),
        "off_star_kept": sum(1 for e in kept_errs if e > OFF_STAR_PX),
        "kept_err_max": rnd(max(kept_errs) if kept_errs else None),
        "n_dmag": len(dmag),
        "dmag_median_mmag": rnd(pct(dmag, 0.5), 1),
        "dmag_rms_mmag": rnd(math.sqrt(sum(d * d for d in dmag) / len(dmag)) if dmag else None, 1),
        "dmag_absmax_mmag": rnd(max(abs(d) for d in dmag) if dmag else None, 1),
        "dinst_median_mmag": rnd(pct(dinst, 0.5), 1),
        "dinst_rms_mmag": rnd(
            math.sqrt(sum(d * d for d in dinst) / len(dinst)) if dinst else None, 1
        ),
        "dinst_absmax_mmag": rnd(max(abs(d) for d in dinst) if dinst else None, 1),
        "mag_std_mmag": rnd(1000.0 * statistics.stdev(mags) if len(mags) > 1 else None, 1),
        "formal_err_median_mmag": rnd(1000.0 * pct(ferr, 0.5) if ferr else None, 1),
    }


def truth_stats(truth, role):
    rows = [r for r in truth.values() if r["role"] == role and r.get("mag") is not None]
    mags = [r["mag"] for r in rows]
    ferr = [r["formal_err"] for r in rows if r.get("formal_err") is not None]
    return {
        "kept": len(rows),
        "mag_std_mmag": round(1000.0 * statistics.stdev(mags), 1) if len(mags) > 1 else None,
        "formal_err_median_mmag": round(1000.0 * pct(ferr, 0.5), 1) if ferr else None,
    }


def solve_check(study: Path, run: str, target):
    """Truth consensus; Argos's live-settings solves against the truth and the run's scale.

    ``wrong``: an Argos solve 5 px or more from the truth at a corner or the centre
    of the frame, or (frames without a truth) a plate scale more than 1 % from the
    run's median. ``target_px``: the two solutions' disagreement at the target, on
    the other frames: the solver-to-solver noise, a bound on the truth's accuracy.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from common import load_solutions

    rows = [json.loads(x) for x in (study / "solves" / f"{run}.jsonl").read_text().splitlines()]
    truth = load_solutions(study / "solves" / f"{run}.jsonl")
    argos_path = study / "solves" / f"{run}_argos.jsonl"
    argos = load_solutions(argos_path) if argos_path.exists() else {}

    def scale(wcs):
        a, b, c, d = wcs.cd
        return 3600.0 * math.sqrt(abs(a * d - b * c))

    scales = sorted(scale(w) for w in argos.values())
    median_scale = pct(scales, 0.5)
    wrong, target_px = {}, []
    for frame, wcs in argos.items():
        ref = truth.get(frame)
        if ref is None:
            off = abs(scale(wcs) / median_scale - 1.0)
            if off > 0.01:
                wrong[frame] = f"scale {scale(wcs):.3f} vs {median_scale:.3f}"
            continue
        h, w = 2.0 * ref.crpix2 - 1.0, 2.0 * ref.crpix1 - 1.0  # crpix is the 1-based centre
        d = 0.0
        for x, y in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1), (w / 2, h / 2)):
            ra, dec = ref.pixel_to_world_deg(x, y)
            px, py = wcs.world_to_pixel_deg(ra, dec)
            d = max(d, math.hypot(float(px) - x, float(py) - y))
        if d >= 5.0:
            wrong[frame] = f"{d:.1f} px, scale {scale(wcs):.3f}"
            continue
        tx, ty = ref.world_to_pixel_deg(target.ra_deg, target.dec_deg)
        ax, ay = wcs.world_to_pixel_deg(target.ra_deg, target.dec_deg)
        target_px.append(math.hypot(float(ax) - float(tx), float(ay) - float(ty)))
    return {
        "frames": len(rows),
        "truth_frames": len(truth),
        "no_consensus": [r["frame"] for r in rows if r.get("consensus") is False],
        "argos_solved": len(argos),
        "argos_scale_arcsec": (
            [round(scales[0], 3), round(median_scale, 3), round(scales[-1], 3)] if scales else None
        ),
        "argos_wrong": wrong,
        "argos_vs_truth_target_px_median": round(pct(target_px, 0.5), 2) if target_px else None,
        "argos_vs_truth_target_px_p95": round(pct(target_px, 0.95), 2) if target_px else None,
        "truth_solve_s_median": round(pct([r["solve_s"] for r in rows], 0.5), 2),
    }


# --------------------------------------------------------------------------- SVG


def svg_chart(
    path: Path,
    title: str,
    xlabel: str,
    ylabel: str,
    series,
    *,
    logy=False,
    ylim=None,
    width=760,
    height=300,
    hline=None,
):
    """A static scatter/line chart. ``series``: [{label, color, points: [(x, y, filled)]}]."""
    left, right, bottom = 64, 16, 44
    # Legend rows first: the plot starts below them.
    legend, lx, row = [], left, 0
    for s in series:
        item_w = 13 + 6.2 * len(s["label"]) + 18
        if lx + item_w > width - right and lx > left:
            lx, row = left, row + 1
        legend.append((lx, 30 + 16 * row, s))
        lx += item_w
    top = 40 + 16 * row
    pw, ph = width - left - right, height - top - bottom
    xs = [p[0] for s in series for p in s["points"]]
    ys = [p[1] for s in series for p in s["points"] if p[1] is not None]
    if not xs or not ys:
        return
    x0, x1 = min(xs), max(xs)
    if x1 == x0:
        x1 = x0 + 1
    if ylim is not None:
        y0, y1 = ylim
    else:
        y0, y1 = min(ys), max(ys)
        pad = 0.05 * (y1 - y0 or 1.0)
        y0, y1 = y0 - pad, y1 + pad
    tf = (lambda v: math.log10(max(v, 1e-3))) if logy else (lambda v: v)
    ty0, ty1 = tf(y0), tf(y1)

    def X(v):
        return left + (v - x0) / (x1 - x0) * pw

    def Y(v):
        t = min(max(tf(v), ty0), ty1)
        return top + ph - (t - ty0) / (ty1 - ty0) * ph

    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="Helvetica, Arial, sans-serif" '
        f'font-size="11">',
        f'<rect width="{width}" height="{height}" fill="#fcfcfb"/>',
        f'<text x="{left}" y="18" font-size="13" fill="#0b0b0b">{_esc(title)}</text>',
    ]
    if logy:
        ticks = [10.0**k for k in range(math.floor(ty0), math.ceil(ty1) + 1)]
        ticks = [t for t in ticks if y0 <= t <= y1]
    else:
        ticks = _nice_ticks(y0, y1)
    for t in ticks:
        out.append(
            f'<line x1="{left}" x2="{left + pw}" y1="{Y(t):.1f}" y2="{Y(t):.1f}" '
            f'stroke="#e4e3df" stroke-width="1"/>'
        )
        out.append(
            f'<text x="{left - 6}" y="{Y(t) + 4:.1f}" text-anchor="end" '
            f'fill="#52514e">{_fmt(t)}</text>'
        )
    if hline is not None:
        out.append(
            f'<line x1="{left}" x2="{left + pw}" y1="{Y(hline):.1f}" y2="{Y(hline):.1f}" '
            f'stroke="#52514e" stroke-width="1" stroke-dasharray="4 3"/>'
        )
    for t in _nice_ticks(x0, x1):
        out.append(
            f'<text x="{X(t):.1f}" y="{top + ph + 16}" text-anchor="middle" '
            f'fill="#52514e">{_fmt(t)}</text>'
        )
    out.append(
        f'<line x1="{left}" x2="{left + pw}" y1="{top + ph}" y2="{top + ph}" '
        f'stroke="#9a9993" stroke-width="1"/>'
    )
    out.append(
        f'<text x="{left + pw / 2:.1f}" y="{height - 8}" text-anchor="middle" '
        f'fill="#52514e">{_esc(xlabel)}</text>'
    )
    out.append(
        f'<text transform="translate(14 {top + ph / 2:.1f}) rotate(-90)" '
        f'text-anchor="middle" fill="#52514e">{_esc(ylabel)}</text>'
    )
    for s in series:
        pts = sorted(s["points"], key=lambda p: p[0])
        if s.get("line"):
            d = " ".join(
                f"{'M' if i == 0 else 'L'}{X(p[0]):.1f},{Y(p[1]):.1f}" for i, p in enumerate(pts)
            )
            out.append(f'<path d="{d}" fill="none" stroke="{s["color"]}" stroke-width="2"/>')
        for x, y, filled in pts:
            if y is None:
                continue
            fill = s["color"] if filled else "#fcfcfb"
            out.append(
                f'<circle cx="{X(x):.1f}" cy="{Y(y):.1f}" r="3" fill="{fill}" '
                f'stroke="{s["color"]}" stroke-width="1.2"/>'
            )
    for lx, ly, s in legend:
        out.append(f'<circle cx="{lx + 5}" cy="{ly}" r="4" fill="{s["color"]}"/>')
        out.append(f'<text x="{lx + 13}" y="{ly + 4}" fill="#0b0b0b">{_esc(s["label"])}</text>')
    out.append("</svg>")
    path.write_text("\n".join(out) + "\n")


def _nice_ticks(a, b, n=6):
    span = b - a
    if span <= 0:
        return [a]
    raw = span / n
    mag = 10 ** math.floor(math.log10(raw))
    step = next(m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= raw)
    start = math.ceil(a / step) * step
    ticks = []
    v = start
    while v <= b + 1e-9:
        ticks.append(round(v, 10))
        v += step
    return ticks


def _fmt(v):
    if abs(v) >= 100 or float(v).is_integer():
        return f"{v:.0f}"
    return f"{v:g}"


def _esc(text):
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# --------------------------------------------------------------------------- main


def main(argv):
    data, study, notes = Path(argv[0]), Path(argv[1]), Path(argv[2])
    runs = sorted(p.name[: -len("_seq.jsonl")] for p in (study / "runs").glob("*_seq.jsonl"))
    results = {"definitions": __doc__.split("Definitions")[1].strip(), "runs": {}}
    for run in runs:
        truth, summary = truth_rows(study, run)
        entry = {
            "frames": summary["frames"],
            "check": summary["check"],
            "aperture_px": round(summary["aperture_px"], 2),
            "search_r_px": summary["search_r_px"],
            "truth": {role: truth_stats(truth, role) for role in ("target", "check")},
            "solves": solve_check(study, run, target_star(data, run)),
            "arms": {},
        }
        for arm in ARMS:
            rows, asum = arm_rows(study, run, arm)
            entry["arms"][arm] = {role: stats(rows, truth, role) for role in ("target", "check")}
            if arm.startswith("batch"):
                entry["arms"][arm]["summary"] = {
                    k: asum.get(k)
                    for k in ("rotation_deg", "shift_px", "frames_resolved", "frames_unanchored")
                }
            all_errs = [e for e in (err(r) for r in rows) if e is not None]
            entry["arms"][arm]["all_stars_err_median"] = round(pct(all_errs, 0.5), 2)
            comp_errs = [
                e for e in (err(r) for r in rows if r["role"] == "comparison") if e is not None
            ]
            entry["arms"][arm]["comparisons_err_median"] = (
                round(pct(comp_errs, 0.5), 2) if comp_errs else None
            )
        results["runs"][run] = entry
    nights: dict[str, list[str]] = {}
    for run in runs:
        nights.setdefault(night_of(run), []).append(run)
    results["nights"] = {}
    for name, group in nights.items():
        truth = group_truth(study, group)
        night = {
            "runs": group,
            "frames": sum(results["runs"][r]["frames"] for r in group),
            "truth": {role: truth_stats(truth, role) for role in ("target", "check")},
            "arms": {},
        }
        for arm in ARMS:
            rows = group_rows(study, group, arm)
            night["arms"][arm] = {role: stats(rows, truth, role) for role in ("target", "check")}
            all_errs = [e for e in (err(r) for r in rows) if e is not None]
            night["arms"][arm]["all_stars_err_median"] = round(pct(all_errs, 0.5), 2)
        results["nights"][name] = night
        figures(study, notes, name, group)
    (notes / "results.json").write_text(json.dumps(results, indent=1) + "\n")
    (notes / "tables.md").write_text(tables(results))
    print(f"{len(runs)} runs -> {notes}")


def figures(study, notes, short, runs):
    truth = group_truth(study, runs)
    for mode, arms in (
        ("seq", ("seq_qt", "seq_web")),
        ("single", ("solo_qt", "solo_web")),
        ("batch", ("batch_before", "batch_s43")),
    ):
        series_err, series_dmag = [], []
        for arm in arms:
            rows = group_rows(study, runs, arm)
            label, _suffix, inner = ARMS[arm]
            color = COLORS[inner or arm]
            tgt = [r for r in rows if r["role"] == "target"]
            series_err.append(
                {
                    "label": label,
                    "color": color,
                    "points": [
                        (r["frame"], max(err(r), 0.01), r["state"] == "kept")
                        for r in tgt
                        if err(r) is not None
                    ],
                }
            )
            pts = []
            for r in tgt:
                t = truth.get((r["frame"], r["key"]))
                if r["state"] == "kept" and r.get("mag") is not None and t and t.get("mag"):
                    pts.append((r["frame"], 1000.0 * (r["mag"] - t["mag"]), True))
            series_dmag.append({"label": label, "color": color, "points": pts})
        svg_chart(
            notes / f"{short}_{mode}_placement.svg",
            f"{short}: target aperture vs its own-solve position (hollow = no point kept)",
            "frame (the night's runs in order)",
            "placement error (green px, log)",
            series_err,
            logy=True,
            ylim=(0.03, 1000.0),
            hline=OFF_STAR_PX,
        )
        svg_chart(
            notes / f"{short}_{mode}_dmag.svg",
            f"{short}: target magnitude minus the own-solve magnitude (kept points)",
            "frame (the night's runs in order)",
            "difference (mmag)",
            series_dmag,
            hline=0.0,
        )


def _arm_table(arms):
    lines = [
        "| arm | kept / flagged / lost | target placement px median / p95 / max | "
        "off-star kept points | dmag vs truth mmag median / rms / max | dinst mmag rms / max "
        "| check dmag rms mmag | all stars px median |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for arm, a in arms.items():
        s, c = a["target"], a["check"]
        lines.append(
            f"| {ARMS[arm][0]} | {s['kept']} / {s['flagged']} / {s['lost']} | "
            f"{s['err_median']} / {s['err_p95']} / {s['err_max']} | {s['off_star_kept']} | "
            f"{s['dmag_median_mmag']} / {s['dmag_rms_mmag']} / {s['dmag_absmax_mmag']} | "
            f"{s['dinst_rms_mmag']} / {s['dinst_absmax_mmag']} | {c['dmag_rms_mmag']} | "
            f"{a['all_stars_err_median']} |"
        )
    return lines


def tables(results):
    lines = ["<!-- generated by scripts/analyze.py; do not edit by hand -->", ""]
    lines += ["## Per night", ""]
    for name, night in results["nights"].items():
        t = night["truth"]["target"]
        lines += [
            f"### {name}",
            "",
            f"{len(night['runs'])} run(s), {night['frames']} frames. Truth: target scatter "
            f"{t['mag_std_mmag']} mmag, median formal error {t['formal_err_median_mmag']} mmag.",
            "",
        ]
        lines += _arm_table(night["arms"]) + [""]
    lines += ["## Per run", ""]
    for run, entry in results["runs"].items():
        t = entry["truth"]["target"]
        sc = entry["solves"]
        lines += [
            f"### {run}",
            "",
            f"Solves: truth on {sc['truth_frames']} of {sc['frames']} frames (no consensus: "
            f"{sc['no_consensus'] or 'none'}). Argos live settings: {sc['argos_solved']} solved, "
            f"scale min / median / max {sc['argos_scale_arcsec']} arcsec per green px, wrong: "
            f"{sc['argos_wrong'] or 'none'}; elsewhere {sc['argos_vs_truth_target_px_median']} px "
            f"median ({sc['argos_vs_truth_target_px_p95']} p95) from the truth at the target.",
            "",
            f"{entry['frames']} frames; aperture {entry['aperture_px']} px, tracker search "
            f"radius {entry['search_r_px']} px; check star {entry['check']}. Truth (own solve "
            f"per frame): target scatter {t['mag_std_mmag']} mmag, median formal error "
            f"{t['formal_err_median_mmag']} mmag.",
            "",
        ]
        lines += _arm_table(entry["arms"])
        lines.append("")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
