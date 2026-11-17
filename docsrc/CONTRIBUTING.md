# Contributing to ARGOS

ARGOS 0.5.0 is the first beta of the new ARGOS: a web interface in a desktop
app, on a headless Python server. Quick 0.5.x patch releases are expected, so
expect changes.

```{seealso}
{doc}`ARCHITECTURE` before your first change: which part owns what, and the
rules between the parts, are what most review comments are about.
{doc}`simulator_testing` runs the whole application without a telescope.
```

## Getting started

Prerequisites: Python 3.11 exactly (`pyproject.toml` pins `>=3.11,<3.12`) and
[uv](https://docs.astral.sh/uv/); Node 22 for the web interface (the version
CI uses); Graphviz for the documentation; Rust stable only to build the
desktop shell. macOS is the reference platform; Debian-family Linux is a
technical preview.

```bash
# macOS
brew install uv graphviz node@22
# Debian or Ubuntu: apt install graphviz; uv and Node from their own sites

git clone https://github.com/jperret21/argos.git
cd argos
uv sync --extra dev --extra qt --extra server --extra docs
(cd web && npm install)
```

| Extra | For |
|---|---|
| `server` | The headless server, FastAPI and uvicorn (`argos/server`) |
| `dev` | pytest, black, ruff, and httpx for the server's `TestClient` |
| `qt` | The retired PyQt6 app and its parity tests |
| `docs` | Sphinx, MyST, Furo and the extensions of this documentation |
| `package` | PyInstaller, for the desktop app's sidecar only |

```{warning}
`uv sync` is an **exact** sync: in an existing `.venv` it uninstalls every
package of an extra you did not name, so a later `uv sync --extra dev` drops
the server, Qt and the docs tools. Name every extra you use, add `--inexact`,
or run commands through `uv run --extra …`, which never removes anything.
```

