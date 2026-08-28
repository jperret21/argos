# Argos — Project Status

> **0.4.1 is a field-validation alpha.** It is suitable for technically
> confident observers who keep their original FITS files and review results;
> it is not yet a general-public or unattended-observatory release.
>
> Last updated: August 2026

## What works today

| Area | Current capability |
|---|---|
| Connection | One Alpaca IP address + port, UDP/direct discovery, and independent mount/camera/focuser/filter-wheel status |
| Telescope control | GoTo, tracking, park, sync and abort through ASCOM Alpaca; manual jog through the Seestar native API |
| Planning | Target lookup (including common catalogues), altitude/visibility preview, editable sequence table and reusable presets |
| Capture | Live raw preview, display-only stretch, frame-quality measures, FITS loading and a dockable observer workspace |
| Sequences | Light/Dark/Flat/Bias runs, pause/resume/stop, optional autofocus hand-off and Siril-compatible session folders |
| FITS | Linear 16-bit science FITS with observing-site, pointing and camera metadata where available |
| Astrometry | Local ASTAP solving with an explicit star-database directory; ASTAP remains an external install |
| Photometry | Differential target light curve, separate comparison/check diagnostics, CSV export, batch re-run and per-frame JSONL diagnostics |
| Site setup | Place search, latitude/longitude/elevation, saved favourite sites and FITS-header propagation |
| Distribution | macOS `.dmg` build workflow, startup splash and automated bundle smoke test |

## Confidence boundaries

| Item | Status | What this means |
|---|---|---|
| Seestar S30 Pro | Reference profile | The software's reference optics/sensor profile. Continue field validation before relying on a result scientifically. |
| Seestar S30 / S50 | **Unvalidated** | The UI marks both profiles as unvalidated. Do not trust their precision photometry until Bayer layout, gain and linearity have been measured on real hardware. |
| Photometric uncertainty | Cross-checked implementation | The live calculation follows the project's `star_var_script` conventions, but needs multi-night comparison against independent reductions. |
| Plate solving | Local/offline once installed | ASTAP and a matching star database must be installed by the observer. Argos does not bundle either. |
| Internet services | Optional | AAVSO catalogue searches and place lookup need internet; successful AAVSO queries are cached for field use. |
| Platforms | macOS reference; Linux technical preview | Tags build a Debian/Ubuntu x86_64 `.deb` in CI. Linux still needs field validation; Windows is not a release target. |

## Before sharing beyond close testers

1. Run the field checklist on at least three real observing nights: connection,
   GoTo, solve, a short light sequence, a calibration sequence, an interrupted
   sequence and a clean shutdown.
2. Compare Argos photometry to `star_var_script` for several variables of
   different amplitude and brightness; retain the raw FITS, Argos CSV and
   reduction output for each comparison.
3. Validate S30 and S50 on hardware, or hide them from the default picker
   until that work exists.
4. Exercise recovery cases deliberately: Wi-Fi loss, a full disk, an ASTAP
   failure, camera disconnect and application restart during a sequence.
5. Have at least two external observers install the `.dmg` from scratch and
   follow the documentation without developer assistance.

## Known operating constraints

| Constraint | Current behaviour / operator action |
|---|---|
| macOS package is unsigned | Right-click the app and choose **Open** on first launch; later releases should be signed and notarised. |
| No weather or observatory-safety interlocks | Keep an observer in charge. Argos must not be used as an unattended safety system. |
| Phone hotspots can block discovery | Use **Discover** first; enter the known Seestar IP address if needed. |
| Catalogue lookups offline | Argos uses its cache only; pre-fetch planned fields before leaving home. |
| ASTAP missing or database missing | The Settings page reports it. Solving is unavailable until the local installation is fixed. |

## Quality gates currently run locally

- `ruff check` and `black --check` on application and tests;
- 436 automated tests passing (45 hardware/simulator-dependent tests skipped
  where the required device is unavailable);
- macOS CI runs lint, format checks and tests; the release workflow builds a
  `.dmg` and smoke-tests the bundled application headlessly.

The most important missing quality gate is now **repeatable field evidence**,
not another UI mock-up: real acquisition logs, raw FITS, independent
photometric comparisons and recovery tests from more than one observer.
