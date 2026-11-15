# Attention rules replayed on the owner's sessions (wave 6b, science review)

> Copied from the wave 6b science review's replay (2026-11-13) for the owner to mark before
> the thresholds are set (`alerts.*` in Settings › Alerts). The tables below describe the
> rules **as shipped to the review**; the last section says what the review's fixes changed.
> The scripts named below stayed in the review's scratch folder; they are not in the repo.

For the owner: mark each row **T** (true alarm, you would have wanted it), **F** (false alarm) or **?**,
in the "Owner" column. Times are UTC. No site coordinates are given here.

## How the replay was made

- **Code under test.** The server's own `argos.server.attention.AttentionService` from the main tree,
  as of 2026-11-13, not a re-implementation. It is driven synchronously with a scripted clock: a tick
  every simulated second (the no-new-frame rule) and every 60 s (the altitude rule).
  Script: `scripts/attn_replay.py`.
- **Runs.** The nine Qt **sequences** of the owner's three nights. Their starts and planned frame counts
  come from `argos.log` ("Sequence start: N frame(s)"). The single saved frames in the other session
  folders are Take shots / live saves, not runs, so the rules never watch them.
- **Inputs for each sub:**
  - DATE-OBS and the save time (the original file's mtime, read-only `stat`).
  - The server sequence's frame metrics: core `frame_metrics` on the raw frame (`hfd`, `star_count`).
  - The server `PhotometryService` outcome for that sub: the target's `comps_used`, or the skip reason
    (S35 `field_lost`, S48 `lock_lost`).
  - The photometry inputs are APFS clones of the frames and each run's target set. Solutions are the
    Argos-live solves, one landing before the next sub when 20 s passed (`live_resolve_s`), the S50 gate
    applied. Script: `scripts/phot_pass.py`.
- **Comparison sets.**
  - Main table: the owner's set as saved (6 comparisons, no check star).
  - Variant B: the comparison nearest the target turned into the check star on the copy (5 comparisons),
    as the brief asks.
- **Altitude.** Computed with the Settings site of each run, as the server does. The site comes from the
  FITS `SITELAT` / `SITELONG`. The default limit is 30°, since `site.min_altitude_deg` is not set.
- **Not replayable.**
  - Disk: the free space on those nights is not recorded.
  - Autofocus: there was no mid-run autofocus.
- **End of RR Lyr 2026-09-25.** `argos.log` shows the Seestar unreachable from 22:54:35 UTC: "TELEPHOTO
  not connected", then "Max retries exceeded". The Qt run then logged nothing more until the app closed at
  23:14:23 UTC. The replay keeps the run "running" over that gap (the frozen worker) and declares the
  mount lost after 3 failed polls (`mount_lost_after`, 22:54:42).
- **Other runs.** They end "stopped by the observer" 5 s after their last save. They stopped short of
  their plan, and the log gives no other reason.

## Every alert the shipped rules raise (main table: the owner's 6 comparisons)

The run_started / run_ended info events are not listed. Each of the 9 runs has one of each.

| # | Run | Sub | UTC raised | Rule | Level | Value | Threshold | Owner | Reviewer's reading |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 20260829T050148Z_XX_Cyg | 1 | 05:03:14 | No new frame | critical | 83 s since sub 1 started (05:01:51); sub 2 saved 05:03:30 (99.4 s) | 83 s = max(2 × 23.1, 23.1 + 60) | | **F** likely: the run's first interval is longer than the cadence floor, and the rule counts from the sub's *start*. Cleared 16 s later. |
| 2 | 20260829T052943Z_XX_Cyg | 1 | 05:31:08 | No new frame | critical | sub 2 saved 92.8 s after sub 1 started | 82 s | | F likely (same cause) |
| 3 | 20260829T053540Z_XX_Cyg | 1 | 05:37:04 | No new frame | critical | 92.4 s | 81 s | | F likely (same cause) |
| 4 | 20260907T040723Z_XX_Cyg | 1 | 04:08:50 | No new frame | critical | 109.7 s | 85 s | | F likely (same cause) |
| 5 | 20260907T040723Z_XX_Cyg | 23 | 04:38:59 | HFD rise | attention | HFD 21.5, 15.5, 20.2 px (subs 21-23) = 2.7× | 1.5 × 7.60 px (median of subs 1-20) | | T likely: focus degraded; the run was stopped after sub 24 |
| 6 | 20260907T044527Z_XX_Cyg | 1 | 04:47:40 | No new frame | critical | 190.2 s | 130 s | | F likely (same cause) |
| 7 | 20260907T045156Z_XX_Cyg | 1 | 04:54:09 | No new frame | critical | 139.3 s | 129 s | | F likely (same cause) |
| 8 | 20260907T045626Z_XX_Cyg | 1 | 04:58:38 | No new frame | critical | 139.2 s | 130 s | | F likely (same cause) |
| 9 | 20260925T195307Z_RR_Lyr | — | 19:53:08 | Altitude | attention | 12.2° (Settings site) | 30° now or within 15 min | | **F**: the Settings site was wrong that night (X3). The mount's own `ALTITUDE` header reads 75° |
| 10 | 20260925T195307Z_RR_Lyr | 1 | 19:54:48 | No new frame | critical | 133.4 s | 97 s | | F likely (same cause as #1) |
| 11 | 20260925T200453Z_RR_Lyr | — | 20:04:54 | Altitude | attention | 13.9° (Settings site); cleared 21:51:45 when that wrong-site altitude rose above 30.5° | 30° | | **F** (wrong Settings site; the mount reads 75° → 47° over the run) |
| 12 | 20260925T200453Z_RR_Lyr | 1 | 20:06:41 | No new frame | critical | 112.3 s | 105 s | | F likely (same cause as #1) |
| 13 | 20260925T200453Z_RR_Lyr | 150 | 22:16:34 | HFD rise | attention | 17.5, 17.6, 23.6 px (subs 148-150) = 2.7× | 1.5 × 8.65 px | | T (functional-spaces §4.10: frame 150, 22:16:14 DATE-OBS). Held to the end of the run, no repeat |
| 14 | 20260925T200453Z_RR_Lyr | — | 22:54:42 | Device lost (mount) | critical | 3 failed mount polls after the Seestar dropped | `mount_lost_after` = 3 | | T: the run never resumed; Qt raised nothing |
| 15 | 20260925T200453Z_RR_Lyr | 195 | 22:56:08 | No new frame | critical | no frame since sub 195 (started 22:54:16) | 112 s = max(2 × 51.5, 51.5 + 60) | | T: the same freeze, 1 min 32 s after the last save |

Variant B (check star assigned on the copy, 5 comparisons) adds two rows; everything else is identical:

| # | Run | Sub | UTC raised | Rule | Level | Value | Threshold | Owner | Reviewer's reading |
|---|---|---|---|---|---|---|---|---|---|
| B1 | 20260925T200453Z_RR_Lyr | 141 | 22:08:58 | Comparisons used | attention | 2 comparisons, subs 139-141 (cleared 22:12:20) | fewer than 3, 3 subs in a row | | ? Starts 7 subs before the HFD rise. With the owner's 6 comparisons (main table), 2 were used only on subs 184, 186, 188, 190 and 192, never 3 in a row, so no alarm. Qt's own CSV had 53, 186, 188, 190 and 192 |
| B2 | 20260925T200453Z_RR_Lyr | 185 | 22:46:14 | Comparisons used | attention | 2 comparisons, subs 183-185 (cleared 22:48:45) | same | | ? Inside the HFD event |

## No storm

- **Items per run.** At most 7 per run (the 195-sub run, variant B), and every cause is raised once.
- **Repeats.** The HFD item holds until the run ends and is never raised again. The two comparisons
  items are 37 min apart (REOPEN_S 600 s): two items, not a flapping one.
- **Critical tones.** The repeating tone (every 30 s) would sound for:
  - #14 and #15, until they are acknowledged;
  - each run-start "No new frame" (#1-4, #6-8, #10, #12), which cleared 7-25 s after it was raised.

  So every run of the three nights would have begun with a three-tone critical alarm.

## Alerts expected but not fired

| Run | Subs | What the data show | Why no rule fired | Reviewer's reading |
|---|---|---|---|---|
| 20260907T045626Z_XX_Cyg (the degraded run) | 1-3 | HFD 26.5, 24.7, 39.2 px = 3.5-5.2× the night's 7.60 px; stars 2 273, 1 414, 826 = 1.03, 0.64, 0.37× the 2 217 of 040723Z's first 20 subs (0.24× the 3 450 of 045156Z) | Baselines are per run and need 20 subs, so a 3-sub run is never judged. functional-spaces §4.10 says this run "would fire"; it does not | Expected, missed |
| 20260829T052943Z / 053540Z_XX_Cyg | all | HFD 9.5-11.7 px = 1.45-1.79× the 6.55 px of 050148Z's first 20 subs (same object, filter, 15 s, gain 80), 7 of 8 subs above 1.5× | Per-run baseline (4-sub runs) | With a baseline carried over runs of the same night, object, filter, exposure and gain, an HFD rise would fire at 053540Z sub 4 (05:39) |
| 20260829T050148Z_XX_Cyg | 19-22 | HFD 9.7, 12.1, 10.2, 10.4 px (1.5-1.85×) | Subs 19-20 belong to the baseline; only 2 judged subs (21-22) above 1.5× | Borderline, not a defect |
| 20260925T200453Z_RR_Lyr | 52, 175 | S35 `field_lost` skips (the replay's server photometry) | Isolated: never 3 in a row | Correct: no tracker alarm |
| 20260925T200453Z_RR_Lyr | 175 | Lowest star count 0.70 × 2 982 | Single sub | Correct |
| all | — | Disk | Free space not recorded | Not replayable |

## What a fix of the no-new-frame rule would give (verified on the same runs)

The rule measures the silence from the newest sub's **start** (DATE-OBS), but a client only learns of a new
frame at its **save**. Silence before the next frame is therefore cadence + the next sub's
start-to-save time (21-65 s on these runs, more on the first interval of each run).

Proposed fix:

- Count from the newest **save** (`frame_saved.t`).
- Take the cadence from save-to-save intervals.
- Before the second save, use F × floor + M, with floor = max(planned cadence, the first sub's
  start-to-save time).

With this fix, rows #1-4, #6-8, #10 and #12 disappear. The worst silence is 0.77 of its limit
(20260907T040723Z, sub 2: 84.9 s against 109.6 s). The freeze (#15) still fires, at 22:56:28 UTC.
Scripts: `scripts/silence_margin.py`, and `scripts/attn_replay.py --save-ref`.

## After the review's fixes (wave 6b fixer, 2026-11-14)

The fixes are in `argos/server/attention.py` and `argos/server/sequence.py`, with their tests in
`tests/server/test_attention.py`. The nine runs were replayed again on the same inputs with the fixed
`AttentionService` (the altitude and disk rules were not exercised by that replay).

- **No new frame** now counts from the newest **save** (`frame_saved.t`), with the cadence taken from
  save-to-save intervals; before the second save the limit is F × floor + M, floor = max(planned
  cadence, the first sub's start-to-save time) (`test_the_silence_runs_from_the_save_not_the_start`).
  Rows #1-4, #6-8, #10 and #12 are gone: no alarm at any run start; the worst silence is 0.77 of
  its limit (20260907T040723Z, sub 1 to 2). The freeze (#15) still fires: sub 195, 22:56:29 UTC.
- **Altitude.** The mount's own altitude is used when the mount points at the target; the
  Settings site extrapolates "within 15 min" only while the X3 site check does not report a
  mismatch, and with a mismatch and no mount reading the rule gives no verdict
  (`test_the_altitude_rule_takes_the_mounts_altitude_when_the_site_disagrees`). On the RR Lyr night
  the mount read 75° → 47°, above the 30° limit: rows #9 and #11 would not be raised. Not
  re-replayed: the replay has no mount pointing; this follows from the code and its test.
  A run without Light frames (the wrap-up's darks) has no altitude rule
  (`test_a_run_without_light_frames_has_no_altitude_rule`).
- **Disk** asks for the run's remaining frames when they need less than 30 min
  (`test_the_disk_rule_needs_only_the_runs_remaining_frames`).
- **A reopened item needs a new acknowledgement** (`test_a_reopened_item_needs_a_new_acknowledgement`);
  a non-critical item flapping within 15 min (`REOPEN_QUIET_S`) of its last tone neither sounds
  nor logs again.
- **Unchanged and left to the owner:** baselines per run (the degraded 2026-09-07 045626Z run and the
  29 Aug 052943Z / 053540Z runs are still never judged: see "Alerts expected but not fired"). Options
  in `web/spec/progress.md` (Wave 6b, owner decisions).

Rows that remain with the fixed rules, for the owner to mark:

| # | Run | Sub | UTC raised | Rule | Level | Owner |
|---|---|---|---|---|---|---|
| 5 | 20260907T040723Z_XX_Cyg | 23 | 04:38:59 | HFD rise (20.2 px = 2.7×) | attention | |
| 13 | 20260925T200453Z_RR_Lyr | 150 | 22:16:33 | HFD rise (23.6 px = 2.7×) | attention | |
| 14 | 20260925T200453Z_RR_Lyr | — | 22:54:42 | Device lost (mount) | critical | |
| 15 | 20260925T200453Z_RR_Lyr | 195 | 22:56:29 | No new frame | critical | |
| B1, B2 | 20260925T200453Z_RR_Lyr (variant B) | 141, 185 | 22:08:58, 22:46:14 | Comparisons used | attention | |

## Baselines carried over runs (owner decision 2026-11-14)

The rows above are untouched. This section replays the one change of 2026-11-14: the HFD-rise
and star-drop baselines (the medians of 20 subs of a filter) are carried over the runs of one
server session when object, filter, exposure and gain match; any other run makes its own, as
before; a server restart starts fresh (`argos/server/protocol.md`, "Baselines carried over
runs"; tests `tests/server/test_attention.py`, "Baselines carried over the runs").

How this replay was made:

- **Code under test.** The server's `AttentionService` (main tree, 2026-11-14), fed the
  `sequence` and `frame_saved` events of each run synchronously with a scripted clock: one
  service per night (one server session all night), against a new service for every run (the
  per-run baselines of the rows above).
- **Per-sub inputs.** Core `frame_metrics` (`hfd`, `star_count`) on APFS clones of the raw
  frames (deleted after reading); DATE-OBS, FILTER, EXPTIME, GAIN and OBJECT from their
  headers; the save time is the original's mtime (read-only `stat`), as above.
- **Only the two baseline rules change.** No other rule reads a baseline, so rows #1-15, B1 and
  B2 stand. RR Lyr 2026-09-25 200453Z (195 subs) was not re-measured: the session held no
  baseline when it started (195307Z, the same setup, had 5 subs), so its rules are the per-run
  ones and row #13 is unchanged.
- **Scripts** stayed in the role's scratch folder (`metrics.py`, `replay.py`); they are not in
  the repo.

Setup and baseline of each run:

| Run | Subs | Filter, exposure, gain | Baseline, carried over runs | Before (per run) |
|---|---|---|---|---|
| 20260829T050148Z_XX_Cyg | 22 | IR, 15 s, 80 | its own: subs 1-20, 6.55 px, 1 986 stars; kept by the session | its own |
| 20260829T052943Z_XX_Cyg | 4 | IR, 15 s, 80 | carried from 050148Z | none (4 subs) |
| 20260829T053540Z_XX_Cyg | 4 | IR, 15 s, 80 | carried from 050148Z | none (4 subs) |
| 20260907T040723Z_XX_Cyg | 24 | IR, 20 s, 80 | its own: 7.60 px, 2 217 stars; kept by the session | its own |
| 20260907T044527Z_XX_Cyg | 2 | IR, 60 s, 80 | none: no baseline of that setup | none |
| 20260907T045156Z_XX_Cyg | 3 | IR, 60 s, 100 | none: no baseline of that setup | none |
| 20260907T045626Z_XX_Cyg | 3 | IR, 60 s, 100 | none: 045156Z, the only earlier run of that setup, had 3 subs | none |
| 20260925T195307Z_RR_Lyr | 5 | IR, 10 s, 80 | none | none |
| 20260925T200453Z_RR_Lyr | 195 | IR, 10 s, 80 | its own (8.65 px), as before | its own |

New alert with carried baselines (the only one; same columns as the main table):

| # | Run | Sub | UTC raised | Rule | Level | Value | Threshold | Owner | Reviewer's reading |
|---|---|---|---|---|---|---|---|---|---|
| C1 | 20260829T053540Z_XX_Cyg | 4 | 05:39:38 | HFD rise | attention | HFD 11.7, 11.4, 11.1 px (subs 2-4) = 1.7×. Title: "HFD 11.1 px = 1.7× the first 20 frames of the run of 05:01 UTC" | 1.5 × 6.55 px = 9.83 px (median of 050148Z's subs 1-20, same object, IR, 15 s, gain 80) | | T likely: the HFD of 050148Z rose from about 6.5 px to 9.5-12.1 px at its sub 16 and stayed there through 052943Z and 053540Z. 052943Z (9.7, 11.0, 10.6, 9.5 px) has 2 subs in a row above 9.83 px, not 3: no alert there |

No star-drop alert is new: the carried 1 986 stars give a limit of 1 390, and 052943Z and
053540Z counted 1 916-1 978. No alert disappears.

Correction to "Alerts expected but not fired" (not edited above):

- **20260829T052943Z / 053540Z.** "7 of 8 subs above 1.5×" is 5 of 8 with these metrics: 9.5,
  9.7 and 9.7 px are 1.45-1.48× the 6.55 px.
- **20260907T045626Z, the degraded run, is still not judged** with the decided keys. Its setup
  (60 s, gain 100) differs from 040723Z's (20 s, gain 80), whose 7.60 px and 2 217 stars the
  review compared it with. functional-spaces §4.10 is corrected to say so.

What-if, not adopted (an owner decision): an HFD baseline carried on object and filter alone
(exposure and gain ignored; the star baseline kept on all four, since star counts scale with
the exposure: 2 217 at 20 s, gain 80 against 3 455 at 60 s, gain 100 that night):

| # | Run | Sub | UTC raised | Rule | Level | Value | Threshold | Owner | Reviewer's reading |
|---|---|---|---|---|---|---|---|---|---|
| W1 | 20260907T045626Z_XX_Cyg | 3 | 05:00:02 | HFD rise | attention | HFD 26.5, 24.7, 39.2 px (subs 1-3) = 5.2× | 1.5 × 7.60 px = 11.40 px (040723Z, 20 s, gain 80) | | T likely (the degraded run). Only with the what-if; no other alert: 044527Z 7.1, 8.9 px; 045156Z 8.2, 12.5, 12.6 px (2 in a row above 11.40 px, not 3) |

A single server session over several nights would carry a baseline from one night to the next.
On these nights it changes nothing: 2026-08-29 (15 s) and 2026-09-07 (20 s and 60 s) never
share a setup, and RR Lyr is another object.

### Owner decision 2026-11-15: the HFD baseline on object and filter, 12 h

The rows above are untouched. The owner adopted W1's rule on 2026-11-15: the HFD baseline is
carried on object and filter only, the star baseline keeps the four keys (object, filter,
exposure, gain), and no baseline is carried after 12 h without a sub of its setup (sub
DATE-OBS; for the HFD, any sub of that object and filter). Replayed as above (the same
per-sub metrics, the server's `AttentionService` of 2026-11-15) in three ways: one service per
night, one service for the three nights (a server left running), and that with the 12 h rule
switched off.

Baselines of each run with these rules (one server session per night):

| Run | HFD baseline | Star baseline |
|---|---|---|
| 20260829T050148Z_XX_Cyg | its own, 6.55 px | its own, 1 986 |
| 20260829T052943Z_XX_Cyg, 053540Z | carried from 050148Z | carried from 050148Z (same 15 s, gain 80) |
| 20260907T040723Z_XX_Cyg | its own, 7.60 px | its own, 2 217 |
| 20260907T044527Z_XX_Cyg (60 s, gain 80) | carried from 040723Z | none (2 subs) |
| 20260907T045156Z_XX_Cyg, 045626Z (60 s, gain 100) | carried from 040723Z | none (3 subs each) |
| 20260925T195307Z_RR_Lyr, 200453Z | as before (195307Z had 5 subs; 200453Z its own) | as before |

Alerts that differ from the per-run rows (same columns as the main table):

| # | Run | Sub | UTC raised | Rule | Level | Value | Threshold | Owner | Reviewer's reading |
|---|---|---|---|---|---|---|---|---|---|
| D1 | 20260829T053540Z_XX_Cyg | 4 | 05:39:38 | HFD rise | attention | as C1: 11.7, 11.4, 11.1 px (subs 2-4) = 1.7×. Title: "HFD 11.1 px = 1.7× the first 20 frames of the run of 05:01 UTC" | 1.5 × 6.55 px = 9.83 px (050148Z) | | as C1 |
| D2 | 20260907T045626Z_XX_Cyg | 3 | 05:00:02 | HFD rise | attention | as W1: 26.5, 24.7, 39.2 px (subs 1-3). Title: "HFD 39.2 px = 5.2× the first 20 frames of the run of 04:07 UTC" | 1.5 × 7.60 px = 11.40 px (040723Z, 20 s, gain 80) | | T likely (the degraded run) |

No other alert appears or disappears: 044527Z (7.1, 8.9 px) and 045156Z (8.2, 12.5, 12.6 px:
2 in a row above 11.40 px, not 3) stay silent on the carried 7.60 px; 040723Z keeps row #5 (sub
23, 04:38:59, on its own baseline); no star-drop alert (the only carried star baseline,
050148Z's 1 986 stars for 052943Z and 053540Z, gives a limit of 1 390; they counted 1 916-1 978).

One server for the three nights gives the same alerts, D1 and D2 and row #5: the HFD key
(XX Cyg, IR) is shared by 2026-08-29 and 2026-09-07, and the 12 h rule drops 08-29's 6.55 px
before 09-07 (the correction to the last paragraph above, written for the four keys). With the
12 h rule switched off it would differ:

| # | Run | Sub | UTC raised | Rule | Level | Value | Threshold | Owner | Reviewer's reading |
|---|---|---|---|---|---|---|---|---|---|
| W2 | 20260907T040723Z_XX_Cyg | 20 | 04:34:43 | HFD rise | attention | 14.5 px = 2.2× 6.55 px (08-29's 050148Z, 9 days earlier), instead of row #5 at sub 23 on its own 7.60 px | 1.5 × 6.55 px = 9.83 px | | what the 12 h rule prevents (not raised with it); D2 would read 6.0× instead of 5.2× |

Scripts: `att_replay.py` (the role's `replay.py` with these three modes) in the fixer's scratch
folder, not in the repo.
