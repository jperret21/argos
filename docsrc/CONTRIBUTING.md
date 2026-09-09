# Contributing to ARGOS

Thanks for your interest. This project is in **early development** — expect
rough edges and frequent changes.

```{seealso}
{doc}`ARCHITECTURE` before your first change: the layer rule it describes is
what most review comments are about. {doc}`simulator_testing` lets you run the
whole application without a telescope.
```

## Getting Started

```bash
# Prerequisites: Python 3.11 and uv. macOS is the reference platform;
# Debian-family Linux is supported as a technical preview.

# macOS example:
brew install uv graphviz
# Debian/Ubuntu: apt install graphviz  (uv: see https://docs.astral.sh/uv/)

git clone https://github.com/jperret21/argos.git
cd argos
uv sync --extra dev
```

```{admonition} Why graphviz
:class: tip

The documentation build renders two architecture diagrams through
`sphinx.ext.graphviz`, which shells out to the native `dot` binary. Because the
docs build with `-W`, a missing `dot` is not a warning — it fails the build, and
the error does not obviously say "install graphviz". CI installs it for the same
reason.
```

## Development Workflow

### Branches

```
main        -- stable, tagged release line
release/*   -- release preparation and field validation
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
uv run python main.py
```

`./run.sh` is a macOS convenience launcher. Use the explicit `uv run` command
in documentation, CI reproductions and cross-platform instructions.

### Run tests

The Qt tests need a platform plugin, and the suite must be run in **two
processes** — the whole suite in one process can abort on the simulator
fixtures. This is exactly what CI does:

```bash
export QT_QPA_PLATFORM=offscreen
uv run --extra dev pytest -q --deselect tests/ui/test_photometry_window.py
uv run --extra dev pytest -q tests/ui/test_photometry_window.py
uv run --extra docs sphinx-build -W -b html docsrc /tmp/argos-docs
```

Run `tests/ui/test_photometry_window.py` on its own, second. Skipping the split
produces an abort that looks like a test failure but is a process-level crash.

```{warning}
Other places in this repository still show a **single-process** `uv run --extra
dev pytest` — the root `README.md`, the root `CONTRIBUTING.md`, and
{doc}`simulator_testing`. The two-process form above is the one CI runs and the
one to trust. If a plain `pytest` aborts on you, this is why.
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
uv run --extra dev black --check argos/ tests/ main.py
uv run --extra dev ruff check argos/ tests/ main.py
```

Use the same paths as CI. To apply Black formatting locally, omit `--check`.

### Documentation

There are **two** documentation trees, and they are built and published
differently.

| Tree | What it is | How it is built |
|---|---|---|
| `docsrc/` | These pages — the Sphinx sources | `sphinx-build`, gated by `-W` in CI |
| `docs/` | The public showcase site at `perretjules.com/argos/` | **Hand-written HTML/CSS.** Nothing generates it; there is no build step |
| `notes/` | Internal working specs and French field notes | Not published. The code cites them by `§` number |

Which to edit:

- a behaviour change an observer would notice → `docsrc/guide.md` and whichever
  reference page states the fact;
- a change to a computed quantity → {doc}`differential_photometry`, and check
  its §11 constants table;
- a new or renamed FITS keyword → {doc}`fits_headers`, which is the single
  source for the writer's output. Do not restate its content elsewhere;
- a new module → add it to the matching `docsrc/api/*.rst`, or it silently
  vanishes from the reference;
- anything about the project's positioning or downloads → `docs/*.html`, by
  hand.

Always run the docs build before pushing; `-W` means a broken cross-reference
fails CI rather than rotting quietly.

## Code Standards

- **Python 3.11 exactly** — `pyproject.toml` pins `>=3.11,<3.12`; 3.12 and later are excluded
- **Type hints** on all public signatures
- **Google-style docstrings** on public classes and methods
- **Line length**: 100 characters max
- Formatter: **black** (non-negotiable). Linter: **ruff**. Both run over
  `argos/ tests/ main.py`. `scripts/` is deliberately excluded — those are
  throwaway development utilities held to a looser standard
- No `print()` — use `logging.getLogger(__name__)` with appropriate level

## Testing Without Hardware

Use the [ASCOM Alpaca Simulator](https://github.com/ASCOMInitiative/ASCOM.Alpaca.Simulators/releases)
(macOS compatible). It runs on `localhost:32323` and simulates telescope, camera,
focuser, and filter wheel with realistic data.

Tests detect the simulator automatically and skip if it is not running.

## Questions?

Open an issue on GitHub.
