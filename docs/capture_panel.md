```{warning}
This is a **design specification** — it describes what *should* be built,
not necessarily what *is* implemented. Some features described here are
planned or partially complete. Check the source code and API reference
for the current state.
```

# Capture / Acquisition panel — science specification

> Source: photometry-expert review (2026-06). This is the authoritative spec for
> the Acquisition panel's *imaging* pipeline. It is versioned so it can be handed
> to any implementer. The non-negotiable principle is §0.

## 0. Non-negotiable: display pipeline ≠ data pipeline

- Debayering, stretch, channel selection, false colour, interpolation — **affect
  display only.**
- The **saved FITS stays raw, linear, 16-bit, CFA intact** (`BAYERPAT='GRBG'`).
- **Never** save a debayered/stretched frame as a science light, and **never** the
  Seestar live-stacked JPEG — photometry needs the individual raw subs.

Architectural consequence: the rendering functions take the raw array and return a
*new* display array; they never mutate the captured array, and the FITS writer is
fed the original raw array. (Already true in `FITSWriter.write` — keep it that way.)

## 1. Debayering — three selectable preview modes

Interpolated demosaicing (bilinear/VNG/AHD) correlates neighbouring pixels and
breaks noise statistics + flux linearity. Fine for a pretty preview, **forbidden
for measurement**. So the preview offers three modes:

| Mode | Use | Note |
|---|---|---|
| **Raw / CFA** (no interpolation) | check Bayer matrix, hot pixels | shows the mosaic; lets you verify GRBG alignment (S30 is **GRBG**, not RGGB — if wrong, R/B swap) |
| **Super-pixel** (2×2 → 1 RGB px) | scientifically clean preview | half-res, introduces no correlation |
| **Interpolated** (bilinear) | nice framing / presentation | cosmetic only |

## 2. Channel selection / split — R, G, B, and G is central

Display: RGB combined · R / G / B alone · Luminance/mono · **G1 / G2 separate**
(detect green-gain imbalance, estimate noise).

Why G matters:
- **Photometry (OSC):** the green channel ≈ Johnson V; AAVSO accepts it as the
  **TG** band for DSLR/OSC differential photometry. Differential photometry is done
  on G.
- **Astrometry / plate-solving:** done on a grayscale image; the extracted **G**
  (best SNR, double density in the CFA) is the best input for astrometry.net.

**Critical:** channel extraction *for measurement* is a **CFA split** (real green
pixels), never the green plane of an interpolated image.

## 3. Stretch & histogram (non-destructive display)

- Auto-stretch STF (1%–99%) — visual only.
- Manual: black point / midtones / white point.
- Linear / log / asinh toggle.
- **Per-channel histogram** (R, G, B), not only luminance.
- Persistent indicator: **“display stretched — linear data on disk.”**

## 4. Measurement tools — the science core of the panel

- **Pixel readout on hover:** ADU under cursor, per channel **and** in raw CFA.
- **Region statistics** (mouse-drawn box): mean / median / std / min / max / N px
  — for sky background, noise, extended-object level.
- **Saturation / clipping indicator:** highlight (red) pixels above a configurable
  full-well threshold. Photometry must stay in the linear regime; a saturated /
  near-non-linear star is unusable. (Threshold from config — see §8.)
- **Sky-background level** (running median) — judge light pollution / sub length.
- **SNR** on a selected star.

⚠️ These measurement regions are **software/display**. Do **not** confuse with the
camera hardware ROI mode, which is forbidden (Seestar firmware bug, see handoff.md).

## 5. Focus tools

- **FWHM / HFD** live on detected stars (mean + on clicked star).
- **Loupe / 100% zoom** on a star for fine manual focus.
- **HFD trend mini-graph** over the last frames during autofocus.

Seestar scale: 2.9 µm @ 160 mm → **~3.74″/px**, undersampled. Stars are ~1–2 px
FWHM in good seeing → FWHM is coarse, and photometric aperture radii (~3–5 px) must
account for this.

## 6. Astrometry / plate-solving

- Solve the current frame (local astrometry.net or API) **on the extracted G**.
- Show: centre RA/Dec, scale (arcsec/px), rotation, mirror.
- Overlay: WCS grid + target circle (confirm centring before a sequence); detected
  stars (count + apertures).

