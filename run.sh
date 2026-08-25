#!/usr/bin/env bash
# SeerControl launcher
set -e
cd "$(dirname "$0")"

# Unset conda/virtualenv environment variables so uv does not mistake the
# conda base environment for our project venv and destroy it on every run.
unset VIRTUAL_ENV
unset CONDA_PREFIX
unset CONDA_DEFAULT_ENV

# Locate uv. Prefer PATH, then fall back to known install locations — uv may live
# in ~/.local/bin (standalone installer) or under Homebrew depending on the machine.
UV="$(command -v uv || true)"
for candidate in "$HOME/.local/bin/uv" /opt/homebrew/bin/uv /usr/local/bin/uv; do
    [ -n "$UV" ] && break
    [ -x "$candidate" ] && UV="$candidate"
done
if [ -z "$UV" ]; then
    echo "error: uv not found. Install it with 'brew install uv' or see https://docs.astral.sh/uv/" >&2
    exit 1
fi

# Sync production dependencies only (dev extras like pytest/simulator not needed to run).
"$UV" sync --quiet

# Prepare the venv for Qt — once per environment build, not once per launch.
#
# Two macOS problems need fixing: freshly-downloaded dylibs carry a quarantine
# flag that SIP refuses to load, and the wheel sometimes ends up with duplicate
# framework dirs (" 2" / " 3" suffixes) that confuse the dynamic linker.
#
# Both fixes are idempotent, but the recursive xattr sweep walks ~6700 files and
# costs ~26 s — it was the single largest chunk of Argos' startup time, and on a
# healthy venv it clears exactly zero flags. The stamp below is invalidated by
# anything that could have rebuilt the environment, so a fresh sync still gets
# swept.
STAMP=".venv/.argos-venv-prepared"
PYQT_DIR=".venv/lib/python3.11/site-packages/PyQt6"
if [ ! -f "$STAMP" ] \
   || [ "uv.lock" -nt "$STAMP" ] \
   || [ "pyproject.toml" -nt "$STAMP" ] \
   || [ "$PYQT_DIR" -nt "$STAMP" ]; then
    find "$PYQT_DIR" -type d \( -name "* 2" -o -name "* 3" \) \
        -exec rm -rf {} + 2>/dev/null || true
    find "$PYQT_DIR" \( -name "* 2.*" -o -name "* 3.*" \) \
        -type f -delete 2>/dev/null || true
    # Only stamp a sweep that actually succeeded — otherwise a transient
    # failure would silently disable it forever.
    if xattr -dr com.apple.quarantine .venv/ 2>/dev/null; then
        touch "$STAMP"
    fi
fi

exec "$UV" run python main.py "$@"
