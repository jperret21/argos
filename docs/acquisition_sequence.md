```{warning}
This is a **design reference** based on an external flight sequence spec.
Some steps (A7–A8, post-session P1–P8) are not yet implemented.
```

# Acquisition Sequence Reference

> Based on seevar A1-A12 sovereign flight sequence (v5.0.0, April 2026).
> Adapted for Argos architecture.

---

## Overview

Each target observation follows a deterministic 12-step chain.
Steps A1-A8 are pre-acquisition setup; A9-A12 are the science acquisition.

```{graphviz} diagrams/sequence_execution.dot
:align: center
```

```
A1 → A2 → A3 → A4 → A5 → A6 → A7 → A8 → A9 → A10 → A11 → A12
Load  Safe  Init  Slew  Wait  Settle  Solve  Nudge  Plan  Acquire  QC  Commit
```

---

## Step Details

### A1 — Target Lock
Load next target from the nightly plan.
Required fields: `name`, `ra_hours`, `dec_deg`, exposure params.

### A2 — Safety Gate
Hard vetoes checked before any hardware is touched:
- Weather OK?
- Temperature < 55°C?
- Battery > 10%?
- Telescope reachable (HTTP probe)?

Abort entire mission if any veto fails.

### A3 — Session Init

```python
# Connect
PUT /api/v1/telescope/0/connected  Connected=true
PUT /api/v1/camera/0/connected     Connected=true

# Deploy
PUT /api/v1/telescope/0/unpark

# Enable tracking
PUT /api/v1/telescope/0/tracking   Tracking=true

# Configure camera
PUT /api/v1/camera/0/gain          Gain=80
```

Wait for `atpark=false` and `slewing=false` after unpark.

### A4 — Slew Command

```python
PUT /api/v1/telescope/0/slewtocoordinatesasync
    RightAscension=<decimal_hours>&Declination=<decimal_degrees>
```

Async — returns immediately, slew happens in background.

### A5 — Slew Verify

Poll until `slewing=false`:

```python
GET /api/v1/telescope/0/slewing
```

Timeout: 60 seconds. If timeout → skip target.

### A6 — Settle

Wait **8 seconds** after slew complete for post-slew vibration to damp.

### A7 — Pointing Verify *(future)*

Take a short exposure (2s), plate-solve, compare centre to intended target.
Compute pointing error in arcminutes.
Tolerance: 12 arcmin.

### A8 — Corrective Nudge *(future)*

If pointing error > 12 arcmin:
- `synctocoordinates` + re-slew
- Retry up to 2 times
- Skip target if still off

### A9 — Exposure Plan

Determine exposure duration based on target brightness, sky quality,
field rotation constraints (Alt-Az mount — rotation increases far from meridian).

### A10 — Acquire

```python
PUT /api/v1/camera/0/startexposure  Duration=<seconds>&Light=true

# Poll until ready
GET /api/v1/camera/0/imageready     # → true

# Download
GET /api/v1/camera/0/imagearray
# Returns int32 array — reshape to (2160, 3840)
# Convert to uint16 for FITS

# Get temperature for FITS header
GET /api/v1/camera/0/ccdtemperature
```

Timeouts: expose 120s, download 300s.

Write raw FITS to local buffer immediately.

### A11 — Quality Gate

Minimal flight-level QC:
- FITS file exists and is readable
- Array shape is (2160, 3840)
- Pixel values in sane range
- No transport corruption

### A12 — Commit

Update session log, advance to next target or end session.

---

## Post-Session: Science Reduction Chain (P1-P8)

After all frames are acquired, run postflight pipeline:

| Step | Name | Description |
|------|------|-------------|
| P1 | Ingest | Validate FITS, recover target identity |
| P2 | Calibration Match | Find matching dark frames (exposure, gain, temp) |
| P3 | Calibration Apply | Dark subtract, flat correct (future) |
| P4 | Astrometric Solve | Plate solve → WCS solution |
| P5 | Source Measurement | Bayer-aware photometry on GRBG mosaic |
| P6 | Ensemble Calibration | Comparison stars, zero-point solution |
| P7 | Quality Verdict | Pass/fail gate on all science requirements |
| P8 | Commit and Report | Update ledger, stage AAVSO reports |

### P7 Verdicts

- `OBSERVED` ✅ — science-grade, proceed to publication
- `FAILED_QC` — generic QC failure
- `FAILED_QC_LOW_SNR` — target too faint
- `FAILED_SATURATED` — target saturated (> 60,000 ADU)
- `FAILED_NO_WCS` — plate solve failed
- `ERROR` — unexpected error

---

## Session State Machine

```
IDLE → PREFLIGHT → PLANNING → FLIGHT → POSTFLIGHT → PARKED
                                  ↓
                               ABORTED
```

---

## Key Constants

```python
SETTLE_SECONDS         = 8      # post-slew vibration damp
SLEW_TIMEOUT           = 60     # seconds
EXPOSE_TIMEOUT         = 120    # seconds
DOWNLOAD_TIMEOUT       = 300    # seconds
POINTING_TOLERANCE     = 12.0   # arcmin (A7 threshold)
POINTING_MAX_RETRIES   = 2
VETO_TEMP              = 55.0   # °C
VETO_BATTERY           = 10     # %
DEFAULT_GAIN            = 80
CLIENT_ID              = 42
```

---

## Cadence Rules (Variable Stars)

| Type | Cadence | Rule |
|------|---------|------|
| Mira / LPV | 7 days | Period / 20 |
| SR (Semi-Regular) | 4 days | ~100-200d period |
| SRC | 5 days | ~200d period |
| CV / UG / RR Lyr | 1 day | Alert Corps requirement |
| Default | 3 days | Fallback |
