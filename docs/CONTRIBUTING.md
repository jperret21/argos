# Contributing to Argos

Thanks for your interest. This project is in **early development** —
expect rough edges and frequent changes.

---

## Getting Started

```bash
# Prerequisites: macOS, Python 3.11+, Homebrew

brew install uv
git clone https://github.com/jperret21/seerstar.git
cd seerstar
uv sync --extra dev
```

---

## Development Workflow

### Branches

```
main        -- stable, tagged
develop     -- integration branch (base your work here)
feat/<name> -- new features
fix/<name>  -- bug fixes
docs/<name> -- documentation
```

### Commits

Conventional Commits format:

```
<type>(<scope>): <description>

Types: feat | fix | docs | refactor | test | chore
Scope: alpaca | camera | mount | ui | sequencer | fits | config
```

Examples:
```
feat(alpaca): add camera temperature readout
fix(camera): handle connection timeout on startup
docs(readme): simplify project status section
```

### Run the app

```bash
./run.sh
```

### Run tests

```bash
uv run --extra dev pytest -q          # whole suite
uv run --extra dev pytest tests/ -v   # verbose
```

> **Always run tests through `uv`.** This project is `uv`-managed and the
> `.venv` it creates has the correct, mutually-compatible pinned deps. Do **not**
> run `pytest` from a system or Anaconda Python: those often ship **numpy 2.x**
> against an **`erfa`/`astropy` built for numpy 1.x**, which raises a wall of
> `numpy.dtype size changed` / binary-incompatibility errors at import time. Those
> failures are an environment artefact, **not** a bug in the code — if you see ~16
> astropy/erfa import errors, you are using the wrong interpreter. Re-run with
> `uv run --extra dev pytest` before concluding anything about a change.
>
> A correct run on this repo is **all green except simulator-gated tests**, which
> auto-skip when the ASCOM Alpaca simulator is not running (see below).

### Format and lint

```bash
uv run black argos/ tests/
uv run ruff check argos/ tests/
```

---

## Code Standards

- **Python 3.11+** required
- **Type hints** on all public signatures
- **Google-style docstrings** on public classes and methods
- **Line length**: 100 characters max
- Formatter: **black** (non-negotiable). Linter: **ruff**
- No `print()` — use `logging.getLogger(__name__)` with appropriate level

---

## Testing Without Hardware

Use the [ASCOM Alpaca Simulator](https://github.com/ASCOMInitiative/ASCOM.Alpaca.Simulators/releases)
(macOS compatible). It runs on `localhost:32323` and simulates telescope, camera,
focuser, and filter wheel with realistic data.

Tests detect the simulator automatically and skip if it is not running.

---

## Questions?

Open an issue on GitHub.
