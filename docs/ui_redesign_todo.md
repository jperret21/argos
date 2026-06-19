# Argos UI Redesign — Remaining Work

> Explicit checklist of what is done and what is left for the workflow-phase UI
> redesign. Branch: `feat/workflow-ui`.
>
> Design spec (source of truth): `ui_design.md`.
> Missing UX features (science + robustness, full list): `ui_design.md` section 12.
> Build-order + status: `ui_design.md` section 10.

Last updated: 2026-06-19.

---

## Done

- [x] **7-phase workflow rail** — Connect / Target / Focus / Photometry / Capture /
      Analyze / Settings, replacing the old 3-mode shell. Settings pushed to the
      bottom. (commit `863a98e`)
- [x] **Capture right rail regrouped** by the one-axis rule into Session /
      Equipment / Display, replacing the six mismatched tabs. (commit `dc6fb8d`)
- [x] **Real Target screen** — observing-summary card (altitude / airmass /
      transit / Moon separation / mount-mode field) + Slew, backed by the pure,
      tested `sky_geometry.compute_target_geometry()`. (commit `4c0492f`)
- [x] **Real Focus screen** — HFD V-curve (samples + fitted parabola + vertex
      marker) + best-focus summary, backed by the pure, tested
      `core/imaging/focus.fit_v_curve()` (now also the single source for
      `AutofocusWorker._find_best`). Drives the Capture sweep via the new public
      `ImagingPage.request_autofocus` / `nudge_focuser` + `autofocus_*` signals;
      verifiable headless through `add_sample` / `set_best`.

---

## Remaining — phase screens

- [ ] **Photometry** — promote target/comparison/check selection to a first-class
      phase; wire the Photometry Setup companion. Interaction = AstroImageJ
      standard (click-to-place `T1`/`C2`/`C3`/`K`) + VPhot reusable field sequence.
- [ ] **Capture cockpit (monitoring)** — stability block (FWHM/HFD, SNR, Max ADU,
      background, tracking) + live light curve as the right-rail content; reduce
      controls to Start / Pause / Stop.
- [ ] **Analyze** companion — check-star + diagnostic co-plots, live ensemble
      toggle, in-plot reversible outlier removal, one-click AAVSO Extended Format
      export.
- [ ] **Connect** — standardise the device-row anatomy (driver dropdown + connect
      + state), one identical shape per device.
- [ ] **Settings** — group into one-axis sections (Observer & Site / Files &
      Folders / Astrometry / Photometry defaults / Appearance).

## Remaining — architecture (keystone, deferred to hardware-in-the-loop)

- [ ] **DeviceSession extraction** — a NINA-style equipment mediator that owns the
      device handles + connect/disconnect, so each phase screen can access the
      devices. **Cannot be verified headless** (the connect path needs a real
      Seestar; the smoke test never connects). Do it with the device attached.
      It unblocks:
  - [ ] Move the Equipment controls out of Capture into Target / Focus.
  - [ ] Put the live field image on Target / Focus / Photometry (not only Capture).
  - [ ] Slim Capture to a monitoring-only cockpit.

## Remaining — science & robustness (selected from `ui_design.md` section 12)

- [ ] **Mount mode alt-az vs equatorial** [SCI] — detect the active mode, surface
      it (Target + status bar), and gate field-rotation handling accordingly.
- [ ] **AAVSO observer code + transform coefficients (Tg, ...)** in Settings.
- [ ] **Target queue / "tonight's plan"** — cycle several variable stars in a night.
- [ ] Plate-solve failure handling; session resume / crash recovery; storage
      gauge; battery + thermal (55 C veto) indicators; end-of-target notifications.
- [ ] (Full list and details: `ui_design.md` section 12.)

## Open design questions (still for Jules — `ui_design.md` section 9)

- [ ] **Q1** — Target and Focus: keep as two screens, or merge into one?
      (currently two)
- [ ] **Q4** — Sequence editor: a dialog off Capture, or its own rail phase?
