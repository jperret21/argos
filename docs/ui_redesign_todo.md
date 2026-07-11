# Argos UX Redesign — Remaining Work

> Status + checklist for the NINA-inspired, capture-first redesign.
> Branch: `feat/ux-redesign` (based on `feat/workflow-ui`).
>
> The plan came out of a full-code audit (2026-07-04): 8 incremental
> workstreams (WS1–WS8), each independently shippable, the app runnable after
> each. Priorities: acquisition is THE core experience (live preview, full
> camera params, autofocus/FWHM, clear sequence automation); live astrometry +
> photometry (light curves during acquisition) is the headline bonus;
> calibration (darks/offsets) stays in post-prod.
>
> Design spec: `ui_design.md` · missing science/robustness features: its §12.

Last updated: 2026-07-04 (WS5 landed).

---

## Done

- [x] **WS1 — Correctness floor** (`f765343`)
      Clip-before-cast in the ImageBytes path (no more uint16 wraparound) ·
      default Alpaca port 32323 · single-shot darks/bias expose shutter-closed ·
      the camera-dock filter combo physically moves the wheel (metadata follows
      the settled position) · take-shot/AF guards · 120 s timeout on the AF
      resume handshake (a lost AF can no longer hang the night) · Park
      confirmation dialog · SolveWorker QThread leak fixed.

- [x] **WS2 — Live loop + driver-derived limits** (`09c35d8`)
      ▶ Live / ■ Stop toggle on the camera dock, mutually exclusive with
      sequence/AF in both directions · gain/exposure ranges read from the
      connected driver (fallbacks kept) · offset/binning spinboxes shown only
      when the driver supports them, guarded mid-run · CCD + focuser
      temperature polled every 10 s · preview quality toggle (full/half),
      display-only — saved FITS stay full-res, decimated frames excluded from
      solve + photometry, WCS overlays cleared on geometry change.

- [x] **WS3 — CameraService** (`e828814`)
      One camera-ownership state machine (IDLE/LIVE/SINGLE/SEQUENCE/AUTOFOCUS),
      acquire/release with priority SEQUENCE > AUTOFOCUS > LIVE/SINGLE,
      preemption of the preview loop, mid-sequence AF handshake, double-release
      safe. 39 unit tests (`tests/workers/test_camera_service.py`).

- [x] **WS4 — Capture visibility everywhere** (`9f769ae`)
      Persistent capture strip in the top status bar (`●REC object · n/N ·
      ETA · HFD`, LIVE chip), visible on every screen, click → Capture ·
      sidebar phase dots (ready/active/blocked) replacing the dead `pulse()` ·
      shape+color device badges (● / ◐ / ○) · keyboard-focusable nav buttons ·
      View menu + F1-F7 derived from the single `MODES` tuple ·
      readiness-aware mode restore.

- [x] **Navigation collapse — 4 modes, NINA-style** (`9093cf4`)
      Target/Focus/Photometry screens deleted (thin scaffolds that deep-linked
      back to Capture). Equipment (ex-Connect) · Capture (THE screen) ·
      Analyze · Settings. The autofocus V-curve now lives in the FocuserDock
      (`widgets/vcurve.py`) next to the AF button; targeting = mount-dock goto
      + Stellarium; photometry roles = click the solved image.

- [x] **WS6 — Sequencer UI parity** (`69c2640`)
      Sequence panel in the wide bottom dock (tabs Sequence/Log) · per-step
      Interval + Dither columns · AF-on-filter-change + end-of-sequence
      action (full completion only, logged) · JSON presets · Pause/Resume at
      frame boundaries · active-row highlight · live pre-run duration
      estimate · dither implemented (alternating MoveAxis nudge + settle).

- [x] **WS5 — Session layer extraction** (`36337b3`) — *the keystone*
      New `argos/core/session/`: `DeviceSession` (device handles, connect/
      disconnect, discovery, typed `CameraCapabilities`, temp/position pollers,
      Stellarium server, `*_will_disconnect` hooks) + `AcquisitionEngine`
      (CameraService, LivePreview/Sequence/Autofocus workers, astrometry,
      catalog cache, target set, live photometry, FITS saves — widget-free).
      `ImagingPage` is now a pure view; the Shell routes Connect intents
      straight to the session. Typed payloads (`LiveFrame`, `PhotometryPoint`,
      `FilterWheelState`, `FocuserState`).

---

## Remaining

### WS6 leftovers

- [ ] Single shots go through the same `_shoot_one` semantics as sequence
      frames so filter/frame-type are correct by construction (the WS1 fix
      already made them honest; this is the structural unification)

### WS7 — Photometry consolidation

The headline science flow, previously split across two divergent paths — now
consolidated on the engine (WS7 landed):

- [x] **Delete `photometry_setup_window.py`** — replaced by the engine's live
      solve → catalog → role-assignment path (which already bakes comp catalog
      mags into `TargetStar.mags`, `imaging_page.py:_on_star_clicked` comparison
      branch). Its one unique capability (batch re-run over saved subs) is
      rebuilt as `argos/workers/photometry_batch_worker.py`.
- [x] Photometry runs on the engine (no second window); the live curve is a dock.
- [x] Single object identity: the camera-dock Object field → `CaptureParams`
      → `AcquisitionEngine._object_name()` keys FITS `OBJECT`, target sets and
      CSVs. The batch worker recovers the same identity from the target set.
