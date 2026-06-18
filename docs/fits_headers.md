# FITS Headers Reference

> Mandatory headers for every science frame.
> Values for ZWO Seestar S30 Pro confirmed from seevar hardware docs (April 2026).

---

## Corrected Hardware Values

> ⚠️ CLAUDE.md listed incorrect values. The correct values are:
>
> | Field | CLAUDE.md (wrong) | Correct |
> |-------|-------------------|---------|
> | BAYERPAT | RGGB | **GRBG** |
> | FOCALLEN | 150 | **160** |
> | NAXIS1/NAXIS2 | 2160/3840 | **3840/2160** (W×H) |

---

## Mandatory Headers — Every Frame

```
SIMPLE  = T
BITPIX  = 16                          # unsigned 16-bit integer
NAXIS   = 2
NAXIS1  = 3840                        # width
NAXIS2  = 2160                        # height
BZERO   = 32768                       # uint16 → int16 offset (FITS convention)
BSCALE  = 1

# Acquisition
DATE-OBS= '2025-08-14T22:31:05.123'  # UTC ISO 8601, exposure start
EXPTIME = 10.0                        # seconds
GAIN    = 80                          # ADU gain (default)
XBINNING= 1
YBINNING= 1
IMAGETYP= 'Light Frame'               # 'Light Frame' | 'Dark Frame' | 'Flat Frame' | 'Bias Frame'

# Instrument
TELESCOP= 'ZWO Seestar S30 Pro'
INSTRUME= 'IMX585'
FOCALLEN= 160                         # mm (NOT 150)
XPIXSZ  = 2.9                         # µm — IMX585 pixel size
YPIXSZ  = 2.9
BAYERPAT= 'GRBG'                      # Sony IMX585 Bayer pattern (NOT RGGB)

# Pointing (read from Alpaca at exposure start)
RA      = <decimal hours J2000>
DEC     = <decimal degrees J2000>
OBJCTRA = '<sexagesimal RA>'          # e.g. '05 34 32.0'
OBJCTDEC= '<sexagesimal Dec>'         # e.g. '+22 00 52'
ALTITUDE= <degrees>
AZIMUTH = <degrees>

# Target
OBJECT  = '<target name>'             # e.g. 'SS_CYG', 'M42'
FILTER  = 'TG'                        # AAVSO code for untransformed Bayer green

# Observer site
SITELAT = <latitude degrees>
SITELONG= <longitude degrees>
SITEELEV= <elevation meters>
OBSERVER= '<name>'                    # from user config
```

---

## File Naming Convention

```
{TARGET}_{IMAGETYP}_{DATE}_{TIME}_{EXPTIME}s_{FILTER}_{FRAME:04d}.fits
```

Examples:
```
SS_CYG_Light_20260412_213045_10s_TG_0001.fits
M42_Light_20250814_223105_10s_LP_0001.fits
M42_Dark_20250814_230000_10s_NoFilter_0001.fits
```

seevar convention (for raw science frames):
```
{TARGET}_{YYYYMMDDTHHMMSS}_Raw.fits
```

---

## Session Folder Structure (Siril-Compatible)

```
~/Argos/sessions/
└── 20250814_M42/
    ├── Lights/
    │   └── M42_Light_*.fits
    ├── Darks/
    │   └── 10s/
    │       └── Dark_*.fits
    ├── Flats/
    │   └── Flat_*.fits
    ├── Bias/
    │   └── Bias_*.fits
    └── session.json
```

---

## Science Notes on Bayer Pattern

The Seestar IMX585 uses **GRBG** (not RGGB):

```
G R G R G R ...
B G B G B G ...
G R G R G R ...
```

For photometry:
- **Green channel** is used (densest sampling, best SNR)
- AAVSO reporting code: **TG** (transformed Green)
- Do NOT debayer before photometry — work on raw mosaic with Bayer-aware aperture code
- Saturation guard: 60,000 ADU

For display/preview only, standard debayering is fine.

---

## Image Array from Alpaca

Raw download from `GET /api/v1/camera/0/imagearray`:

```python
import numpy as np

# Response JSON contains flattened int32 array
raw = response.json()["Value"]

# Reshape to (height, width) = (2160, 3840)
frame = np.array(raw, dtype=np.int32).reshape(2160, 3840)

# Clip and convert to uint16 for FITS
frame_u16 = np.clip(frame, 0, 65535).astype(np.uint16)
```
