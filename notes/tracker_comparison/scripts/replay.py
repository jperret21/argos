"""Replay a run's saved frames through the live trackers and the per-frame truth.

Arms, all measured by core's ``measure_frame`` with one aperture for the whole
run (the batch's series FWHM, measured on the first frame) and each frame's own
e-/ADU (its EGAIN), so that only the aperture placement differs:

``qt``     Qt's live sequence path, run as code: a real ``AcquisitionEngine``
           (offscreen, no devices) fed each frame through
           ``_on_seq_frame_image`` and ``_on_seq_frame_saved``
           (acquisition_engine.py:837), i.e. ``ApertureTracker`` + S35.
``web``    the web tracker ``FieldTracker`` (argos/server/field_track.py),
           driven as ``FieldService._track`` / ``_build_tracker`` /
           ``_reacquire`` drive it (argos/server/field.py:1471-1605), the point
           skipped when its health is ``lost`` (the S35 rule).
``truth``  no tracker: each frame measured through its own ASTAP solution, every
           star moved to the frame's date by its proper motion when
           ``proper_motions.json`` gives one (the live arms, like both apps,
           place apertures at the J2000.0 catalogue position).

Solve schedule (both live arms): the run starts with frame ``--first``'s own
solution (the solve made before Start). With ``--resolve-s S > 0`` the
auto-solve re-solves a frame when S seconds have passed since the last solve
started (astrometry_controller.py ``_due``, ``live_resolve_s``); the solution
lands before the next frame is measured (a solve takes 0.2-0.3 s, the cadence
is 50-85 s) and resets the tracker (``_on_reference_solved``). ``--resolve-s 0``
never re-solves: the tracker alone carries the run (a run whose solves fail).
The mount-motion trigger (2 arcmin) is not replayed: the frames carry no mount
position.

Output: one JSON line per (arm, frame, star): the aperture centre, the truth
centre, whether a point was written, its magnitude and formal error, and the
tracker state.

    PYTHONPATH=<release tree> QT_QPA_PLATFORM=offscreen python replay.py
        <frames dir> <targets.json> <solves.jsonl> <field_track.py> <out.jsonl>
        [--resolve-s 20] [--check nearest|none|AUID] [--first N] [--count M]
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import math
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from astropy.io import fits

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (  # noqa: E402
    load_module,
    load_solutions,
    load_target_set,
    set_at_epoch,
    star_key,
    truth_xy,
)

from argos.core.catalog.targets import ROLE_CHECK, ROLE_COMPARISON  # noqa: E402
from argos.core.imaging.green import green_plane  # noqa: E402
from argos.core.imaging.metrics import detect_stars  # noqa: E402
from argos.core.photometry.params import PhotometryParams, frame_egain, measure_frame  # noqa: E402
from argos.core.photometry.tracking import TrackedWCS, select_tracking_anchors  # noqa: E402
from argos.workers.photometry_batch_worker import discover_light_frames  # noqa: E402

# argos/server/field.py constants (MAX_DETECTED_SOURCES, REACQUIRE_REFERENCE_STARS,
# MAX_DETECTED_ANCHORS) and the default star radius (hub.py _star_radius).
MAX_DETECTED_SOURCES = 2000
REACQUIRE_REFERENCE_STARS = 300
MAX_DETECTED_ANCHORS = 6
STAR_RADIUS = 5


class WebArm:
    """``FieldService`` tracking, reduced to what places the apertures."""

    def __init__(self, field_track, tset, params) -> None:
        self.ft = field_track
        self.tset = tset
        self.params = params
        self.wcs = None
        self.tracker = None
        self.ref_raw = None
        self.anchors_detected = []
        self.ref_stars = []
        self.on_ref_frame = False

    def solved(self, wcs, raw) -> None:
        """field.py:878-993: a solution lands for the frame ``raw``."""
        stars = detect_stars(raw, max_stars=MAX_DETECTED_SOURCES, radius=STAR_RADIUS)
        self.anchors_detected = [
            (float(s.x), float(s.y), float(s.flux)) for s in stars.stars if s.eccentricity < 0.6
        ]
        ref = [(float(s.x), float(s.y), float(s.flux)) for s in stars.stars]
        self.ref_stars = sorted(ref, key=lambda s: -s[2])[:REACQUIRE_REFERENCE_STARS]
        self.wcs, self.ref_raw, self.tracker = wcs, raw, None

    def track(self, raw):
        """field.py:1471-1530 (``_track``) then ``_reacquire`` (1532-1546)."""
        if raw is self.ref_raw:
            return self.wcs  # the solved frame itself is not tracked (field.py:1477)
        green = green_plane(raw)
        if self.tracker is None:  # a new solution drops the tracker and its pose (984)
            self.tracker = self._build(green_plane(self.ref_raw), green.shape)
            if self.tracker is None:
                return None
        self.tracker.reacquired = False
        self.tracker.update(green, allow_rotation=True)
        if self.tracker.anchors_used == 0 and self.ref_stars:
            stars = detect_stars(raw, radius=STAR_RADIUS)
            current = [(float(s.x), float(s.y), float(s.flux)) for s in stars.stars]
            found = self.ft.vote_transform(
                self.ref_stars, current, self.tracker.transform, allow_rotation=True
            )
            if found is not None:
                previous = self.tracker.transform
                self.tracker.transform = found[0]
                if self.tracker.update(green, allow_rotation=True):
                    self.tracker.reacquired = True
                else:
                    self.tracker.transform = previous
        return TrackedWCS(self.wcs, self.tracker)

    def _build(self, ref_green, gs):
        """field.py:1554-1605 (``_build_tracker`` and ``_detected_anchor_xy``)."""
        tset, params, wcs = self.tset, self.params, self.wcs
        h, w = gs
        search_r = max(8.0, 2.0 * params.aperture_px(None))
        margin = search_r + 2.0
        candidates = tset.by_role(ROLE_COMPARISON) + tset.by_role(ROLE_CHECK)
        anchors = select_tracking_anchors(ref_green, wcs, candidates, params) if candidates else []
        xy = []
        for star in anchors:
            x, y = wcs.world_to_pixel_deg(star.ra_deg, star.dec_deg)
            if margin <= float(x) < w - margin and margin <= float(y) < h - margin:
                xy.append((float(x), float(y)))
        if len(xy) < 2:
            chosen = self._detected_xy(ref_green, margin)
            if len(chosen) >= 2 or not xy:
                xy = chosen
        if not xy:
            for star in tset.stars:
                x, y = wcs.world_to_pixel_deg(star.ra_deg, star.dec_deg)
                if margin <= float(x) < w - margin and margin <= float(y) < h - margin:
                    xy.append((float(x), float(y)))
        if not xy:
            return None
        return self.ft.FieldTracker(
            xy, frame_center=(w / 2.0, h / 2.0), search_r=search_r, reference_green=ref_green
        )

    def _detected_xy(self, ref_green, margin):
        h, w = ref_green.shape
        usable = [
            (x, y, f)
            for x, y, f in self.anchors_detected
            if margin <= x < w - margin and margin <= y < h - margin
        ]
        usable.sort(key=lambda item: item[2], reverse=True)
        sat = float(self.params.sat_adu)
        chosen = []
        for x, y, _f in usable:
            xi, yi = int(round(x)), int(round(y))
            if float(np.max(ref_green[yi - 1 : yi + 2, xi - 1 : xi + 2])) >= sat:
                continue
            if any(math.hypot(x - ox, y - oy) < 20.0 for ox, oy in chosen):
                continue
            chosen.append((x, y))
            if len(chosen) >= MAX_DETECTED_ANCHORS:
                break
        return chosen


def make_engine(tmp: Path, tset, fwhm: float):
    from argos.core.config import _DEFAULTS, Config
    from argos.core.session.acquisition_engine import AcquisitionEngine
    from argos.core.session.device_session import DeviceSession

    cfg = Config(dict(_DEFAULTS, sessions_path=str(tmp / "sessions")))
    engine = AcquisitionEngine(cfg, DeviceSession(cfg))
    engine.target_set = lambda: tset
    engine._last_fwhm = fwhm  # the series aperture (P7), as the batch measures it
    return engine


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("frames")
    ap.add_argument("targets")
    ap.add_argument("solves")
    ap.add_argument("field_track")
    ap.add_argument("out")
    ap.add_argument("--resolve-s", type=float, default=20.0)
    ap.add_argument("--check", default="nearest")
    ap.add_argument("--first", type=int, default=0)
    ap.add_argument("--count", type=int, default=0)
    ap.add_argument(
        "--live-solves",
        default=None,
        help="solutions the auto-solve returns (solve_frames.py --mode argos); default: truth",
    )
    args = ap.parse_args(argv)

    from PyQt6.QtWidgets import QApplication

    _app = QApplication.instance() or QApplication([])  # noqa: F841 - QObjects need one

    field_track = load_module(Path(args.field_track), "web_field_track")
    solutions = load_solutions(Path(args.solves))
    live = load_solutions(Path(args.live_solves)) if args.live_solves else solutions
    paths = discover_light_frames(Path(args.frames))
    end = (args.first + args.count) if args.count else len(paths)
    indices = list(range(args.first, end))
    paths = paths[args.first : end]
    tset, check = load_target_set(Path(args.targets), args.check)
    params = PhotometryParams.from_config(lambda _key, default: default)
    tmp = Path(tempfile.mkdtemp(prefix="replay_"))
    run_root = tmp / "run"
    (run_root / "lights").mkdir(parents=True)

    import argos.core.session.acquisition_engine as ae

    captured: list = []
    real_measure = ae.measure_frame

    def capture(*a, **kw):
        out = real_measure(*a, **kw)
        captured[:] = out
        return out

    ae.measure_frame = capture
    raw0 = np.asarray(fits.getdata(paths[0]))
    fwhm = detect_stars(np.nan_to_num(raw0.astype(np.float32))).mean_fwhm
    engine = make_engine(tmp, tset, fwhm)
    egain_now = {"value": params.egain}
    engine._egain = lambda: egain_now["value"]
    web = WebArm(field_track, tset, params)

    first = solutions[indices[0]]  # the solve before Start: the first frame's truth
    engine.astrometry._wcs = first
    engine._on_reference_solved(None, None, "")
    web.solved(first, raw0)
    last_solve_t = None
    logs: list[str] = []
    engine.log_message.connect(lambda _level, msg: logs.append(msg))

    rows = []
    for index, path in zip(indices, paths):
        with fits.open(path) as hdul:
            raw = np.asarray(hdul[0].data)
            header = hdul[0].header
        egain = frame_egain(header, {}) or params.egain
        egain_now["value"] = egain
        fparams = dataclasses.replace(params, egain=egain)
        start = str(header["DATE-OBS"])
        t_mid = (
            datetime.fromisoformat(start.replace("Z", "")).replace(tzinfo=timezone.utc).timestamp()
            + float(header["EXPTIME"]) / 2.0
        )
        green = green_plane(raw)

        def placed(wcs, stars=None):
            return {
                star_key(s): tuple(float(v) for v in wcs.world_to_pixel_deg(s.ra_deg, s.dec_deg))
                for s in (stars if stars is not None else tset.stars)
            }

        def record(arm, positions, results, state, anchors, health=None):
            by_key = {star_key(r.star): r for r in results} if results else {}
            for s in tset.stars:
                key = star_key(s)
                truth = truth_xy(solutions, index, s)
                pos = positions.get(key) if positions else None
                r = by_key.get(key)
                has = r is not None and (
                    (r.diff is not None and r.diff.mag is not None)
                    or (r.relative is not None and r.relative.flux_ratio is not None)
                )
                mag = r.diff.mag if has and r.diff is not None and r.diff.mag is not None else None
                ferr = r.diff.mag_err if mag is not None else None
                phot = r.phot if r is not None else None
                kept = state == "kept"
                rows.append(
                    {
                        "arm": arm,
                        "frame": index,
                        "key": key,
                        "role": s.role,
                        "x": pos[0] if pos else None,
                        "y": pos[1] if pos else None,
                        "tx": truth[0] if truth else None,
                        "ty": truth[1] if truth else None,
                        "point": bool(has) and kept,
                        "mag": mag if kept else None,
                        "formal_err": ferr if kept else None,
                        "comps": r.diff.comps_used if kept and r is not None and r.diff else None,
                        "snr": phot.snr if phot is not None else None,
                        "inst_mag": phot.inst_mag if kept and phot is not None else None,
                        "inst_err": phot.inst_mag_err if kept and phot is not None else None,
                        "state": state,
                        "anchors": anchors,
                        "health": health,
                    }
                )

        # --- Qt: the real engine, fed as the SequenceWorker feeds it -------------
        before = {k: len(c.points) for k, c in engine.lightcurves.items()}
        logs.clear()
        engine._on_seq_frame_image(raw)
        engine._on_seq_frame_saved(
            str(run_root / "lights" / path.name),
            SimpleNamespace(
                timestamp=start + "Z",
                exposure_s=float(header["EXPTIME"]),
                image_type="Light Frame",  # S44: the engine measures Light subs only
            ),
        )
        tracked = engine.tracked_wcs()
        skipped = any("field moved" in m for m in logs)
        qt_positions = placed(tracked) if tracked is not None else None
        # The engine's own measurement of this frame (captured, unchanged); its
        # points are checked against the curves it appended to.
        qt_results = [] if skipped else list(captured)
        captured.clear()
        appended = {k for k, c in engine.lightcurves.items() if len(c.points) > before.get(k, 0)}
        for res in qt_results:
            p_mag = res.diff.mag if res.diff is not None else None
            if p_mag is not None and star_key(res.star) not in appended:
                raise SystemExit(f"frame {index}: engine result without a point")
        tracker = engine._tracker
        record(
            "qt",
            qt_positions,
            qt_results,
            "lost" if skipped else "kept",
            tracker.anchors_used if tracker is not None else None,
        )

        # --- web: FieldTracker under the same solutions ------------------------
        web_wcs = web.track(raw)
        if web_wcs is None:
            record("web", None, None, "lost", None, "lost")
        else:
            health = web.tracker.health if web.tracker is not None else "ok"
            results = []
            if health != "lost":
                results = measure_frame(green, web_wcs, tset, fparams, fwhm=fwhm)
            record(
                "web",
                placed(web_wcs),
                results,
                "lost" if health == "lost" else "kept",
                web.tracker.anchors_used if web.tracker is not None else None,
                health,
            )

        # --- truth: the frame's own solution, the stars at the frame's date ------
        # (proper motion: RR Lyr has moved 0.8 px since J2000; the arms, like the
        # apps, place apertures at the catalogue position)
        own = solutions.get(index)
        if own is not None:
            tset_now = set_at_epoch(tset, solutions.jd.get(index))
            results = measure_frame(green, own, tset_now, fparams, fwhm=fwhm)
            record("truth", placed(own, tset_now.stars), results, "kept", None)

        # --- the auto-solve: a solution of this frame lands before the next ----
        # (a failed solve keeps the previous WCS: astrometry_controller.py:211)
        landed = live.get(index)
        if args.resolve_s > 0 and (last_solve_t is None or t_mid - last_solve_t >= args.resolve_s):
            last_solve_t = t_mid
            if landed is not None:
                engine.astrometry._wcs = landed
                engine._on_reference_solved(None, None, "")
                web.solved(landed, raw)

    with open(args.out, "w") as out:
        for row in rows:
            out.write(json.dumps(row) + "\n")
        out.write(
            json.dumps(
                {
                    "summary": True,
                    "check": check,
                    "frames": len(paths),
                    "resolve_s": args.resolve_s,
                    "fwhm": fwhm,
                    "aperture_px": params.aperture_px(fwhm),
                    "search_r_px": max(8.0, 2.0 * params.aperture_px(None)),
                }
            )
            + "\n"
        )
    print(f"{len(paths)} frames -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
