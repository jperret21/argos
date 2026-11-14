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