```{admonition} Why Graphviz
:class: tip

The documentation renders six architecture diagrams (`docsrc/diagrams/*.dot`)
through `sphinx.ext.graphviz`, which runs the native `dot`. Because the docs
build with `-W`, a missing `dot` fails the build, and the error does not
obviously say "install Graphviz". CI and the Pages job install it for the
same reason.
```

## Development workflow

### Branches

```
main         -- the released line; the website is deployed from it
release/*    -- release preparation; the fixes of a release are made here
feat/<name>  -- new features
fix/<name>   -- bug fixes
docs/<name>  -- documentation
```

A fix to `argos/core` or to the retired Qt app that changes a result gets the
next S number in the release notes (`notes/release_0_5_0.md`) and a
regression test that fails on the code before the fix. A change to the
server's API starts in its contract, `argos/server/protocol.md`, and API 2
only grows.

### Commits

Conventional Commits:

```
<type>(<scope>): <description>

Types:  feat | fix | docs | refactor | test | perf | build | ci | chore
Scopes: the area touched, for example server | web | desktop | photometry |
        camera | mount | sequence | aavso | fits | config | site
```

Examples:

```
feat(server): live no-detection flag at measurement
fix(web): the readout says what a suspect point means
docs(site): the developer guide describes the 0.5.0 server
```

### Run the app

The web interface, for development: the server and the Vite dev server in one
command, the browser opened on them (Ctrl+C stops both):

```bash
.venv/bin/python run_web.py --sim             # the simulator, a separate dev config
.venv/bin/python run_web.py --replay DIR      # the simulator replays copies of real frames
.venv/bin/python run_web.py                   # your own config (~/.argos) and devices
```

`--sim` and `--replay` keep their configuration, sessions and logs under
`~/.argos-dev`; the last form uses your real configuration and sessions
folder, and its Connection screen reaches your real devices, so keep it for
the telescope. Details: {doc}`simulator_testing`.

The desktop app (the Tauri shell and the frozen server) is built as a
development build, "ARGOS Dev", for every local run; the steps are in
[`web/README.md`, "Desktop app (Tauri)"](https://github.com/jperret21/argos/blob/main/web/README.md#desktop-app-tauri).

The retired Qt app, for parity checks only (the `qt` extra):

```bash
uv run --extra qt python main.py
```

### Run the tests

The Python suite must run in **two processes**, as CI does: the whole suite in
one process can abort on the simulator fixtures, which looks like a test
failure but is a process-level crash. Run
`tests/ui/test_photometry_window.py` on its own, second.

```bash
export QT_QPA_PLATFORM=offscreen
uv run --extra dev --extra qt --extra server pytest -q --deselect tests/ui/test_photometry_window.py
uv run --extra dev --extra qt --extra server pytest -q tests/ui/test_photometry_window.py
```

The web interface and the desktop shell (CI's "Web UI and desktop shell"
job; the shell's tests compile against `web/dist`, so build the web first):

```bash
cd web
npm run check        # svelte-check: types and accessibility; warnings fail
npm test             # vitest
npm run build        # web/dist
cd src-tauri
cargo fmt --check
cargo clippy --all-targets -- -D warnings
cargo test
```

The documentation, with warnings as errors, as the Pages job builds it:

```bash
uv run --extra docs sphinx-build -W -b html docsrc /tmp/argos-docs
```

A correct run is green except the tests that skip themselves: the OmniSim
tests when no Alpaca simulator answers, the parity tests without PyQt6, and
the tests on recorded sessions when those are absent ({doc}`simulator_testing`).

> **Run the tests through `uv`.** Its `.venv` holds the pinned,
> mutually compatible dependencies. A system or Anaconda Python often pairs
> numpy 2.x with an `erfa`/`astropy` built for numpy 1.x, which raises a wall
> of `numpy.dtype size changed` errors at import time. Those come from the
> interpreter, not from the code.

### Format and lint

```bash
uv run --extra dev black --check argos/ tests/ main.py packaging/
uv run --extra dev ruff check argos/ tests/ main.py packaging/
```

These are CI's paths. Omit `--check` to apply Black's formatting.

### Documentation

| Tree | What it is | How it is built |
|---|---|---|
| `docsrc/` | These pages, the Sphinx sources | `sphinx-build -W`, in CI and in the Pages job |
| `docs/` | The public showcase at `perretjules.com/argos/` | Hand-written HTML and CSS; nothing generates it |
| `notes/` | Internal specifications, release notes, field notes | Not published; the code cites them by `§` and S number |
| `web/README.md`, `web/spec/` | The web interface: how to run it, its specifications and checks | Not published |

`.github/workflows/pages.yml` publishes `docs/` at `/argos/` and this
documentation at `/argos/docs/` together, on a push to `main` only.

Which page to edit:

- a behaviour an observer would notice: {doc}`guide` and the reference page
  that states the fact;
- a computed quantity: {doc}`differential_photometry`, and its constants
  table;
- a new or renamed FITS keyword: {doc}`fits_headers`, the single source for
  the writer's output; do not restate it elsewhere;
- a route or an event of the server: `argos/server/protocol.md`;
- a new module: its `docsrc/api/*.rst` page, or it vanishes from the
  reference;
- the project's positioning or downloads: `docs/*.html`, by hand.

Build the documentation before pushing: with `-W`, a broken cross-reference
fails CI instead of rotting quietly.

## Code standards

- **Python 3.11 exactly**; type hints on public signatures; Google-style
  docstrings on public classes and methods.
- **Line length 100.** Black formats, ruff lints, both over `argos/ tests/
  main.py packaging/`. `scripts/` is deliberately excluded: those are
  development utilities held to a looser standard.
- **No `print()`** in the package: `logging.getLogger(__name__)`. The
  exceptions are the server's command line (`argos/server/__main__.py`: its
  two start-up lines on stdout, `--self-check`, start-up errors before
  logging exists).
- **The server never imports Qt** (`tests/server/test_no_qt.py`).
- **The web interface uses design tokens**, never a colour value
  (`web/src/design/BRAND.md`), and every number on screen goes through
  `web/src/lib/format`.
- **No personal data in the repository**: tests use placeholder observer codes
  (`TST`, `TST01`) and no real site.

## Questions

Open an issue on GitHub.
