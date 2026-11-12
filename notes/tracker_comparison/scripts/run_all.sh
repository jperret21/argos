#!/bin/sh
# Re-run the whole tracker comparison on COPIES of the owner's runs.
#
#   run_all.sh <copies dir> <out dir> <fixed tree> <before tree> <field_track.py> <astap_cli> <python> [<notes dir>]
#
# <copies dir>/<run>/lights and <copies dir>/<run>/targets.json for each run.
# Ground truth: each frame's own consensus solve, the stars moved to the frame's
# date by their proper motion (../proper_motions.json); the live arms' auto-solve gets
# what Argos's live settings return for each frame (solve_frames.py --mode argos);
# <fixed tree>: the release/0.5.0 worktree (S35, S43); <before tree>: a tree with
# the batch worker before S43 (argos/core and argos/workers otherwise identical).
set -eu
DATA=$1; OUT=$2; FIXED=$3; BEFORE=$4; WEBTRACK=$5; ASTAP=$6; PY=$7; NOTES=${8:-}
HERE=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$OUT/solves" "$OUT/runs"
export QT_QPA_PLATFORM=offscreen
for dir in "$DATA"/*/; do
  run=$(basename "$dir")
  [ -f "$dir/targets.json" ] || continue
  echo "== $run"
  [ -s "$OUT/solves/$run.jsonl" ] || PYTHONPATH=$FIXED "$PY" "$HERE/solve_frames.py" \
    "$dir/lights" "$dir/targets.json" "$OUT/solves/$run.jsonl" --astap "$ASTAP" > /dev/null
  [ -s "$OUT/solves/${run}_argos.jsonl" ] || PYTHONPATH=$FIXED "$PY" "$HERE/solve_frames.py" \
    "$dir/lights" "$dir/targets.json" "$OUT/solves/${run}_argos.jsonl" --astap "$ASTAP" \
    --mode argos > /dev/null
  PYTHONPATH=$FIXED "$PY" "$HERE/replay.py" "$dir/lights" "$dir/targets.json" \
    "$OUT/solves/$run.jsonl" "$WEBTRACK" "$OUT/runs/${run}_seq.jsonl" --resolve-s 20 \
    --live-solves "$OUT/solves/${run}_argos.jsonl"
  PYTHONPATH=$FIXED "$PY" "$HERE/replay.py" "$dir/lights" "$dir/targets.json" \
    "$OUT/solves/$run.jsonl" "$WEBTRACK" "$OUT/runs/${run}_solo.jsonl" --resolve-s 0
  PYTHONPATH=$BEFORE "$PY" "$HERE/run_batch.py" "$dir/lights" "$dir/targets.json" \
    "$OUT/solves/$run.jsonl" "$OUT/runs/${run}_batch_before.jsonl" 2> /dev/null
  PYTHONPATH=$FIXED "$PY" "$HERE/run_batch.py" "$dir/lights" "$dir/targets.json" \
    "$OUT/solves/$run.jsonl" "$OUT/runs/${run}_batch_s43.jsonl" --solver astap \
    --astap "$ASTAP" 2> /dev/null
done
# The S43 evidence: RR Lyr frames 0-79 through frame 0's solve, the owner's set.
RR=20260925T200453Z_RR_Lyr
if [ -d "$DATA/$RR" ]; then
  PYTHONPATH=$BEFORE "$PY" "$HERE/run_batch.py" "$DATA/$RR/lights" "$DATA/$RR/targets.json" \
    "$OUT/solves/$RR.jsonl" "$OUT/runs/${RR}_first80_batch_before.jsonl" --count 80 \
    --check none 2> /dev/null
  PYTHONPATH=$FIXED "$PY" "$HERE/run_batch.py" "$DATA/$RR/lights" "$DATA/$RR/targets.json" \
    "$OUT/solves/$RR.jsonl" "$OUT/runs/${RR}_first80_batch_s43.jsonl" --count 80 \
    --check none --solver astap --astap "$ASTAP" 2> /dev/null
fi
# The truth against the image (truth_check.json), then tables, results.json and
# figures (analyze.py), when a notes dir is given.
[ -z "$NOTES" ] || PYTHONPATH=$FIXED "$PY" "$HERE/truth_check.py" "$DATA" "$OUT" "$NOTES"
[ -z "$NOTES" ] || PYTHONPATH=$FIXED "$PY" "$HERE/analyze.py" "$DATA" "$OUT" "$NOTES"
