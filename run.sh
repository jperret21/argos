#!/usr/bin/env bash
# SeerControl launcher
set -e
cd "$(dirname "$0")"

# Unset conda/virtualenv environment variables so uv does not mistake the
# conda base environment for our project venv and destroy it on every run.
unset VIRTUAL_ENV
unset CONDA_PREFIX
unset CONDA_DEFAULT_ENV

# Sync production dependencies only (dev extras like pytest/simulator not needed to run).
/opt/homebrew/bin/uv sync --quiet

# macOS sometimes creates duplicate framework dirs with " 2" / " 3" suffixes inside the
# PyQt6 wheel, which confuses the dynamic linker. Remove them — safe and idempotent.
find .venv/lib/python3.11/site-packages/PyQt6 -type d \( -name "* 2" -o -name "* 3" \) \
    -exec rm -rf {} + 2>/dev/null || true
find .venv/lib/python3.11/site-packages/PyQt6 \( -name "* 2.*" -o -name "* 3.*" \) \
    -type f -delete 2>/dev/null || true

# Remove quarantine flags — safe and idempotent.
xattr -dr com.apple.quarantine .venv/ 2>/dev/null || true

exec /opt/homebrew/bin/uv run python main.py "$@"
