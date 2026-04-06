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

# PyQt6 platform plugin path — Qt does not auto-discover this in uv venvs on macOS.
# Without this, QApplication crashes with "Could not find the Qt platform plugin cocoa".
SITE_PKGS=".venv/lib/python3.11/site-packages"
export QT_QPA_PLATFORM_PLUGIN_PATH="$(pwd)/${SITE_PKGS}/PyQt6/Qt6/plugins/platforms"

exec /opt/homebrew/bin/uv run python main.py "$@"
