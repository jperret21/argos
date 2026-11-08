# ARGOS web UI: the eight waves, and how to (re)launch one

This file is the playbook for building the web UI wave by wave. It says what each wave
contains, where it stands, and how to start, resume or re-run it with a team of agents, so
the work can stop at any point and be picked up later from this file alone.

To launch a wave, ask Claude: **"launch wave N following web/spec/waves.md"** (or "resume
wave N" when a run was stopped). Claude reads this file, checks the state of the branch,
builds the team of section 3 with the wave's scope from section 5, runs it, verifies the
result itself, shows the screenshots and commits only after the owner says so.

Sources this file summarises (they win if they disagree): `web/spec/README.md` (§7 the
waves, §4 the API rows, §2 the mapping rows), `web/lab/PROPOSAL.md` (§6 promotions by
wave, §7 server work, §9 WebKit risks), `web/spec/progress.md` (what each finished wave
actually delivered).

---

## 1. Status

| Wave | Content | Status | Commits (branch `explore/web-ui`) | Screenshots |
|---|---|---|---|---|
| W1 | Shell and Connection | **done** 2026-11-01 | `7525c61` server, `7d999b7` components and shell, `1902d6a` Connection, `7a7b359` gallery | `web/screenshots/2026-11-01_wave1-*` |
| Lab | Design lab and art direction | **done** 2026-11-01 | `d96f440` prototypes, `694a20f` decisions D1-D11 accepted | `web/screenshots/2026-11-01_lab-*` |
| W2 | Settings | **done** 2026-11-03 | `5462efd` server, `78b054a` design system and components, `437f612` Settings, `622b91e` gallery | `web/screenshots/2026-11-02_wave2-settings` |
| — | 0.5.0 fixes merged into the web branch | **done** | `c746875` (merge of `release/0.5.0`, incl. `94b12b7`) | — |
| W3 | Observe: acquisition | **reviewed and fixed** 2026-11-08 (exit criterion met through the UI; design, technical and science reviews applied, `progress.md` Wave 3 sections 2 and 6); the owner's commit pending | — (uncommitted) | `web/screenshots/2026-11-08_wave3-observe` |
| W4 | Field identification and image tools | **done** 2026-11-08: exit criterion met (roles and Night Red through the UI; tracking on 195 real frames, 0.2-0.9 px, no loss); design, technical and science reviews applied (`progress.md` Wave 4, section 6); the owner's commit pending | — (uncommitted) | `web/screenshots/2026-11-08_wave4-field` |
| W5 | Live photometry | to do | — | — |
| W6 | Plan (and Run, Watch, attention) | to do | — | — |
| W7 | Review | to do | — | — |
| W8 | Desktop app and Qt retirement | to do | — | — |

Update this table when a wave is committed (commit hashes, date, screenshot folder).

### Order and dependencies

```
W1 shell + Connection ──► W2 Settings ──► W4 field + overlays ──► W5 live photometry ──► W7 Review
        │                      │                 ▲                        │                  ▲
        └──► W3 Observe acquisition ─────────────┘                        └──► W6 Plan ──────┘
                                                                                  W8 desktop + Qt retirement (after W7)
```

W3 does not need W2 (device settings come from the devices). W4 needs W2 (ASTAP settings,
catalogue budgets) and W3 (viewer, HUD). W5 needs W4. W6 needs W5 for the Run band and the
live curve. W7 needs W5 (light-curve component) and W4 (viewer tools). W8 comes last.

---

## 2. Before launching any wave

1. **Clean base.** `git status` on `explore/web-ui` shows only `presentation/` and
   `ARGOS et star_var_script (1).pdf` (both deliberately untracked). If a stopped run left
   partial edits, that is a **resume**: keep them and add the resume note of §3.5.
2. **Green suites.** `.venv/bin/python -m pytest -q` (1039 passed, 71 skipped at `c746875`),
   and in `web/`: `npm run check`, `npm test`, `npm run build`.
3. **Release fixes.** If `release/0.5.0` (or a later release branch) gained commits, merge it
   first (`git merge --no-ff release/0.5.0`) so the server ports the fixed Qt behaviour; dry
   run with `git merge-tree --write-tree --name-only explore/web-ui release/0.5.0`.
4. **Owner decisions.** Everything in `web/spec/README.md` §8 and §1.3 and D1-D11 of
   `web/lab/PROPOSAL.md` §10 is decided. New questions go to the owner before the run, not
   inside it.

---

## 3. The team and the process (same for every wave)

### 3.1 Phases

| Phase | Agents | What they do |
|---|---|---|
| Foundations (parallel) | **backend** + one or two **front-end** developers | Backend writes the wave's routes into `argos/server/protocol.md` first, then implements and tests them. Front-end promotes the lab code of the wave (PROPOSAL §6) into `web/src/lib`, against that contract. Each owns distinct folders. |
| Integration | **integrator** | Builds the screens, wires everything, verifies end to end against the simulator, writes the wave's section of `web/spec/progress.md`. |
| Review (parallel) | **design review**, **technical review**, and a **science review** whenever the wave writes or computes data (W3, W4, W5, W6, W7) | Adversarial, run the app, read every screenshot, report findings with evidence and a fix. They edit nothing. |
| Finishing | **fixer** | Applies every high and medium finding (low when cheap), re-verifies, saves the final screenshots to the gallery, updates `protocol.md`, `web/README.md`, `progress.md`. |

Then Claude (main session) verifies alone: whole Python suite, ruff/black, `npm run check`,
`npm test`, `npm run build`, `npm run audit:night-red` on the Night Red originals, Qt app
untouched (`git diff --quiet -- argos/ui argos/workers argos/core`), `~/.argos/config.json`
untouched; reads the key screenshots; reports to the owner; commits on approval, split as:
server, components / design system, screens, gallery manifest (each web commit checked to
build on its own with `git checkout-index` into a scratch folder).

### 3.2 Cost

A full wave is 7 to 8 agents and several hours. **Owner rule (2026-11-08): save tokens
wherever possible, but never at the cost of development quality.** So the team, the model
(the session's, Opus), the reasoning effort and the reviews (design, technical, and science
when the wave touches data) stay as in §3.1. What is cut is duplicated work.

**Default economy measures (from W4 on):**

- **One shared screenshot set.** The integrator captures the wave's full state matrix (three
  themes at 1440x900, Observatory at 1280x800) once, into the wave's gallery folder with its
  `manifest.json`. Reviewers read those images and capture only the extra states they need
  to prove a finding; they do not re-shoot the whole matrix. The fixer re-captures only the
  screens its fixes changed and updates the manifest. (In W1 the design reviewer alone took
  148 screenshots that duplicated the integrator's.)
- **Lean hand-offs.** The next phase gets each report's summary, files and open issues; the
  full verification logs stay in the journal and are passed only to the fixer.
- **Targeted reading.** Prompts name the spec sections, files and lab sources each role
  needs; agents read those, not whole specs, and do not re-read what the brief already states.
- **Edit in place.** Change files with targeted edits; never rewrite a whole file to change a
  part of it.
- **Concise reports.** Structured fields, no narrative that restates the brief.
- **Run to completion.** Stopping a run mid-way throws away the context of the agents that
  were working; prefer to launch a wave only when it can run to its end.
- **Main session.** Verification by commands; read only the key screenshots; no re-reading
  of full reports.

**Variants that do reduce checking** (only if the owner asks for them): one combined design
+ technical reviewer; no separate fixer (the integrator applies the findings in a second
pass); a wave split in two halves each with a single review.

### 3.3 Rules every agent gets

- Never commit, stage, stash, reset, merge or switch branches; never touch `.worktrees/`.
- Do not modify the Qt app (`argos/ui`, `argos/workers`, `argos/core`): read it and port the
  Qt-coupled logic into `argos/server`, citing source lines. Science behaviour is the one of
  the **fixed** code (0.5.0, see `notes/release_0_5_0.md`).
- Never read-modify-write `~/.argos/config.json`, never write into `~/Argos/sessions`: every
  server for tests or smoke runs uses temporary `--config-dir`, `--log-dir`, sessions path,
  `HOME` and `TMPDIR`. Real FITS files may be **read** as fixtures after copying them to a
  temp folder; no personal metadata in reports.
- `web/src/lab` and `web/lab` are the reference: promotion copies and adapts into
  `web/src/lib`; lib never imports the lab; `npm run check` covers the lab and stays clean.
- Python: `.venv/bin/python`, never `uv sync`, black/ruff at 100 columns. No new npm
  dependency without the owner (PROPOSAL §8 says none is needed).
- Servers and vite in the background with recorded PIDs, killed at the end, each agent on
  its own ports (§3.4). Scratch files under the session scratchpad.
- Owner priorities: professional scientific-instrument look, symbols rather than text per
  BRAND, scarce brass (`npm run audit:brass`), the image is the hero (no dead band, reference
  1440x900 and 1280x800), Night Red strictly red, the logo is never redrawn, offline.
- Report honestly: failed or skipped checks are said.

### 3.4 Ports

One block per wave so concurrent agents never collide: wave N uses servers `87N0`-`87N9`
and vite `51N0`-`51N9` (backend smoke `87N0`, front-end A `87N1`/`51N1`, front-end B
`51N2`, integrator `87N3`/`51N3`, design review `87N5`/`51N5`, technical review
`87N6`/`51N6`, science review `87N7`, fixer `87N8`/`51N8`). Waves 1-3 used older ad hoc
ports (W3: 8790, 8791, 5193, 5194, 8745/5176, 8755/5185, 8756/5186, 8757, 8746/5177).

### 3.5 Resuming a stopped run

A stopped workflow keeps its partial edits in the working tree. Resume by adding to every
prompt: *"RESUMING AN INTERRUPTED RUN: partial, uncommitted edits are in the working tree
(list the paths from `git status`). Start with `git status` and `git diff <base commit>`
restricted to the paths of your role, keep what is sound, finish from there; do not redo
finished parts or revert other roles' files."* Agents that had finished in the stopped run
can be replayed from the workflow cache (`resumeFromRunId`) only within the same Claude
session; otherwise re-run them with the note.

### 3.6 What every wave delivers

- The wave's API rows in `argos/server` with tests in `tests/server`, documented in
  `protocol.md` (API 2 stays additive).
- Its screens in `web/src/lib`, its promoted lab components, gallery entries in `/?gallery=1`.
- `web/spec/progress.md`: a "Wave N" section with the mapping rows and their status, the
  exit-criterion evidence, the promotions done, the gaps.
- `web/screenshots/<date>_waveN-<slug>/` with `manifest.json` (captions for the website and
  the documentation), gallery rebuilt with `python web/scripts/build_screenshot_gallery.py`.

---

## 4. Prompt skeleton

Every agent prompt is: **CONTEXT** (branch, clean base commit, what is done, the merged
release fixes, decisions in force, this wave's scope from §5, files to read) + **RULES**
(§3.3) + **ROLE** (one of the paragraphs below, filled from §5) + the reports of the
previous phase for the integrator, reviewers and fixer. Every agent returns a structured
report: summary, files, verification (command and outcome), screenshots, open issues;
reviewers return findings (severity, area, file, problem, evidence, fix).

- **Backend:** write the wave's routes into `protocol.md` first; implement rows *[§5 API]*
  as `README.md` §4 specifies; port from the fixed Qt code with citations; extend the
  simulator when the wave needs it; tests for every route and event plus the wave's science
  parity checks; whole Python suite, ruff, black, a live smoke run with temporary folders.
- **Front-end A / B:** promote *[§5 promotions]* from the lab into the named folders, tokens
  only, keyboard and screen-reader support, Night Red safe, vitest tests, every new
  component in every state in the dev gallery; `npm run check`, `npm test`, `npm run
  build`; screenshots in the three themes, read; Night Red audit.
- **Integrator:** build *[§5 screens]* per the area spec, keep everything that works, add
  the new actions to the command palette; verify end to end against the simulator,
  including the exit criterion; screenshots at 1440x900 (three themes) and 1280x800; write
  the progress section.
- **Design review:** run on own ports, screenshot every state of the wave at both sizes and
  three themes, audit Night Red and brass, judge against BRAND and PROPOSAL; findings only.
- **Technical review:** conformance to `README.md` §4 and `protocol.md` both sides, event
  loop never blocked (measure), lifecycles (cancel, errors, shutdown), cleanup, no
  hard-coded colours, no new dependency, suites green; findings only.
- **Science review:** the wave's data against the fixed Qt code and the core functions on
  the same inputs (headers, measurements, fits, exports), with scripts and numbers;
  findings only.
- **Fixer:** apply the findings (science first), re-verify everything, final screenshots
  into the gallery with captions, update the docs, report what was fixed or skipped and why.

The last workflow scripts (W2, W3) are kept in the Claude session folder
(`~/.claude/projects/-Users-jperret-Documents-perso-dev-argos/<session>/workflows/scripts/argos-web-wave*.js`)
and can serve as a model; they hard-code that session's scratch folder.

---

## 5. The waves

Each wave lists: goal; API rows (`README.md` §4.3); shared components; screens and mapping
rows (`README.md` §2); lab promotions (PROPOSAL §6); extra server work (PROPOSAL §7); what
the science review checks; exit criterion; notes.

### W1 — Shell and Connection (done)

- **Goal:** start a night in the web UI: see and fix every device, find the Seestar, pick
  the profile; global log and status.
- **API:** A1-A4, A8-A10, A13-A18, A80 (and A19, the Stellarium bridge, brought forward).
- **Delivered:** shortcut registry, Dialog / ConfirmDialog / Popover / Menu / Select /
  Table / Drawer / LogView / JobProgress, StartupScreen, Connection screen, Planetarium
  card. See `progress.md` "Wave 1".
- **Exit criterion (met):** connect, discover, retry, disconnect each device without
  freezing; every Qt Connection control has its web control.
- **Gaps carried:** mount auto-retry not reproduced live (the simulator cannot lose its
  mount); alpyca's process-wide HTTP lock can delay other rows by up to 5 s.

### W2 — Settings (done)

- **Goal:** configure observer, site, paths, ASTAP, catalogues, privacy, appearance without Qt.
- **API:** A5, A6, A11, A67 (list only), A81-A84; config meta with read-only reasons,
  omitted keys and personal keys; the site-against-mount check (PROPOSAL §7).
- **Delivered:** SettingsForm, FilePicker, Sheet, Undo toast, SupportBundleDialog,
  Settings screen, About, Help items, command palette; promotions Control, Ring, tooltip v2,
  key hints, StatusBadge chips, NumberField v2 / Stepper / Slider, Readouts, `format/number.ts`,
  `charts/ink.ts`; BRAND amendments and tokens (D1-D11), D8 sizes, Night Red / brass audits
  as npm scripts.
- **Exit criterion (met):** every key of 02 appendix A editable or read-only with a reason;
  config changes sync live between two clients.
- **Gaps carried:** Observer & site scrolls about 90 px at 1280x800 while a site mismatch is
  shown; Comfortable density not yet on the levels fields and Devices rows; JS bundle over
  500 kB (split Settings into its own chunk); place search (Nominatim) and a real Seestar's
  own site untested; WebKit untested.

### W3 — Observe: acquisition (integrated 2026-11-08; reviews and commit pending)

- **Goal:** a full capture night: framing, filter, focus, autofocus, single FITS saves
  (lights, darks), jog, catalogue GoTo, Stellarium.
- **API:** A19-A31, A34-A41 (camera state and settings, Take shot with save, `frame_saved`,
  frame header fields, `frame_metrics`, Open FITS, filter wheel, mount alignment / jog with a
  server dead-man / tracking rate, focuser, moves, autofocus job, conditions, observation,
  target, catalogue resolve and suggest, target-name suggestions).
- **Components:** segmented filter control, jog pad, `VCurvePlot`, `ConditionsTimeline`,
  HUD chips.
- **Screens and rows:** Camera, Mount, Focuser cards, Conditions drawer tab, Open FITS
  dialog, status-bar frame / HFD segments, Planetarium target-name suggestions; M4,
  M38-M43, M48-M49, M59-M67.
- **Promotions:** Segmented (manual activation), SplitButton, Toolbar (data-driven,
  overflow), HoldButton (ring; Park), FocuserCard (gauge, queued taps D9), JogPad,
  Observe modes Framing and Focus (layout model, ModeBar, Arrange, Band; Field and Run
  shown disabled), splitter attachments, viewer HUD (chips, cursor readout D6), ExposureCheck,
  Histogram with keyboard handles and display ramp (D11), VCurvePlot with fit, one
  ConditionsTimeline, mini charts, frame worker statistics; icons watch, attention,
  inspector through the inventory.
- **Simulator:** star HFD depends on the focuser position (a V-curve); the wheel takes time
  to move.
- **Science review:** every Take-shot header (Light, Dark, Bias, Flat) against
  `fits_writer.py` with the same context; S1 Dark guard (wheel moving, other slot, no
  wheel), S2 per-frame snapshot, S3 FILTER read back, S20 QA on the saved frame, X1, X2;
  DATE-OBS / DATE-AVG; `frame_metrics` against core metrics; autofocus fit and Stop
  returning the focuser before the camera is released; Open FITS dating and refusal of
  non-raw data.
- **Exit criterion:** Take shot writes correct FITS metadata (S1-S3 fixed); autofocus runs,
  cancels and halts cleanly; jog stops on key-up, blur and socket loss.
- **Team used:** backend, controls and instruments, workspace and charts, integrator,
  design / technical / science reviews, fixer. Base commit `c746875`.

### W4 — Field identification and image tools (integrated 2026-11-08; reviews and commit pending)

- **Goal:** identify the field, see catalogues and roles on the image, click stars, centre
  the target; complete the viewer tools.
- **API:** A32-A33, A43-A49, A51-A53 (A32 centre on the target, A33 sync if kept; A43-A48
  field solve, automatic identification, field state, catalogue fetch, layers, per-frame
  transform; A49 star selection; A51-A53 the target set and its roles).
- **Components:** overlay layer (SVG), star card, viewer context menu, loupe, region tool,
  CFA preview and palettes (GPU), Statistics card, Catalogue layers popover, Settings sheet
  reuse.
- **Screens and rows:** Observe Field group, popover, star card, Statistics card, Display
  card view options; M7, M44-M47, M50 (pre-checks only), M51-M58.
- **Promotions:** Observe **Field** mode; FieldBand (comparison candidates table linked to
  the image), InspectorCard, StarCard (`imaging/field/*`); HUD compass and arcminute scale
  bar; OKLCH false-colour palettes (Fire, Ice; neutral in Night Red) from
  `research/frame/gl.ts`; virtual table rows (`research/table/*`) for the variables and
  Gaia lists.
- **Server (PROPOSAL §7):** candidates with `b_minus_v`, `neighbours_in_aperture`.
- **Science review:** WCS and field identification against the Qt path (ASTAP flags S24),
  catalogue positions on the image, role assignment written to `targets/<object>.json`.
- **Exit criterion:** overlays follow the tracked field; clicking a star assigns a role and
  writes `targets/<object>.json`; Night Red shows no non-red pixel.
- **Notes:** check WebGL2 R16UI on WebKitGTK before relying on the GPU palettes (PROPOSAL §9).

### W5 — Live photometry

- **Goal:** measure a variable star live: target set, ensemble, light curve, variables list.
- **API:** A50, A54-A58.
- **Components:** `LightCurvePlot`, `TargetSetList`, Ensemble table.
- **Screens and rows:** Photometry card, drawer tabs Light curve / Variables / Ensemble; M8
  (live parts), M78-M79, M95 (live tabs), M96-M99.
- **Promotions:** one `LightCurvePlot` + `charts/uplot/*` merged from the charts,
  workspace and research labs (linked facets; check star plotted as check − catalogue V with
  a trailing ±1σ band, D10; flags by shape; newest point with a static ring; zoom states
  Whole run / Following / Zoom kept; UTC / JD / BJD axis); Field band live status; the Run
  band uses the same component.
- **Server (PROPOSAL §7):** BJD_TDB per frame in the photometry stream; leave-one-out status
  per comparison.
- **Science review:** live points identical to the Qt values (same points, same errors,
  same flags, S16-S19 fixes), ensemble vetting (S17), ratio-only points (S18), BJD_TDB.
- **Exit criterion:** a sequence-free live run shows target and check curves identical to
  the Qt values (same points, same errors).

### W6 — Plan, and the Run experience

- **Goal:** plan and run sequences, transits, presets, visibility; follow a long run.
- **API:** A42, A59-A66 (A42 exoplanet lookup and suggest; A59 the sequence plan; A62 start,
  pause, resume, stop; A66 transit predict and plan; the rows between per `README.md` §4.3).
- **Components:** `VisibilityTimeline`, Steps table editors, run strip, Preflight popover.
- **Screens and rows:** Plan screen; M68-M77.
- **Promotions:** Observe **Run** mode (Run band = live light curve); RunCard (state, n/N,
  last-frame age vs cadence, end time, next autofocus, Pause, Stop) and the end-of-night
  wrap-up (D2); **Watch** view readable from 2 m (D3); attention system (rules on the
  server, levels by mark and word, status-bar chip and list, sound Off / Soft / Normal, D3);
  VisibilityTimeline (neutral coverage fill); night checklist / preflight; mini charts for
  the run.
- **Server (PROPOSAL §7):** WS `attention` event and `POST /api/attention/{id}/ack`, rules
  evaluated per frame (no new frame, HFD rise, star-count drop, too few comparisons,
  tracker lost, altitude limit, disk, run stopped on error, device lost); **mount-motion
  interlock** `409 run_active` on GoTo, Centre, Park, tracking off, jog and Sync during a
  run, with "Pause the run and slew" (D2); keep-awake during a run; preflight (disk,
  calibration counts, lid note).
- **Science review:** a transit plan written by the web UI produces `observation.json`
  (S5); no Light step defaults to the Dark slot (S7); visibility needs a site and covers
  transits after midnight (S26); attention thresholds replayed on the owner's sessions (the
  HFD rise of 2026-09-25 fires at frame 150 per `web/lab/research/functional-spaces.md`
  §4.10), with the owner marking true and false alarms.
- **Exit criterion:** a transit plan produces `observation.json`; Stop / Pause / outcome
  visible; no silent clamp.

### W7 — Review

- **Goal:** review sessions and the live run, export to AAVSO, inspect frames, re-run
  photometry.
- **API:** A67-A79.
- **Components:** plot wall (facets, linked axis, cell menu, expand pane), job strip,
  export dialogs, frame previous / next.
- **Screens and rows:** R0, R1, R2, Re-run dialog; M8 (re-run), M50, M80-M95, M100-M103.
- **Promotions:** `review/PlotWall.svelte` with the health strip and `charts/export.ts`
  (copy TSV, PNG); virtual table for Frames.
- **Science review:** exports byte-identical to `write_aavso` / `write_curves_csv` for the
  sample sessions with the 0.5.0 guards (S9-S13: check-star role kept, per-star CSV
  identified, flagged points left out, observer code required, batch re-run finds `.fit`,
  no JD 0, roles kept); airmass from the right source (the 2026-09-25 session has a wrong
  Settings site: its CSV airmass is wrong, the header AIRMASS is right).
- **Exit criterion:** exports byte-identical to `write_aavso` / `write_curves_csv` for the
  sample sessions, with the new guards; a re-run writes a new folder inside the session.

### W8 — Desktop app and Qt retirement

- **Goal:** ship the Tauri app (.dmg, .deb); remove PyQt from the runtime.
- **API:** A7, A12 (A7 shutdown, refused with what is busy unless forced; A12 reveal a file,
  desktop app only).
- **Components:** Quit dialog + shutdown scrim, custom title bar (Night Red), native app
  menu (Q-G10), crash notice, ⌘1-5.
- **Screens and rows:** M18, M20; optional multi-window later (D27 says no in v1).
- **Prerequisites:** Rust toolchain (`rustup`) — not installed; needs the owner's approval
  to install. Tauri v2 with the Python server as a sidecar (stdout `ARGOS_PORT` /
  `ARGOS_TOKEN` already implemented). Plugins: `tauri-plugin-window-state`; global
  shortcut only if the owner wants a system-wide abort; notifications rejected for v1.
- **Checks (PROPOSAL §9):** Popover API needs the macOS 14+ SDK (`vtool -show-build` on the
  release binary); WebKitGTK feature floor (2.50) and R16UI on Linux GPUs; Web Audio arming;
  Meta key-up while ⌘ is held; trackpad pinch; one pass of the labs' captures in a Tauri
  dev build on Windows if Windows is targeted.
- **Exit criterion:** every mapping row of §2 is "done"; the Qt inventory re-run on the
  final tree shows nothing new; `PyQt6` and `pyqtgraph` leave the runtime dependencies.
