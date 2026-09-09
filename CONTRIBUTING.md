# Contributing to Argos

The full contributing guide lives in the documentation sources:
**[`docsrc/CONTRIBUTING.md`](docsrc/CONTRIBUTING.md)** — branch and commit
conventions, the test commands, and the documentation rules.

This file exists so GitHub finds a contributing guide from issues and pull
requests; it only looks in the repository root, `.github/`, and `docs/`, and
`docs/` is the published website rather than the documentation sources.

Quick start:

```sh
uv sync --extra dev
# The suite runs in two processes; a single process can abort on the
# simulator fixtures. This is what CI does.
export QT_QPA_PLATFORM=offscreen
uv run --extra dev pytest -q --deselect tests/ui/test_photometry_window.py
uv run --extra dev pytest -q tests/ui/test_photometry_window.py
```
