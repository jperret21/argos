"""How the web tracker held a jump frame: its own windows, or the star-pattern vote.

    PYTHONPATH=<release tree> python probe_reacquire.py <frames dir> <targets.json>
        <solves.jsonl> <field_track.py> <frame> [<frame> ...]

For each jump frame F, the tracker is built as replay.py builds it on frame F-1
with F-1's own solution (the sequence case), then updated on F: the anchors its
windows matched before any re-acquisition, and whether ``vote_transform`` then
found the field.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from astropy.io import fits

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import load_module, load_solutions, load_target_set  # noqa: E402
from replay import STAR_RADIUS, WebArm  # noqa: E402

from argos.core.imaging.green import green_plane  # noqa: E402
from argos.core.imaging.metrics import detect_stars  # noqa: E402
from argos.core.photometry.params import PhotometryParams  # noqa: E402
from argos.workers.photometry_batch_worker import discover_light_frames  # noqa: E402


def main(argv):
    frames, targets, solves, track = map(Path, argv[:4])
    ft = load_module(track, "web_field_track")
    solutions = load_solutions(solves)
    paths = discover_light_frames(frames)
    tset, _check = load_target_set(targets)
    params = PhotometryParams.from_config(lambda _key, default: default)
    for f in map(int, argv[4:]):
        prev = np.asarray(fits.getdata(paths[f - 1]))
        cur = np.asarray(fits.getdata(paths[f]))
        arm = WebArm(ft, tset, params)
        arm.solved(solutions[f - 1], prev)
        arm.tracker = arm._build(green_plane(prev), green_plane(cur).shape)
        own = arm.tracker.update(green_plane(cur), allow_rotation=True)
        stars = detect_stars(cur, radius=STAR_RADIUS)
        current = [(float(s.x), float(s.y), float(s.flux)) for s in stars.stars]
        vote = ft.vote_transform(arm.ref_stars, current, arm.tracker.transform)
        print(
            f"frame {f}: windows matched {own} of {arm.tracker.size} anchors; "
            f"vote {'found ' + str(vote[1]) + ' stars' if vote else 'none'}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
