# Contributing to ARGOS

The full contributing guide lives in the documentation sources:
**[`docsrc/CONTRIBUTING.md`](docsrc/CONTRIBUTING.md)**: setup, branch and
commit conventions, the test commands of the server, the web interface and
the desktop shell, and the documentation rules.

This file exists so GitHub finds a contributing guide from issues and pull
requests; it only looks in the repository root, `.github/`, and `docs/`, and
`docs/` is the published website rather than the documentation sources.

Quick start:

```sh
uv sync --extra dev --extra qt --extra server --extra docs
(cd web && npm install)
.venv/bin/python run_web.py --sim     # the web UI on the simulator, a separate dev config

# The suite runs in two processes; a single process can abort on the
# simulator fixtures. This is what CI does.
export QT_QPA_PLATFORM=offscreen
uv run --extra dev --extra qt --extra server pytest -q --deselect tests/ui/test_photometry_window.py
uv run --extra dev --extra qt --extra server pytest -q tests/ui/test_photometry_window.py
```