## 7. Per-frame quality feedback (during acquisition)

Per sub, log + mini-curve: **HFD, star count, sky background, max ADU,
eccentricity.** Spot clouds/defocus/vibration live; sort subs later. Also write into
the FITS header and/or `session.json`.

## 8. Hardware to lock down (else photometry is wrong) — config, not hardcoded

- **ADC depth & 16-bit scale factor** — IMX585 Starvis 2 is a 12-bit ADC with
  HCG/HDR modes; "16-bit" is often a scaling.
- **Linearity / full-well threshold** → feeds the §4 saturation indicator.
- **System gain (e-/ADU) per gain setting** → SNR + noise estimation.

Proposed config keys (defaults to confirm against hardware):
```jsonc
"camera": {
  "adc_bits": 12,
  "fits_scale_bits": 16,        // raw scaled to 16-bit
  "full_well_adu": 60000,       // saturation/linearity threshold (16-bit scale)
  "linearity_max_adu": 50000,
  "egain_table": {}             // {gain_value: e-/ADU}; empty → driver/IMX585 lookup
}
```

## Implementation notes

- **Threading:** debayer + stretch + channel extraction run in a **QThread worker**
  (numpy/PyQtGraph), never on the UI thread, or the preview freezes the UI.
- `core/imaging/debayer.py` stays **Qt-free** and unit-tested (the data pipeline).
- Display rendering may live in a worker; measurement overlays in the viewer widget.

---

## Roadmap (MVP → phases)

**MVP (capture-grade) — DONE:**
- [x] §0 architecture (FITS writer saves raw linear CFA; rendering is separate)
- [x] §1 — three debayer modes (Raw CFA / Super-pixel / Interpolated)
- [x] §2 — channel split R / G / B / G1 / G2 / Luminance via CFA (real pixels)
- [x] §3 — stretch (black/mid/white, linear/log/asinh) + per-channel histogram + indicator
- [x] §4 — pixel readout, region stats (ROI), saturation highlight (full-well from config)

**Phase 2 — DONE:**
- [x] §5 — HFD trend graph + per-frame focus metrics (Focus tab); **FWHM overlay
  on detected stars** (rings sized by FWHM, `detect_stars` measures FWHM +
  eccentricity per star) + **100% loupe** (cursor-tracking 1:1 magnifier).
  Toggles live in the Display tab.
- [x] §7 — live per-frame metrics; **FITS QA headers (HFD/FWHM/NSTARS/SKYLEVEL/
  ECCENTR) written for single-shot *and* sequence frames**; **`session.json`**
  rolls up every sub's metrics (written atomically as the sequence runs).
- [x] move the display pipeline (debayer/stretch/channel/metrics/detect) into a
  QThread worker (`workers/preview_processor.py` — latest-frame-wins).
- [x] §8 — camera ADC/full-well/linearity exposed in config + Configuration UI;
  the saturation threshold reads full-well from config

**Phase 3:**
- [x] §6 — plate solving on the green plane via **ASTAP**: solver glue
  (`core/imaging/platesolve.py` + `workers/solve_worker.py`), an **Astrometry
  config panel** (ASTAP path/auto-detect, catalog, search radius, downsample,
  scale hint), and a **Solve** button in the analysis window (centre RA/Dec,
  scale, rotation). Now also: a **FrameWCS** model (astropy TAN, pixel ↔
  celestial on the green grid) with **`wcs_grid`** geometry; a **RA/Dec grid +
  field-centre marker + target reticle** overlay in the viewer (toggle in the
  Display tab); **per-star RA/Dec** on the clicked star (analysis window *and*
  live view); and a **live-frame Solve** (toolbar) that uses the mount RA/Dec as
  the position hint, reports the offset from the goto target, and draws the grid
  + target circle on the live image. **Future:** name the clicked star from a
  Gaia/UCAC catalogue (RA/Dec → designation + magnitude).

### Status
- `core/imaging/debayer.py` provides the **data-pipeline primitives** (CFA split +
  the 3 render modes), Qt-free and unit-tested. UI wiring exposes the modes in the
  image toolbar (display only).
