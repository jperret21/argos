# Data Model

The relationships between the key dataclasses and persisted files in SeerControl.

```{graphviz} data_model.dot
:align: center
```

## File persistence

| File | Format | Schema | Lifetime |
|---|---|---|---|
| `~/.seercontrol/config.json` | JSON | `Config` | Permanent |
| `session.json` | JSON | `SessionLog` + `FrameRecord`[] | One session |
| `targets.json` | JSON | `TargetSet` + `TargetStar`[] | One session |
| `*.fits` | FITS | 16-bit uint, full headers | Per frame |
| `photometry.csv` | CSV | `LcPoint` columns | Per target |
| `aavso.txt` | Text | AAVSO Extended Format | Per target |

## Key dataclasses

| Class | Module | Purpose |
|---|---|---|
| `Config` | `core/config.py` | Application settings (observer, camera, astrometry, photometry) |
| `SequencePlan` | `core/imaging/sequencer.py` | Acquisition plan (multiple steps) |
| `FrameSpec` | `core/imaging/sequencer.py` | One frame to shoot |
| `FrameWCS` | `core/imaging/platesolve.py` | Pixel ↔ celestial mapping |
| `SolveResult` | `core/imaging/platesolve.py` | ASTAP outcome |
| `TargetSet` | `core/catalog/targets.py` | Session's selected stars |
| `TargetStar` | `core/catalog/targets.py` | One star with role (target/comp/check) |
| `AperturePhot` | `core/photometry/aperture.py` | Raw aperture measurement |
| `DiffResult` | `core/photometry/differential.py` | Calibrated differential magnitude |
| `LightCurve` | `core/photometry/lightcurve.py` | Accumulated points for a target |
| `SessionLog` | `core/imaging/session_log.py` | Per-frame QA records |
