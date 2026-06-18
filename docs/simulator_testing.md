# Testing Argos against the ASCOM Alpaca Simulator

Argos talks to the Seestar over **ASCOM Alpaca**. The same protocol is
spoken by the official **ASCOM Alpaca Simulators** (OmniSim), so you can develop
and test the whole app — connect, expose, preview, focus, jog, sequence —
**without the telescope plugged in**.

This doc covers:

1. [What the simulator gives you](#1-what-the-simulator-gives-you)
2. [Installing & building it (macOS arm64)](#2-installing--building-it-macos-arm64)
3. [Running it](#3-running-it)
4. [Manual app test against the sim](#4-manual-app-test-against-the-sim)
5. [Automated integration tests](#5-automated-integration-tests)
6. [Known sim quirks (expected, not bugs)](#6-known-sim-quirks-expected-not-bugs)
7. [Troubleshooting](#7-troubleshooting)

---

## 1. What the simulator gives you

OmniSim exposes a full set of Alpaca devices on one HTTP port (default
**`32323`**): **Camera**, **Telescope**, **Focuser**, **FilterWheel**, and more.
Argos connects to all of them exactly as it would to a real Seestar.

| You can test… | How the sim behaves |
|---|---|
| Connection panel | All 4 devices connect on `localhost:32323` |
| Live preview / exposure | Camera returns a synthetic star field on `StartExposure` |
| Display pipeline (debayer, STF, histogram) | Runs on the real downloaded frame |
| Focus (HFD curve) | Focuser moves; metric computed from the frame |
| Mount jog / GoTo | Telescope reports & updates RA/Dec |
| Sequencer | Chained exposures run end-to-end |

What it **won't** reproduce: the Seestar's native JSON-RPC features (UDP
auto-discovery, native jog, the real GRBG star field). For native-protocol tests
use the bundled `seestar_alp` simulator instead — see
[`tests/conftest.py`](../tests/conftest.py) (`seestar_simulator` fixture).

---

## 2. Installing & building it (macOS arm64)

The simulator is a .NET app. It is **not** vendored in this repo — clone it next
to your other dev projects (here: `~/Documents/perso/dev/`):

```bash
cd ~/Documents/perso/dev
git clone https://github.com/ASCOMInitiative/ASCOM.Alpaca.Simulators.git
```

You need the **.NET SDK** (Apple Silicon / arm64 build). Check it:

```bash
dotnet --version      # any 8.x or newer is fine
```

> Install via `brew install --cask dotnet-sdk` if missing.

### One required source edit (macOS only)

The project compiles Windows COM interop by default, which fails on macOS. Gate
it to Windows so the Alpaca server still builds everywhere. In
`ASCOM.Alpaca.Simulators/ASCOM.Alpaca.Simulators.csproj`, the `ASCOM_COM`
define must be **conditioned on Windows**:

```xml
<DefineConstants Condition=" '$(OS)' == 'Windows_NT' ">$(DefineConstants);ASCOM_COM</DefineConstants>
```

(If you cloned fresh and it isn't already conditioned, add the
`Condition=" '$(OS)' == 'Windows_NT' "` part.) This edit lives in the **simulator
clone, not in seerstar** — it is not tracked by this repo.

---

## 3. Running it

```bash
cd ~/Documents/perso/dev/ASCOM.Alpaca.Simulators/ASCOM.Alpaca.Simulators
DOTNET_ROLL_FORWARD=LatestMajor dotnet run
```

- `DOTNET_ROLL_FORWARD=LatestMajor` lets the project (targeting `net8.0`) run on
  a newer installed SDK (e.g. .NET 10) without retargeting.
- First run builds the project (a minute or two); subsequent runs are instant.

**Confirm it's up** (in another terminal):

```bash
curl -s http://localhost:32323/api/v1/telescope/0/connected
# → {"Value":...,"ErrorNumber":0,...}   means the server is live
```

The browser UI at <http://localhost:32323> lets you inspect device state and
change the port (**Server settings → Server Port**) if `32323` is taken. Keep it
at `32323` — that's the value Argos and the tests default to
(`SIMULATOR_PORT` in `tests/conftest.py`).

---

## 4. Manual app test against the sim

With the simulator running, launch Argos:

```bash
cd ~/Documents/perso/dev/seerstar
./run.sh
```

Then walk the app:

| Step | Where | Check |
|---|---|---|
| 1. Connect | **Connection** panel | Host `localhost`, port `32323` → **Connect** the 4 devices (LEDs go green) |
| 2. Preview | **Acquisition** → **Capture** | Start a 1 s exposure → image appears, **no UI freeze**, auto-STF stretches it |
| 3. Display | **Display** tab | R/G/B histogram visible; black/white/midtone sliders react; view selector (super-pixel / bilinear / CFA channels) |
| 4. Measure | on the image | Crosshair cursor + ROI selection → stats (min/max/mean/σ) show in the bar (not a big column) |
| 5. Focus | **Focus** tab | HFD curve fills as exposures roll in |
| 6. Mount | **Mount** tab | RA/Dec read back; jog moves the mount |
| 7. Filter | **Filter** tab | Connect the wheel → current filter shown; "Move to" rotates (Dark/IR/LP) |
| 8. Sequence | **Sequence** tab | Chain a few Light frames → progress advances, frames render |

---

## 5. Automated integration tests

A simulator-backed test suite drives the **real device wrappers + workers** the
way a live session does. Every test is decorated `@simulator_required`, so it
**auto-skips** when the sim is down and never breaks a normal `pytest` run.

```bash
# Full suite (sim tests skip if it's not running)
~/.local/bin/uv run --extra dev pytest

# Just the simulator suite (start the sim first)
~/.local/bin/uv run --extra dev pytest tests/core/test_simulator_*.py -v
```

| File | Validates |
|---|---|
| [`test_simulator_camera.py`](../tests/core/test_simulator_camera.py) | connect + metadata, gain tolerance, exposure state machine, image download, every display view (`render_view`), `frame_metrics` + `detect_stars`, full stretch path |
| [`test_simulator_telescope.py`](../tests/core/test_simulator_telescope.py) | position ranges, slew **reaches** target, tracking toggle, sync |
| [`test_simulator_focuser.py`](../tests/core/test_simulator_focuser.py) | caps + position, absolute move, relative step, halt-when-idle |
| [`test_simulator_filterwheel.py`](../tests/core/test_simulator_filterwheel.py) | connect, read position, change filter (Dark/IR/LP) |
| [`test_simulator_sequence.py`](../tests/core/test_simulator_sequence.py) | **end-to-end `SequenceWorker`** → FITS subs in the Siril folder + per-frame QA headers + a valid `session.json` (§7); a multi-filter plan **drives the wheel** and ends on the last filter |
| [`test_simulator_session.py`](../tests/core/test_simulator_session.py) | original smoke: camera→display pipeline, telescope position |

The sequence test runs the worker's `run()` synchronously on the test thread, so
its Qt signals fire by direct connection — no event loop needed.

Pure-logic pieces that back these flows are also unit-tested **without** the sim:
[`test_metrics.py`](../tests/core/test_metrics.py) (`detect_stars` FWHM/eccentricity)
and [`test_session_log.py`](../tests/core/test_session_log.py) (`session.json`).

---

## 6. Known sim quirks (expected, not bugs)

The OmniSim camera is generic, so a couple of things differ from a real Seestar.
Argos tolerates both on purpose:

- **Gain not implemented** → log line `Camera does not implement Gain —
  skipping`. The sim has no Gain property; the real Seestar does and is
  unaffected. (`set_gain`/`get_gain` in
  [`core/alpaca/camera.py`](../argos/core/alpaca/camera.py) swallow the
  `NotImplementedException`.)
- **JSON instead of ImageBytes** → log line `ImageBytes unavailable/mismatched —
  using JSON imagearray`. The sim's binary buffer doesn't match its reported
  dimensions, so the wrapper falls back to the JSON `ImageArray` path, which
  infers the true shape. The real device uses the fast binary path.

Both are informational. If you see them, the sim is working as intended.

---

## 7. Troubleshooting

| Symptom | Fix |
|---|---|
| `curl localhost:32323` refused | Simulator not running — start it (§3) |
| Tests all skip with "Simulator not running" | Same — start the sim, or it's on a different port |
| Build error about COM / Windows interop | Apply the `ASCOM_COM` Windows gate (§2) |
| `dotnet run` complains about framework version | Prefix with `DOTNET_ROLL_FORWARD=LatestMajor` (§3) |
| Port `32323` already in use | Change it in the sim's web UI (Server settings) **and** keep `tests/conftest.py` / the Connection panel in sync |
| App connects but no image | Give the exposure time to finish; the sim needs ~1 s + download before `ImageReady` |

---

**See also:** [ARCHITECTURE.md](ARCHITECTURE.md) ·
[capture_panel.md](capture_panel.md) ·
[CONTRIBUTING.md](CONTRIBUTING.md)
