"""Level 0 — Validate that all modules import cleanly. No hardware needed.

Usage:
    .venv/bin/python scripts/validate_imports.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

MODULES = [
    "seercontrol",
    "seercontrol.core.alpaca.client",
    "seercontrol.core.alpaca.telescope",
    "seercontrol.core.alpaca.camera",
    "seercontrol.core.alpaca.discovery",
    "seercontrol.core.seestar.native_client",
    "seercontrol.core.imaging.fits_writer",
    "seercontrol.core.config",
]

ok = True
for mod in MODULES:
    try:
        __import__(mod)
        print(f"  OK  {mod}")
    except Exception as exc:
        print(f"  FAIL  {mod}  →  {exc}")
        ok = False

print()
if ok:
    print("All imports OK — no hardware needed for this check.")
else:
    print("Some imports failed. Run: uv sync --extra dev")
    sys.exit(1)
