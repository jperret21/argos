# FITS headers reference

Everything on this page is written by {mod}`argos.core.imaging.fits_writer`. The
data array is `uint16`, linear, and still in its Bayer mosaic — ARGOS never
debayers, stretches or scales what it writes to disk.

```{note}
Many headers are written **only when the acquisition supplied the value**. A
frame taken with no site configured has no `SITELAT`; a frame taken without a
solved target has no `TARGRA`. The tables below mark those *conditional*.
```

````{admonition} Reading one for yourself
:class: tip

```python
from astropy.io import fits

with fits.open("XX_Cyg_ir_light_e020000ms_g080_00024.fit") as hdul:
    print(repr(hdul[0].header))
```

The format is FITS 3.0 ([Pence et al. 2010](https://doi.org/10.1051/0004-6361/201015362));
keyword conventions follow the ASCOM/AAVSO usage common to acquisition software,
so most of what follows will already be familiar from N.I.N.A. or MaxIm DL.
````

## File naming

```text
{OBJECT}_{FILTER}_{TYPE}_e{EXPOSURE_MS}ms_g{GAIN}_{INDEX}.fit
```

For example `XX_Cyg_ir_light_e020000ms_g080_00024.fit`: a 20 s exposure at gain
80 through the IR filter, frame 24 of the series.

- The prefix is fixed for one homogeneous series; only the final index changes,
  which is what Siril's sequence discovery requires.
- Exposure is in **milliseconds**, zero-padded to six digits. The index is
  1-based and padded to five.
- `_g{GAIN}` is omitted when the gain is unknown.
- The extension is `.fit`, not `.fits`.
- There is deliberately **no timestamp in the filename** — the precise time
  belongs in `DATE-OBS`.
- Object, filter and type are sanitised for the filesystem and lower-cased
  (except the object, which keeps its case).

## Session folder

```text
{sessions}/{RUN}_{OBJECT}/
├── lights/
├── darks/
├── flats/
├── biases/
├── session.json
├── photometry_quality.json
└── diagnostics/
```

`{RUN}` is the run identifier, or the first frame's UTC timestamp formatted
`%Y%m%dT%H%M%SZ` when there is none — for example `20260906T213734Z_XX_Cyg`.
Image-type folders are lower-case plurals, as Siril expects.

## Structure

| Keyword | Meaning |
|---|---|
| `SIMPLE` | file conforms to FITS standard |
| `BITPIX` | number of bits per data pixel — always 16 |
| `NAXIS`, `NAXIS1`, `NAXIS2` | axis count and lengths (X/columns, Y/rows) |
| `EXTEND` | FITS dataset may contain extensions |
| `IMAGETYP` | `Light Frame`, `Dark Frame`, `Flat Frame` or `Bias Frame` |

`BZERO = 32768` and `BSCALE = 1` are added by astropy for unsigned 16-bit data.

## Timing

| Keyword | Meaning |
|---|---|
| `DATE-OBS` | UTC date/time of exposure **start** |
| `DATE-LOC` | local date/time of exposure start |
| `DATE-AVG` | UTC date/time of exposure **midpoint** |
| `MJD-OBS` | MJD of exposure start (UTC) |
| `MJD-AVG` | MJD of exposure midpoint (UTC) |
| `EXPTIME` | [s] exposure time |
| `EXPOSURE` | [s] exposure time (alias) |

The midpoint headers are the ones photometry uses: a light curve point is timed
by `DATE-AVG`, not `DATE-OBS`.

## Sensor and gain

| Keyword | Meaning |
|---|---|
| `GAIN` | camera gain **setting** (0–600 on the Seestar), not a physical unit |
| `EGAIN` | [e⁻/ADU] electron gain, with its source named in the comment |
| `GAIN_E` | [e⁻/ADU] electron gain (AAVSO alias) |
| `EPERDN` | [e⁻/ADU] electron gain (alias) |
| `RDNOISE` | [e⁻] read noise, from the sensor reference |
| `FULLWELL` | [e⁻] full-well capacity, from the sensor reference |
| `XBINNING`, `YBINNING` | binning factors — always 1 |
| `CCD-TEMP` | [°C] sensor temperature *(conditional)* |
| `OFFSET` | electronic offset / bias setting *(conditional)* |
| `READOUTM` | sensor readout mode *(conditional)* |

```{warning}
`GAIN` and `EGAIN` are different quantities. `GAIN` is the dimensionless slider
value; `EGAIN` is the electrons-per-ADU conversion the photometry noise model
needs. Do not use one for the other.
```

```{admonition} Which ADU? An unresolved question — read before you trust EGAIN
:class: danger

The sensor is a **12-bit ADC whose output is scaled into a 16-bit file**. That
leaves a factor of 16 hanging over every electron conversion, and this
documentation cannot tell you which side of it `EGAIN` sits on, because the code
does not record it.

The consistency check that ought to hold is
$\text{EGAIN} \times (\text{saturation ADU}) \le \text{FULLWELL}$. With ARGOS's
own reference values it fails at every shipped gain — see
{doc}`differential_photometry` §3.5 for the table. Something in
`EGAIN` / `FULLWELL` / `camera.linearity_max_adu` is referenced to a different
ADU scale from the others.

Until it is resolved: **`EGAIN` and `FULLWELL` are reference-table values, not
measured calibrations of your unit.** If your reduction depends on absolute
electrons — a real SNR, a photon-noise model — measure the gain yourself from a
pair of flats rather than reading it out of this header. Everything
*differential* is unaffected, because a constant gain error cancels.
```

## Instrument and optics

| Keyword | Meaning |
|---|---|
| `TELESCOP` | telescope name, from the active profile |
| `INSTRUME` | sensor name — `IMX585` for the S30 Pro |
| `APTDIA` | [mm] aperture diameter — 30.0 for the S30 Pro |
| `FOCALLEN` | [mm] focal length — 160.0 for the S30 Pro |
| `FOCRATIO` | focal ratio — f/5.3 for the S30 Pro |
| `XPIXSZ`, `YPIXSZ` | [µm] unbinned pixel size — 2.9 |
| `BAYERPAT` | Bayer pattern — `GRBG` |
| `XBAYROFF`, `YBAYROFF` | Bayer offsets |
| `EQUINOX`, `RADESYS` | equinox and celestial reference system |

```{admonition} Frames written before 0.4.1
:class: warning

`FOCRATIO` was written as f/3.2 instead of f/5.3, and `APTDIA` was not written
at all. Both are corrected in 0.4.1 — check any frame you already hold.
```

## Target and pointing

| Keyword | Meaning |
|---|---|
| `OBJECT` | target name, truncated to 68 characters |
| `FILTER` | the **physical filter-wheel** selection: `IR`, `LP` or `Dark` |
| `TARGRA`, `TARGDEC` | [h], [deg] requested target coordinates (J2000) *(conditional)* |
| `RA`, `DEC` | [h], [deg] pointing coordinates (J2000) *(conditional)* |
| `OBJCTRA`, `OBJCTDEC` | the same pointing in sexagesimal *(conditional)* |
| `ALTITUDE`, `AZIMUTH` | [deg] telescope altitude and azimuth *(conditional)* |
| `PIERSIDE` | side of pier *(conditional)* |

Sexagesimal formats are `HH MM SS.ss` for `OBJCTRA` (two decimals) and
`±DD MM SS.s` for `OBJCTDEC` (one decimal).

```{important}
`FILTER` is the filter wheel's position, never a photometric band. The band used
for differential photometry is a separate setting (`photometry.default_band`,
`TG` by default) and is not stamped into this header.
```

## Sky conditions

| Keyword | Meaning |
|---|---|
| `AIRMASS` | airmass at exposure start, Pickering (2002) *(conditional)* |
| `MOONSEP` | [deg] angular separation between target and Moon *(conditional)* |
| `MOONALT` | [deg] Moon altitude at the site *(conditional)* |
| `MOONPHAS` | Moon illuminated fraction, 0–1 *(conditional)* |

## Observer and site

| Keyword | Meaning |
|---|---|
| `OBSERVER` | observer name *(conditional)* |
| `SITELAT` | [deg] site latitude *(conditional)* |
| `SITELONG` | [deg] site longitude, east positive *(conditional)* |
| `SITEELEV` | [m] site elevation *(conditional)* |

## Software

| Keyword | Meaning |
|---|---|
| `SOFTWARE` | acquisition software and version |
| `SWCREATE`, `CREATOR` | the same, under their conventional aliases |
| `ANNOTATE` | session annotation *(conditional)* |

## Frame quality

Measured on the green plane and written per frame when the metric is available.

| Keyword | Meaning |
|---|---|
| `HFD` | [px] half-flux diameter, at the subsampled scale |
| `FWHM` | [px] mean star FWHM on the green plane |
| `NSTARS` | detected star count |
| `SKYLEVEL` | [ADU] median sky background |
| `ECCENTR` | mean star eccentricity, 0 = round |

```{important}
`HFD` and `FWHM` are both in **green-plane pixels**, which are twice the size of
raw sensor pixels. To convert to arcseconds, multiply by 2 and then by the
full-resolution plate scale — 3.74″/px on an S30 Pro, so one green pixel is
7.48″. Using the full-resolution scale directly gives an answer a factor of two
too small.
```

These describe the frame, not the photometry: they are the trends Review plots
to tell a good hour from a bad one.

## What is *not* in the header

```{admonition} The frames carry no astrometric solution
:class: warning

ARGOS writes no WCS. There is no `CRVAL`, no `CRPIX`, no `CD` matrix, no
`CTYPE`, and no plate-scale keyword of any kind among the 65 written above.
`RA`/`DEC` and `OBJCTRA`/`OBJCTDEC` record where the **mount** was pointing —
they are not a solved position and cannot be used to convert pixels to
coordinates.

The practical consequence for your reduction: **every frame must be re-solved
downstream.** Siril will do it, and ASTAP is already on your machine. Budget for
it, and do not assume a stacking script that expects a WCS will work on these
files unmodified.

The solution ARGOS computes during a session lives in the session record and in
the interface, not in the pixels you keep.
```

## The Bayer pattern is not negotiable

The array on disk is the raw CFA mosaic with `BAYERPAT = 'GRBG'`. Any tool that
reads it must debayer with that pattern, or the colours — and the photometry —
are wrong. ARGOS's own measurements never debayer at all: they read the green
plane described in {doc}`differential_photometry`.

```{warning}
If you open one of these frames and it looks grey and grainy at 1:1, nothing is
broken — you are looking at an undebayered mosaic. Siril debayers on import when
`BAYERPAT` is present; check that its *Debayer* setting is reading the header
rather than a forced pattern.
```

```{seealso}
{doc}`references` for the FITS standard, the AAVSO `TG` band definition and the
airmass formula behind the `AIRMASS` keyword.
```
