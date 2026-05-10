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

# Qt plugin path is auto-detected in main.py via sysconfig — no hardcoded path needed.
exec /opt/homebrew/bin/uv run python main.py "$@"