- [x] One config-driven parameter set — `argos/core/photometry/params.py`
      (`PhotometryParams.from_config` + `measure_frame`) is the single source for
      live and batch; the setup window's fixed spinboxes/band combo are gone.
- [x] Revive `comparison_table.py` — `ComparisonEnsembleTable` shows the
      in-use comps (target-set role=comparison + their catalog mags) with remove,
      as a Comparisons tab of the Photometry window.
- [x] `PhotometryWindow` real API (`set_export_meta` / `feed_point` /
      `load_curves`), one 9-column CSV schema (`write_curves_csv`), saturated
      points ringed (red ×).
- [x] Batch re-run in a worker with progress + cancel (QThread, off the UI
      thread), driven from the Capture toolbar's "Re-run subs" button.

### WS9 — UI design pass: dockable workspace + themes (see `ui_design_pass.md`)

NINA-inspired customization — the user composes their own night cockpit:

- [x] **WS9a — Dockable Imaging workspace** (`d06114a`): every panel is a
      QDockWidget (movable/closable/floatable), panel-toggle strip, layout
      persisted with defensive restore, sober defaults
- [x] **WS9b — Statistics dock + HFD History dock** (`d06114a`): full stats
      grid (median/MAD off the UI thread), trend promoted out of the
      focuser dock
- [ ] **WS9c — Theme system**: parameterized Palette → generated QSS,
      presets (equilux, charcoal+teal NINA-like, high-contrast, red-light
      night mode), runtime switch from Settings → Appearance
- Note: WS9a should land BEFORE WS7's light-curve dock so the curve arrives
  as a dock, not another fixed splitter.

### WS8 — Capture cockpit + polish

- [x] Capture form frozen (read-only + hint) while a sequence/AF owns the
      camera, released on any state transition incl. errors
- [x] Bounded shutdown: all worker stops requested first, then joined under
      one 5 s global budget; a worker missing it is logged and abandoned
      instead of blocking the UI thread (was ~35 s worst case)
- [x] Mount auto-reconnect: retry every 10 s after a lost connection,
      stopped by explicit user disconnect or shutdown
- [ ] Storage / battery / thermal indicators — DEFERRED to the hardware
      session: the NativeClient is not integrated anywhere yet and the
      telemetry events aren't in docs/seestar_protocol.md; needs the real
      Seestar to observe what the firmware actually sends
- [x] theme.py alias layer retained intentionally (WS9c rebinds it from the
      Palette — it is now the compat surface, not dead code)
- [ ] Update `docs/STATUS.md` + `docs/ui_design.md` to the session-layer
      architecture (docs pass)

### Screens polish (can ride along WS6–8)

- [ ] Equipment — standardise the device-row anatomy (driver dropdown +
      connect + state), one identical shape per device
- [ ] Settings — group into one-axis sections (Observer & Site / Files &
      Folders / Astrometry / Photometry defaults / Appearance)
- [ ] Analyze — deeper vetting: check-star + diagnostic co-plots, live
      ensemble toggle, reversible outlier removal
- [ ] Optional target-info readout (altitude/airmass/transit/Moon from the
      pure `sky_geometry` helper, kept in core) as a compact line in the
      mount dock — NOT a screen

### Science & robustness (selected from `ui_design.md` §12)

- [~] Mount mode alt-az vs equatorial [SCI] — detect + surface DONE
      (AlignmentMode read at connect, shown in the status bar next to
      Tracking). Field-rotation handling DONE for batch photometry
      (`photometry/tracking.py`: apertures follow the field via anchor-star
      re-centroiding + rigid fit; `photometry.track_apertures` to disable)
      and `sky_geometry.field_rotation_rate()` feeds `compute_target_geometry`
      for the planned mount-dock geometry line. Still open: live-path
      rotation warning / session-length cap gated on the Alt-Az mode.
- [~] AAVSO observer code DONE (`observer.obscode`); transform coefficients
      (Tg, …) still to add in Settings
- [ ] Target queue / "tonight's plan" — cycle several variable stars a night
- [ ] Plate-solve failure handling · session resume / crash recovery ·
      end-of-target notifications

### Validation on real hardware (after or alongside WS6)

- [ ] Connect the physical Seestar S30 Pro: discovery, connect-all, filter
      moves, live loop, single shots (light **and** dark), a short sequence,
      autofocus sweep, park (with the new confirmation)
- [ ] Check driver-derived gain/exposure limits against the real camera
      (the mock exposes gain 0–100; the Seestar will differ)
- [ ] Verify FITS headers on real frames (exposure mid-time, filter, gain,
      offset, readout mode, site/observer)
- [ ] One real photometry pass: solve → catalog overlay → roles → live curve

### Open design questions

- [x] Q1 — Target and Focus screens: RESOLVED — both deleted; the night
      happens in Capture (user decision, 2026-07-04)

---

## Known machine quirks (this dev Mac)

- Something (IDE?) wipes/resyncs `.venv` between shell invocations — always
  chain `uv sync --extra dev` and the command in ONE invocation, and unset
  `VIRTUAL_ENV` / `CONDA_PREFIX` / `CONDA_DEFAULT_ENV` first (same reason as
  `run.sh`).
- Run tests as `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q
  --deselect tests/ui/test_photometry_window.py`, then that file alone.
  The full suite in one process can abort (pre-existing seestar_alp simulator
  thread pollution — lands in `test_photometry_window.py` or `test_shell.py`);
  retry once before concluding. Not an app bug.
- Simulator: `uv run python scripts/mock_alpaca_server.py` (Alpaca on 32323).
