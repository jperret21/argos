# Notes for AI agents working on Argos

Read this before you change code or run tests. It captures the few things that
trip agents up here.

## Running the test suite — use `uv`, nothing else

```bash
uv run --extra dev pytest -q
```

This repo is **`uv`-managed**. The `.venv` that `uv sync --extra dev` builds has
the correct, mutually-compatible pinned dependencies. Run tests through `uv` and
only through `uv`.

**Do NOT run `pytest` from a system / Anaconda / pyenv Python.** Those commonly
have **numpy 2.x** installed against an **`erfa` / `astropy` compiled for
numpy 1.x**. That mismatch raises a cascade of import-time errors
(`ValueError: numpy.dtype size changed`, binary-incompatibility, etc.) in every
test that touches `astropy` — roughly **16 failures** here. **Those are an
environment artefact, not a code bug.** If you see them, you are using the wrong
interpreter; re-run with `uv run --extra dev pytest` before drawing any
conclusion about your change.

A correct run is **all green except simulator-gated tests**, which auto-skip when
the ASCOM Alpaca simulator is not running (≈19 skipped is normal).

## When you refactor, update the tests in the same change

UI smoke coverage lives in a **single** function, `tests/ui/test_shell.py::
test_shell_three_mode_walkthrough` (PyQt6 SIGABRTs when many widget-creating
tests tear down separately, so everything widget-touching is in one test). It
pokes private attributes/methods of the windows directly. If you rename or move a
method/attribute/button (e.g. moving catalog/target logic out of
`AnalysisWindow` into `PhotometrySetupWindow`), **update that test in the same
commit** — otherwise the suite breaks on the removed API even though the app is
fine.

## Conventions

- No emoji in UI or code; use Feather SVG icons.
- `black` (line length 100) + `ruff`: `uv run black argos/ tests/` /
  `uv run ruff check argos/ tests/`.
- See `docs/CONTRIBUTING.md` for the full workflow and `docs/ARCHITECTURE.md`
  for layout.
