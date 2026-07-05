# Argos — Real-Seestar Hardware Test Plan

> Protocol for the FIRST validation of the `feat/ux-redesign` branch against a
> physical ZWO Seestar S30 Pro. Written to be executed by a test operator or
> an AI agent driving the machine. Follow the order — later steps depend on
> earlier ones, and the destructive step (Park) is LAST.
>
> Report format: for every numbered check, record **PASS / FAIL / SKIP** plus
> the exact log line or observed value. On any FAIL, capture the session log
> (bottom dock → Log tab) and `~/.argos/` config, do NOT force-continue a
> section whose setup step failed.

## 0. Prerequisites

- [ ] The Seestar S30 Pro is powered on, opened via the ZWO app once (arm
      raised), then the ZWO app is fully CLOSED (it holds the connection).
- [ ] Seestar and this Mac are on the same Wi-Fi network (or the Mac is on
      the Seestar's own AP).
- [ ] `seestar_alp` (or an Alpaca bridge on the Seestar) is running and
      reachable: `curl -s http://<SEESTAR_IP>:32323/api/v1/telescope/0/connected`
      returns JSON with `"ErrorNumber":0`. Record `<SEESTAR_IP>`.
- [ ] Repo on branch `feat/ux-redesign`, clean tree. Launch with `./run.sh`.
- [ ] Note: run at DUSK or NIGHT for sections 6-8 (stars needed). Sections
      1-5 work in daylight.

## 1. Connection (Equipment screen)

1.1 [ ] Click **Discover** — the Seestar's address appears (UDP discovery).
        If not, type `<SEESTAR_IP>` and port `32323` manually; note which.
1.2 [ ] **Connect all**. Expected: the four status-bar badges turn to
        `● Mount  ● Camera  ● Filter Wheel  ● Focuser` (green, filled).
        Record any device that fails and its exact log ERROR line.
1.3 [ ] Statusbar shows `Tracking ON` or `Tracking OFF` (not `Tracking —`).
1.4 [ ] Sidebar: the Capture dot turns green (ready).
1.5 [ ] Log shows the driver-derived camera limits line
        (`gain … exposure …`). Record the values — they are the REAL
        Seestar limits (the mock exposes 0-100; expect different).

## 2. Capture screen — live loop & single shots (daylight OK, cap on)

2.1 [ ] Switch to Capture (F2). The dockable workspace shows: image area,
        Camera dock right, Sequence dock bottom.
2.2 [ ] Camera dock → set Exposure 1s, Gain mid-range → **▶ Live**.
        Expected: frames arrive continuously, stats strip updates
        (Min/Max/Mean move), status shows `Live preview`, statusbar shows
        the LIVE chip.
2.3 [ ] While Live runs: **◉ Take shot**. Expected: log `Saved …fits`, the
        live loop KEEPS running afterwards.
2.4 [ ] **■ Stop live**. Status returns to `Idle`.
2.5 [ ] Frame type `Dark Frame` → **Take shot**. Expected: a dark is saved;
        open the FITS (toolbar → Open FITS) and check header
        `IMAGETYP = 'Dark Frame'`. With the cap on, Max ADU should be low.
2.6 [ ] Check the saved FITS headers (any frame): `OBJECT`, `EXPTIME`,
        `GAIN`, `FILTER`, `DATE-OBS`, `DATE-AVG` (mid-time) present.
        Record `EGAIN`/`OFFSET`/`READOUTM` presence (driver-dependent).

## 3. Filter wheel — THE regression to watch

The camera-dock filter combo must PHYSICALLY move the wheel (WS1 fix).

3.1 [ ] Camera dock → Filter combo → select a different filter.
        Expected: the wheel is audible/visible moving; log `Filter → <name>`;
        the Equipment-tab FilterWheel dock shows the new position; the combo
        stays on the real settled position.
3.2 [ ] Equipment dock → move the wheel from THERE. Expected: camera-dock
        combo follows (syncs to the settled position).
3.3 [ ] Take one shot per filter position; check each FITS `FILTER` header
        matches the physical filter. THIS IS THE SCIENCE-CRITICAL CHECK.

## 4. Focuser + autofocus (needs stars — night; else SKIP 4.3+)

4.1 [ ] Equipment tab → Focuser dock: position readout is a plausible
        integer; Temp shows a value within ~10 min (10s polling).
4.2 [ ] In/Out ±100 steps: position changes accordingly; Halt works.
4.3 [ ] Point at a star field (see §5), start Live, then **⚡ Autofocus**.
        Expected: V-curve appears in the Focuser dock and fills in live;
        sweep ends with `Autofocus complete — best pos=… HFD=…`; the
        focuser lands at the vertex; HFD in the stats strip improves.
4.4 [ ] Statusbar action shows `Autofocus running` during, `Idle` after.
4.5 [ ] Try **Take shot** DURING the sweep. Expected: refused with
        `Autofocus running — it owns the camera` (no crash, no hang).

## 5. Mount (goto / tracking / Stellarium)

5.1 [ ] Mount dock: RA/Dec/Alt/Az update every ~2s.
5.2 [ ] Goto a bright target above the horizon (type RA/Dec). Expected:
        slew starts, `slewing` shows in the badge, position converges.
5.3 [ ] Tracking toggle ON/OFF works and reflects in the statusbar.
5.4 [ ] Jog dialog: arrows move the mount at the selected rate; release
        stops the motion.
5.5 [ ] (Optional) Stellarium: Equipment screen → start the server; in
        Stellarium connect a telescope on the shown port; Ctrl+1 slews
        Argos; the reticle follows the mount.
5.6 [ ] **Network-drop drill** (WS8): with the mount connected, toggle the
        Mac's Wi-Fi off ~15s then back on. Expected: badge goes to error,
        log `Mount connection lost.` then `Retrying the mount every 10s`;
        within ~30s of Wi-Fi return: `Mount reconnected`, polling resumes.

## 6. Sequence (night; 5-10 min run)

6.1 [ ] Sequence dock: build 2 steps — 5× Light 10s + 3× Light 5s on
        another filter. Set Interval 2s on step 1, `AF every 0`, When done
        `Nothing`. The estimate label shows a plausible total.
6.2 [ ] **▶ Start**. Expected: active row highlights, progress `n/N — ETA`,
        statusbar strip shows `●REC <object> · n/N · ETA · HFD` on EVERY
        screen (switch to Equipment and back to verify).
6.3 [ ] Camera dock form is FROZEN during the run with the ownership hint;
        Take shot/Live refused.
6.4 [ ] **⏸ Pause** mid-step: the current frame completes + saves, then the
        run holds (`Paused` status). **▶ Resume** continues at the right
        frame count.
6.5 [ ] Filter-change boundary between the steps physically moves the wheel
        before the first frame of step 2.
6.6 [ ] Let it COMPLETE. Expected: `Sequence complete.`, form unfreezes,
        strip clears. Check the session folder layout (per type/filter
        sub-folders, `session.json` present, frame numbering monotonic).
6.7 [ ] Second short run: **■ Stop** mid-way. Expected: stops at the frame
        boundary, `Sequence stopped.`, no mount action even if When-done
        was set (it only fires on FULL completion).

## 7. Astrometry + live photometry (night, ASTAP installed)

7.1 [ ] With a star field framed: toolbar **Solve**. Expected: `OK` solve
        summary with RA/Dec, WCS grid overlay appears.
7.2 [ ] VSX/VSP catalog fetch fires after the solve (needs internet);
        variables/comparisons chips arm; markers land ON stars, not offset.
7.3 [ ] Click a comparison star → info card shows its chart label + mags →
        assign roles: 1 target (a variable) + 2-3 comparisons.
7.4 [ ] Open the Light curve dock (panel strip). Take a few shots or run a
        short sequence: one point per solve/saved sub appears on the curve.
7.5 [ ] `~/Argos/sessions/targets/<object>_<star>.csv` exists with the
        9-column header
        `jd_utc,bjd_tdb,mag,mag_err,airmass,fwhm,sky_adu,comps_used,saturated`.
7.6 [ ] Toolbar **Re-run subs** over the just-captured folder: progress
        dialog runs and CANCEL works; after a full run the curve reloads
        and the batch mags are within ~0.1 of the live mags for the same
        frames (batch uses fixed-floor aperture — small offset expected;
        record the offset).
7.7 [ ] Analyze screen: reload the CSV → curve displays; AAVSO export
        produces a file stamped with your obscode + band.

## 8. Shutdown + park (LAST — closes the arm)

8.1 [ ] Start a Live loop, then quit the app (Cmd+Q). Expected: the window
        closes within ~5s (bounded shutdown); log ends with `Shell closed`;
        no zombie `python main.py` process (`pgrep -f main.py`).
8.2 [ ] Relaunch: the dock layout you left is restored; mode restore lands
        on Equipment (hardware mode not restored — by design).
8.3 [ ] Reconnect mount → Mount dock **⊙ Park**. Expected: a CONFIRMATION
        dialog appears first; on Yes the arm physically closes.

## 9. Telemetry reconnaissance (for the deferred WS8 item)

With the app closed, run the native probe and capture what the firmware
actually sends (this unblocks the battery/storage/thermal statusbar item):

```bash
unset VIRTUAL_ENV CONDA_PREFIX CONDA_DEFAULT_ENV
uv sync --quiet
.venv/bin/python scripts/validate_native.py <SEESTAR_IP>   # if present
```

- [ ] Save the full output. Any JSON events mentioning battery / capacity /
      freeMB / temp are GOLD — paste them verbatim in the report.

## Known non-blockers (do not report as bugs)

- The pytest suite's full-run abort (seestar_alp thread pollution) — test
  infra only, documented in `ui_redesign_todo.md`.
- Theme change from Settings needs a restart for dock title bars/side icons.
- Batch re-run REPLACES the CSVs of the same object (by design, documented).
- Dithering on alt-az nudges both axes; field rotation is untouched.

## Report template

```
ARGOS HARDWARE TEST — <date>, operator: <name/agent>
Seestar IP: …   firmware: …   branch/commit: …
Section 1: 1.1 PASS  1.2 FAIL (log: "…")  …
…
FITS header sample (2.6): …
Camera limits (1.5): gain …–…, exposure …–… s
Batch-vs-live mag offset (7.6): … mag
Telemetry capture (9): attached / none seen
Blockers found: …
```
