# Testing without a telescope

ARGOS can be developed and tested with no Seestar at hand, at four levels:

| Level | What it runs | What it checks | Section |
|---|---|---|---|
| Built-in simulator | `run_web.py --sim`: the server's synthetic camera, mount, filter wheel and focuser | Every screen and the device logic, except plate solving | [§1](#the-built-in-simulator) |
| Replay | `run_web.py --replay DIR`: the simulator serving copies of real Seestar frames | Field identification, tracking and live photometry on real frames | [§2](#replaying-real-frames) |
| Automated tests | `tests/server` (in process, no Qt, no network), `tests/packaging`, the web and shell tests | The contract, the science ports, the parity with the fixed Qt code | [§4](#automated-tests) |
| Alpaca devices | The ASCOM Alpaca Simulators (OmniSim), or `scripts/mock_alpaca_server.py` | The Alpaca clients of `argos.core.alpaca` against a conforming server | [§5](#ascom-alpaca-simulators-omnisim) |

```{admonition} None of these is a Seestar
:class: important

The 0.5.0 web UI and its server were tested with the built-in simulator and
with replays of real nights. They have not yet been used live on a Seestar:
the server's Alpaca path was run against fake devices and unreachable
addresses in its tests, not against the telescope (`web/README.md`, "Known
limits"; `web/spec/progress.md`, waves 1 and 3). Live testing on the
telescope is pending.
```

```{warning}
Every command on this page keeps your own files out of the way: never point
a development server at your observing configuration (`~/.argos`) or your
recorded sessions (`~/Argos/sessions`). A server started without
`--config-dir` reads `~/.argos/config.json`, and a fresh configuration saves
sessions to `~/Argos/sessions` (`argos/core/config.py`). Replay only
**copies** of frames.
```

(the-built-in-simulator)=
## 1. The built-in simulator

From the repository root, after `cd web && npm install` once:

```bash
.venv/bin/python run_web.py --sim                    # server + Vite + browser
.venv/bin/python run_web.py --sim --port 0 --no-browser
```

`run_web.py` starts `python -m argos.server --simulator` (the simulator is
connected at start-up) and the Vite dev server, then opens the browser on
`?api=…&token=…`. Ctrl+C stops both; a change under `web/src` reloads the page,
a change to the Python server needs a restart.

With `--sim` (and `--replay`), the server uses a **development
configuration**, seeded once in `~/.argos-dev/config/config.json`, whose
sessions, sequence presets, caches and logs all live under `~/.argos-dev`
(`run_web.py`, `seed_dev_config`). `--dev-dir DIR` puts that folder elsewhere,
for example in a scratch folder for screenshots. Arguments after `--` go to
the server (`run_web.py --sim -- --connect-timeout 5`).

What the simulator emulates (`argos/server/protocol.md`, "Simulator"; the
code is `argos/server/devices/sim_*.py`):

| Device | Behaviour |
|---|---|
| Camera | A Seestar **S50**-like sensor: 1080 × 1920 px, 16-bit, **mono**. 240 Gaussian stars (FWHM 2.8 px), a 1600 ADU pedestal plus 200 ADU/s of sky, shot and read noise, fixed hot pixels, a drift of about 5 px between frames. Gain scales the signal by 10^((gain − 80)/200). The exposure time is really waited, and Stop interrupts it. It reports no `ElectronsPerADU`, so the e-/ADU comes from the rest of the chain ({doc}`differential_photometry`). |
| Mount | German equatorial, slewing at 4°/s per axis, tracking at the sidereal rate, starting parked at the pole, at a fixed site. Alt-az from a closed-form sidereal time that ignores precession, nutation and refraction (about 0.4° in 2026), checked against astropy by the tests. |
| Filter wheel | The profile's slots (Dark, IR, LP); 0.6 s per slot. On **Dark** the camera gets no light, so the dark-frame checks can be tested on pixels. |
| Focuser | 0 to 10 000 steps; the star FWHM follows a V with its minimum at step 5 300, so the autofocus converges there. |

**What it cannot do.**

- **Plate solving.** The synthetic sky matches no catalogue, so the field,
  its tracking and the live photometry need a replay (§2) or Open FITS on a
  copy of a real frame (`web/README.md`, "Known limits").
- **The Seestar's frames.** The S30 Pro writes 3840 × 2160 GRBG colour
  mosaics; the simulator's frames are mono and S50-sized.
- **The Seestar's mount.** The Seestar is alt-az; the simulated mount is
  equatorial and reports a pier side.

(replaying-real-frames)=
## 2. Replaying real frames

```bash
cp -cR /path/to/a/session/lights /tmp/replay       # APFS clones on macOS; cp -R elsewhere
.venv/bin/python run_web.py --replay /tmp/replay
```

`--replay DIR` is the simulator with `--sim-replay DIR`: each exposure
returns the pixels of the next FITS file of `DIR` in file-name order (`.fit`,
`.fits`, `.fts`, raw 16-bit), starting again from the first after the last.
The sensor geometry and Bayer pattern are the first file's. The simulated
mount reports the pointing of the file being exposed (`RA`/`DEC`, else
`OBJCTRA`/`OBJCTDEC`), and is alt-az, as the Seestar that took the frames. So
field identification, the aperture tracker and the live photometry run on
real Seestar frames during a simulated sequence (protocol.md, "Simulator
replay source").

**Limits of a replay.**

- The frames saved during a replay are dated by the computer's clock, so
  their times, BJD_TDB and airmass are today's for that field, not the
  night's. A replay checks the pipeline; the night's own numbers come from
  Review and the re-run on the original session (see {doc}`guide`).
- Exposure, gain, focus and the wheel do not change the replayed pixels.
- A folder without a FITS image, or whose first file is not raw 16-bit,
  stops the server at start-up with the reason.
- The server writes nothing into `DIR`. Use copies anyway: the rule is that
  recorded sessions stay read-only.

## 3. The server on its own

```bash
.venv/bin/python -m argos.server --simulator --port 0 --dev-token dev \
    --config-dir /tmp/argos-dev --log-dir /tmp/argos-dev/logs
```

Once its socket listens, the server prints two lines on stdout,
`ARGOS_PORT=<port>` and `ARGOS_TOKEN=<token>`; everything else goes to
stderr. `curl http://127.0.0.1:<port>/api/health` answers without a token
(`{"ok": true, "version": "0.5.0", "api": 2, …}`); every other route needs
`Authorization: Bearer <token>`. A new `--config-dir` gets a fresh
configuration whose `sessions_path` is `~/Argos/sessions`: set it to a
scratch folder (in Settings, or seed `config.json` as `run_web.py` does)
before you record anything.

| Option | Effect |
|---|---|
| `--simulator` | Connect the built-in simulator at start-up |
| `--sim-replay DIR` | The simulator replays the FITS files of `DIR` (absolute path) |
| `--port N` | Port, 8742 by default; `0` takes any free port |
| `--dev-token TOKEN` | A fixed token instead of a random one per launch (development only; the server warns when it is short) |
| `--config-dir`, `--log-dir` | Configuration and log folders (default `$ARGOS_CONFIG_DIR`, else `~/.argos`; `$ARGOS_LOG_DIR`, else the platform's diagnostics folder) |
| `--connect-timeout S` | The TCP pre-check of an Alpaca address before a connect (3 s) |
| `--self-check` | Import the server and every file it loads by path, then exit (the packaging smoke test) |

The full contract, every route and every event, is
[`argos/server/protocol.md`](https://github.com/jperret21/argos/blob/main/argos/server/protocol.md).

(automated-tests)=
## 4. Automated tests

| Suite | Needs | Runs |
|---|---|---|
| `tests/server` | the `dev` and `server` extras | The server in process through Starlette's `TestClient`, on the simulator: no Qt, no network, sessions in pytest's `tmp_path` (`tests/server/conftest.py`, fixtures `make_client` and `science_client`). `test_no_qt.py` fails if the server imports Qt. |
| Parity tests, in `tests/server` | also the `qt` extra | Eleven files run the fixed Qt code and the server on the same inputs and compare the results; they skip themselves without PyQt6 (`pytest.importorskip`). Identity with the fixed Qt only shows that nothing regressed: the results are checked first against independent references ({doc}`validation`). |
| `tests/server/test_review_owner_sessions.py` | recorded sessions | Review on three recorded nights, read from `$ARGOS_OWNER_SESSIONS`; skipped when they are absent. |
| `tests/packaging` | the `dev` extra | The desktop shell and the sidecar's spec: versions, the files the frozen server loads by path. |
| `tests/core`, `tests/ui`, `tests/workers` | the `qt` extra for the Qt parts | The core, and the retired Qt app kept for parity. |
| `web/` | Node and `npm install` | `npm run check` (types and accessibility, warnings fail), `npm test` (vitest), `npm run build` |
| `web/src-tauri/` | Rust, and `web/dist` built | `cargo fmt --check`, `cargo clippy --all-targets -- -D warnings`, `cargo test` |

The commands, as CI runs them, are in {doc}`CONTRIBUTING`. The suite is run
in two processes; a single process can abort on the simulator fixtures.

(ascom-alpaca-simulators-omnisim)=
## 5. ASCOM Alpaca Simulators (OmniSim)

ARGOS talks to the Seestar over **ASCOM Alpaca**. The
[ASCOM Initiative's Alpaca Simulators](https://github.com/ASCOMInitiative/ASCOM.Alpaca.Simulators)
(OmniSim) speak the same protocol, so testing against them checks conformance
to the standard rather than to our own assumptions about it. They serve a
camera, a telescope, a focuser and a filter wheel on one HTTP port, `32323`
by default, which is also the Seestar's Alpaca port.

```{note}
The OmniSim tests below exercise the core's Alpaca clients
(`argos.core.alpaca`). The web UI connected to OmniSim has not been recorded
as tested for 0.5.0; the server's Alpaca adapter is covered by its tests with
fake devices (`tests/server/test_alpaca_adapter.py`,
`test_unreachable.py`).
```

### Run it with Docker

No .NET SDK needed. Clone the simulators wherever you keep source, then build
the image once (the `ASCOM_COM` define must first be conditioned on Windows,
see below, or the Linux build fails):

```bash
git clone https://github.com/ASCOMInitiative/ASCOM.Alpaca.Simulators.git
cd ASCOM.Alpaca.Simulators
docker build -t omnisim .
```

Run and stop it (quote the `--urls` glob, or zsh expands it):

```bash
docker rm -f omnisim 2>/dev/null
docker run -d --name omnisim -p 32323:32323 -p 32227:32227/udp \
    omnisim dotnet ascom.alpaca.simulators.dll '--urls=http://0.0.0.0:32323'
docker stop omnisim
```

### Or build it with .NET

You need the .NET SDK (8 or newer; on macOS, `brew install --cask dotnet-sdk`).
The project compiles Windows COM interop by default, which fails elsewhere: in
`ASCOM.Alpaca.Simulators/ASCOM.Alpaca.Simulators.csproj`, condition the
`ASCOM_COM` define on Windows (an edit in your clone of the simulators, not
in this repository):

```xml
<DefineConstants Condition=" '$(OS)' == 'Windows_NT' ">$(DefineConstants);ASCOM_COM</DefineConstants>
```

Then, from the project folder:

```bash
cd ASCOM.Alpaca.Simulators/ASCOM.Alpaca.Simulators
DOTNET_ROLL_FORWARD=LatestMajor dotnet run
```

`DOTNET_ROLL_FORWARD=LatestMajor` lets the project, which targets `net8.0`,
run on a newer SDK. Check that it is up:

```bash
curl -s http://localhost:32323/api/v1/telescope/0/connected
# {"Value":...,"ErrorNumber":0,...}
```

Its own page, <http://localhost:32323>, shows the devices' state. Keep the
port at `32323`: it is the tests' default (`SIMULATOR_PORT` in
`tests/conftest.py`).

### The OmniSim test suite

Every test in these files is marked `@simulator_required` and skips itself
when nothing answers on `localhost:32323`, so a normal run never fails
because the simulator is down.

```bash
export QT_QPA_PLATFORM=offscreen
uv run --extra dev --extra qt --extra server pytest tests/core/test_simulator_*.py -v
```

| File | Checks |
|---|---|
| `test_simulator_camera.py` | Connection and metadata, gain tolerance, the exposure state machine, the download, every display view, `frame_metrics` and `detect_stars`, the stretch |
| `test_simulator_telescope.py` | Position ranges, a slew that reaches its target, tracking, sync |
| `test_simulator_focuser.py` | Capabilities and position, absolute and relative moves, halt |
| `test_simulator_filterwheel.py` | Connection, position, a filter change (Dark, IR, LP) |
| `test_simulator_sequence.py` | The retired Qt `SequenceWorker` end to end: FITS files in the session folder, the per-frame quality keywords, a valid `session.json`; a multi-filter plan drives the wheel |
| `test_simulator_session.py` | Camera to display, telescope position |
| `test_telescope.py` | Also holds `@simulator_required` cases beside its unit tests |

`test_simulator_sequence.py` imports PyQt6 and needs the `qt` extra.

### Expected differences from a Seestar

The OmniSim camera is generic, and ARGOS tolerates two of its differences on
purpose:

- **No Gain property.** The log says `Camera does not implement Gain —
  skipping`; `set_gain` and `get_gain` in `argos/core/alpaca/camera.py`
  swallow the `NotImplementedException`.
- **JSON instead of ImageBytes.** The log says `ImageBytes
  unavailable/mismatched — using JSON imagearray`: the simulator's binary
  buffer does not match its reported size, so the client falls back to the
  JSON `ImageArray`, which gives the true shape.

| Symptom | Fix |
|---|---|
| `curl localhost:32323` refused | Start the simulator |
| Every OmniSim test skips | The simulator is down, or on another port |
| Build error about COM or Windows interop | Condition `ASCOM_COM` on Windows |
| `dotnet run` complains about the framework version | Prefix `DOTNET_ROLL_FORWARD=LatestMajor` |
| No image | Wait for the exposure plus the download (about 1 s) before `ImageReady` |

### The minimal mock: `scripts/mock_alpaca_server.py`

```bash
.venv/bin/python scripts/mock_alpaca_server.py           # listens on localhost:8765
```

A pure-Python stand-in serving only `telescope/0` and `camera/0`, with no
.NET or Docker. Start ARGOS with `run_web.py --sim` (its development
configuration), then in Connection: Disconnect all, Seestar, address
`127.0.0.1`, port `8765`, Connect all. Checked on 2026-11-16 with the 0.5.0 server through
its API (`POST /api/devices/connect-all`): the mount and the camera connect,
the filter wheel and the focuser fail with "unknown device", which is the
mock's limit, not a fault of ARGOS; a 1 s exposure returns a 100 × 100 frame
through the JSON fallback. Use OmniSim when all four devices matter.

**See also:** {doc}`ARCHITECTURE` · {doc}`CONTRIBUTING` · {doc}`seestar_protocol`
