# Differential photometry — method and equations

This page states exactly what ARGOS 0.5.0 computes, with the equations as they are
implemented. Every formula below is traceable to a module in
{mod}`argos.core.photometry`; the headless server behind the desktop app
(`argos/server`) calls the same code, or a port of it that writes the same bytes
(checked in {doc}`validation`, §9). Fixes are cited by their number in the
release notes (S1-S85, X1-X3: `notes/release_0_5_0.md` in the repository).

```{admonition} Scope
:class: important

ARGOS measures **raw, uncalibrated sub-exposures**. No dark, flat or bias is
applied, and no colour transformation to a standard photometric system is
performed. The result is a **quick-look** light curve: enough to see that a
variable is varying, that comparison stars are stable and that the night is
usable — not a publishable measurement. Calibration, registration and final
photometry belong to Siril and `star_var_script`, on the raw frames ARGOS
preserves.
```

```{seealso}
How these numbers were checked against references that do not depend on ARGOS
(Siril, astropy, the VSP catalogue, the frames' own noise, the AAVSO format), and
what was not checked: {doc}`validation`. Every formula below carries a citation;
the full list, with links, is in {doc}`references`. Every constant is a
configuration key, gathered in {ref}`§11 <all-parameters>`.
```

## 1. The measurement grid: the green plane

Every geometric and photometric quantity is defined on one grid, so a pixel in
the astrometric solution is the same pixel that is measured.

The sensor is a colour (CFA) detector with a `GRBG` Bayer pattern. ARGOS forms
the **green plane** as the per-tile average of the two green samples
({mod}`argos.core.imaging.green`, `green_plane`):

$$
G(i, j) = \tfrac{1}{2}\left[\,\text{raw}(2i,\,2j) + \text{raw}(2i{+}1,\,2j{+}1)\,\right]
$$

The plane has shape $(H/2,\ W/2)$; odd dimensions are cropped by one row or
column so the two greens line up. Green is used because it is the densest
sampling of the Bayer mosaic and therefore the best signal-to-noise channel for
stars. On the S30 Pro the raw values are 12-bit data scaled by 16 into the 16-bit
file (99.92 % of the raw values of three nights are multiples of 16: S73), so the
green plane steps by 8 ADU; §3.2 says why that matters.

```{note}
One green pixel spans two raw pixels. The saved frames carry no astrometric
solution at all, no WCS and no plate-scale keyword (see {doc}`fits_headers`).
```

Averaging the two greens is not free. It broadens the effective PSF by up to
half a green pixel — about 3.7″ on an S30 Pro — and it bakes in any G1/G2
response imbalance, a common CMOS artefact. Both are accepted in exchange for
$\sqrt{2}$ in signal-to-noise and a grid that lines up exactly with the
astrometric solution.

Two consequences matter scientifically:

- The green plane is **not** a photometric $V$ band. It is an instrumental
  passband, recorded as `TG` — the AAVSO code for an untransformed green
  channel, defined in the [DSLR Observing
  Manual](https://www.aavso.org/dslr-observing-manual). Do not report it as $V$.
- Interpolated debayering is never used for measurement. Debayer mode, stretch
  and channel selection are display settings; the data pipeline reads the CFA
  array.

## 2. Astrometry and the aperture tracker

Plate solving is delegated to ASTAP, which solves the green plane and returns a
WCS. The WCS is what makes identification possible: catalogue positions
(Gaia DR3, AAVSO VSX, SIMBAD, the NASA Exoplanet Archive, AAVSO VSP) are
projected into pixel coordinates, and a click on a star is projected back to
$(\alpha, \delta)$. ARGOS measures no astrometry of its own (it fits no position,
proper motion or parallax; the motions below are Gaia's): the solution answers
"which star is this?" and "where is my aperture?".

**Each star at the frame's date.** Catalogue positions are J2000.0. A star of the
target set that has a Gaia DR3 match carries its proper motion, and every
aperture is placed at the star's position on the frame's date (S77): Gaia DR3
gives the motion, VSX and VSP give none. A VSX or VSP star with an AUID takes a
Gaia source whose J2000.0 or 2016.0 position lies within 1″ of the catalogue's,
or, for a star with a catalogue $V$, the one source within 6″ whose $G$ is within
1 mag of $V$ with no other source there within 2.5 mag. On RR Lyr (0.224″/yr)
the aperture centre moved from 0.99 to 0.077 green px of the star (median,
195 frames; {doc}`validation` §7).

**Between two solutions, a tracker.** A solution is only valid at the instant it
was made: on an alt-azimuth mount the field rotates, and any mount drifts.
ARGOS does not model the rotation; it measures it
({mod}`argos.core.photometry.tracking`, `ApertureTracker`). On every frame it
centroids a few **anchor** stars around their predicted positions, fits the rigid
transform (rotation and translation, no scale) that maps their positions through
the solution onto the measured ones, and places every aperture through the
solution moved by that transform. Live, on a mount in equatorial mode the fit is
a translation only.

- **Anchors** are comparisons and check stars seen at SNR ≥ 10, unsaturated and
  without a hot pixel, at most 6, chosen on the frame the solution was solved on.
  A star with a star of the set holding a quarter of its core flux or more within
  the search radius plus 8 green px is no anchor (S69): a centroid climbs onto a
  bright neighbour. The search radius is $\max(8, 2 \times 7.5) = 15$ green px.
- **Centroids** are re-centred on themselves until they move less than 0.01 px,
  then refined in a 4 px window (S69); a single centroid kept 30-80 % of the
  prediction's error and lagged a fast-turning field by about 1°.
- **Inconsistent anchors** are rejected before the fit: a rigid motion keeps
  distances, so of $n$ matched anchors one is kept only if its separations from
  at least $\max(1, \lfloor (n-1)/2 \rfloor)$ of the others match the solution's
  within 1.5 green px; two anchors that disagree are both dropped
  (`consistent_pairs`, S80); a residual clip follows.

The gates below refuse a point, flag it *suspect* or ask for a new solution. Their
thresholds are the owner's decisions, recorded in the S entries named; the code is
the core's tracker and its callers (`argos/core/session/acquisition_engine.py`,
`argos/workers/photometry_batch_worker.py`) and their server ports
(`argos/server/photometry.py`, `argos/server/rerun.py`), which write the same bytes
({doc}`validation` §9).

| Gate | Rule | Effect |
|---|---|---|
| No anchor seen (S35) | no star of the set at SNR ≥ 5 where the solution places it | live: no point for that frame |
| Lock lost (S48, S43) | fewer than $\lceil n/2 \rceil$ of the $n$ anchors seen at SNR ≥ 5 after the tracker's update | live: no point, a solve due at once; re-run: the frame re-solved, else its points flagged *suspect* |
| Few anchors (S56, S58) | fewer than 3 anchors centred within 1 px | verified only through a solution of this frame or the previous one, with the tracker moved less than 10 green px since it; else re-solved, else *suspect* |
| Rotation (S69 a) | the tracked rotation since the solution exceeds 2° | a solve is due; retried only after 2° more |
| Off-centre (S69 b) | a comparison or check star seen at SNR ≥ 5 whose centroid is more than 1 green px from its aperture centre | left out of that frame's ensemble; its own row *suspect* |
| Plate scale (S50, S55) | a new solution more than 1 % from the session's scale | refused; three solutions agreeing within 0.3 % move the reference |
| Anchor confirmation (S54) | a new solution that shows fewer than $\lceil k/2 \rceil$ of the tracker's $k$ anchors | refused; three refused solutions agreeing within 20 green px are taken as a re-pointing |

A star fainter than SNR 5 is not tested for centring: its centroid scatters by
about $1.6/\text{SNR}$ px per axis, so the 1 px test would reject it on noise.

## 3. Aperture photometry

Implemented in {mod}`argos.core.photometry.aperture`.

### 3.1 Geometry

The aperture radius adapts to the seeing:

$$
r_\text{ap} = \max\left(r_\text{min},\ k \cdot \text{FWHM}\right)
$$

with $k = 2.5$ and $r_\text{min} = 4$ green px by default. The sky annulus has
default radii $r_\text{in} = 8$ and $r_\text{out} = 12$ green px, constrained so
that the annulus never touches the aperture
({mod}`argos.core.photometry.params`, `measure_frame`):

$$
r_\text{in} \ge r_\text{ap} + 1, \qquad r_\text{out} \ge r_\text{in} + 2
$$

**One aperture per series.** The FWHM is measured once and held for the whole
series: live, on the first frame measured for that object (S31); in a batch
re-run, on its first readable frame. The four geometry settings cannot be
changed while a sequence runs (S15). Only when no star is detected does the
FWHM fall back to 3.0 green px, which gives
$\max(4,\ 2.5 \times 3.0) = 7.5$ px: the fallback does **not** land on
$r_\text{min}$. On the three study nights the aperture was 5.3-5.5 green px
(FWHM about 2.1-2.2 green px; release notes S69, S75).

```{warning}
**A live curve and a re-run of the same frames can use different apertures.**
Each measures its own FWHM on its own first frame, and the two estimates can
differ; the re-run's flight recorder names the aperture it used. Do not overlay
a live curve and a re-measured one and read their difference as astrophysics.
```

An aperture or a sky annulus that is not wholly on the frame is not measured
(S81): every pixel centre within $r_\text{out}$ of the star must lie on the
frame. Before 0.5.0 a truncated aperture was measured and written as a good
point, up to 5 mag faint.

### Aperture size on the sky

The radii above are in **green-plane pixels**, each spanning two raw pixels.
In angular terms, for the shipped profiles (nominal scale
$206.265 \times \text{pixel}/\text{focal length}$, 2.9 µm pixels):

| Profile | ″ / green px | $r_\text{ap}$ = 4 px | 5.4 px (study nights) | fallback 7.5 px | annulus 8–12 px |
|---|---|---|---|---|---|
| S30 Pro (160 mm) | 7.48 | 29.9″ | **40.4″** | 56.1″ | 60–90″ |
| S30 (150 mm) | 7.98 | 31.9″ | 43.1″ | 59.8″ | 64–96″ |
| S50 (250 mm) | 4.79 | 19.1″ | 25.8″ | 35.9″ | 38–57″ |

```{admonition} A 40-arcsecond aperture is enormous — check for neighbours
:class: warning

This is the error source least visible on screen and most likely to ruin a
curve. At 30-40″ radius, any field within ~20° of the galactic plane will put a
second star inside somebody's aperture, and several inside the sky annulus.

A blended companion is *mostly* harmless while the seeing is constant: it adds
a fixed offset that differential photometry absorbs. It stops being harmless the
moment the FWHM changes, because the fraction of the companion's light inside
the aperture then changes too — producing a variation correlated with seeing
that looks exactly like astrophysics.

ARGOS names one case for you (S79): a comparison or check star with a brighter
star of the set, or a variable, within 2 aperture radii is reported as
**crowded**, in the log and in the target set, and is kept: the observer decides.
Stars outside the set (field stars) are not tested. Before assigning a role,
zoom in and look at the aperture circle.
```

**Why 2.5 × FWHM?** It is not the signal-to-noise optimum, which sits nearer
1×FWHM ([Howell 1989](https://doi.org/10.1086/132477); optimal extraction in
[Naylor 1998](https://doi.org/10.1046/j.1365-8711.1998.01314.x)). A wide
aperture is chosen deliberately: it captures essentially all of the flux, so the
measurement is insensitive to seeing-dependent aperture losses — which is what
matters when you are differencing frames taken over hours. The price is sky
noise and blending, paid knowingly.

### 3.2 Sky and flux

The sky level $\tilde{s}$ is the **3σ-clipped mean** of the annulus pixels
(S76, `sky_level`): pixels farther than three standard deviations from the median
are rejected, and the clip is repeated on what is kept until it rejects nothing (at
most 10 passes), as photutils' `ApertureStats` and astropy's
`sigma_clipped_stats(sigma=3, maxiters=10)` do. The clip rejects a star or a hot
pixel that falls in the annulus, as the median did; the median itself is not used
because the green plane steps by 8 ADU, so it lands on a 4-8 ADU grid, an error of
about 2 ADU per pixel in no error term (before 0.5.0 the sky was that median).
With $n_\text{pix}$ pixels inside the aperture,

$$
F = \sum_{(i,j)\,\in\,\text{ap}} I(i,j) \;-\; n_\text{pix}\,\tilde{s}
$$

in ADU.

### 3.3 Noise

The uncertainty is the CCD equation, evaluated in electrons. Since 0.5.0 the
default model (`photometry.noise_model`: `green_plane`) is the one of the plane
ARGOS measures: each value of the (G1+G2)/2 green plane holds two raw pixels'
electrons, so its gain is $2g$ (e⁻/ADU, $g$ that of one raw pixel) and it carries
two pixels' read noise $R$ (e⁻ RMS per raw pixel; $R/\sqrt{2}$ on the scale of
one raw pixel, as the averaged value); and only the sky level above the camera's
black level $b$ (the telescope profile's, 1024 ADU on the S30 Pro) is photons.
With $F_e = 2g F$, $s_e = 2g(\tilde{s} - b)$, $n$ aperture pixels and
$n_\text{ann}$ annulus pixels kept by the sky clip, in electrons of the plane
(`measure_aperture`, `_pixel_variance_e`):

$$
\sigma_F^2 = F_e + n\left(1 + \frac{n}{n_\text{ann}}\right)
\left(s_e + 2R^2\right)
$$

The terms are the star's photon noise, then the sky photon noise and the read
noise over the aperture, each enlarged by the error of the sky level subtracted
from it: the clipped mean of the $n_\text{ann}$ annulus pixels the clip keeps
(S75, S76).
The signal-to-noise ratio is $\text{SNR} = F_e / \sigma_F$, the one every gate
reads. The instrumental magnitude's error then adds the star's scintillation in
quadrature (S74):

$$
\sigma_\text{scint}^2 = 10^{-5}\, C_Y^2\, D^{-4/3}\, t^{-1}\, X^{3}\, e^{-2h/8000\,\text{m}}
$$

a relative flux error, with Osborn et al.'s $C_Y = 1.5$, the telescope's aperture
$D$ (m; 30 mm on the S30 Pro), the exposure $t$ (s), the airmass $X$ (each star's
own in a re-run; live and in Open FITS, the frame's, within 1 % of each star's own
across the field: S74) and
the site's height $h$ (the frame's `SITEELEV`, else the Settings site's, else sea
level) ({mod}`argos.core.photometry.uncertainty`, `scintillation_sigma`). It is
0.017 mag in 10 s at airmass 1 at sea level. The SNR does not include it. Without an
exposure time or an airmass the term is 0, and the log says so once.

The model's sky σ matches the σ measured in the annuli of the owner's frames
within 4 % (0.960-1.039 on 31 frames at gains 80 and 100; 0.883 on the one frame at
gain 65, where read noise dominates). A 30 mm aperture sits near the Fresnel scale,
where $C_Y$ is least certain: the bright RR Lyr star pairs measure 1.1-1.4, so bright
stars' errors (and AAVSO `MERR`) are on the safe side ({doc}`validation` §5-§6).
`photometry.noise_model`: `pixel` keeps the 0.4.x formula (one raw pixel's gain,
the whole sky level as photons, neither term), for comparison only: with the
measured $g$ it counts the black level as photons and gives 2.5-3.5 times the real
sky noise.

```{admonition} Source — the CCD equation, scintillation
:class: seealso

Merline & Howell (1995); Howell, *Handbook of CCD Astronomy* (2006); Young (1967);
Osborn et al. (2015, MNRAS 452, 1707). Full citations in {doc}`references`.

Two terms of a calibrated reduction are still absent. **Dark current** is never
measured: its *signal* is absorbed into the annulus' sky level and subtracted with
the sky, but its *shot noise* is not counted — small on short uncooled
sub-exposures against a bright sky. **Faint stars** bias the sky slightly low even
after the clip (the clip, and the median it replaced, leave out their brightest
pixels, which an aperture still sums), so blank apertures read slightly positive (on
RR Lyr 2026-09-25, +10 ± 6 ADU per aperture with the clipped mean, +28 ± 8 with the
median; {doc}`validation` §5).
```

```{admonition} Where does $g$ come from — and when is it wrong?
:class: important

ARGOS resolves the electron gain at the frame's own gain setting (S73, S83), in
order ({mod}`argos.core.hardware.egain`):

1. the `camera.egain_table` entry for that gain;
2. your own photon-transfer file's entry at that gain (`camera_calibration*.json`,
   Settings › Instrument › Photon-transfer calibrations), with its `rdnoise` as the
   read noise: a measurement of your camera beats one made on another unit;
3. the telescope profile's photon-transfer measurement: the S30 Pro's
   0.228 ± 0.005 e⁻/ADU at gain 80 (read noise 2.6 e⁻), scaled at 0.1 dB per gain
   step over gains 0-251 (checked at gain 100: 0.183 measured, 0.181 scaled; any
   other scaled gain is logged "scaled, not measured"); a scaled gain uses the
   measured read noise too;
4. the driver's `ElectronsPerADU`;
5. the sensor reference curve.

That value is what goes into `EGAIN` in the FITS header, with its source in the
comment, and the measured read noise into `RDNOISE`. A **saved frame**, opened
with **Open FITS image…** or re-measured with **Re-run photometry…**, takes the
same order at its own `GAIN`: an S30 Pro frame of 0.4.x at gain 80, whose `EGAIN`
says 0.8 (the driver) or 1.723 (the reference), takes the measured 0.228 (or your
file's value at that gain); an `EGAIN` your table or your file wrote is kept. The
flight recorder's `frame` record names the value and its source.

The 0.228 is the photon transfer of **one** S30 Pro over three nights. Another unit
of the same model may differ; your own photon-transfer file (step 2) is how to say
so. The S30 and S50 profiles carry no measurement and no black level (unvalidated
profiles).

:::{admonition} Before 0.5.0
:class: warning

0.4.x used the frame's `EGAIN` (0.8 or 1.723 e⁻/ADU on the S30 Pro at gain 80):
its Poisson errors were 1.9-2.7 times too small, and each SNR gate read another
SNR (an "SNR 10" was about 7.6 on 0.4.1 frames). Before 0.4.2 the offline path
fell back to 1.0 e⁻/ADU. Re-measure those runs with **Re-run photometry…** for
errors from the camera's measured noise ({doc}`validation` §6).
:::
```

```{admonition} The read noise
:class: note

With the green-plane model, the read noise is the one measured with the e⁻/ADU
(your photon-transfer file's `rdnoise` at that gain; else 2.6 e⁻ on the S30 Pro,
the ADC's quantisation included, wherever the profile gives the gain); elsewhere
`photometry.read_noise_e` (1.5 e⁻ by default), also for a file entry without
`rdnoise` (logged once: give your file both). The `pixel` model always uses the
setting. The noise model, the read noise, the electron gain table and the
photon-transfer folder cannot be changed while a sequence runs (S84), as the
aperture geometry (S15): one curve keeps one error model. Two inputs are not
locked: an edit of the photon-transfer *file* itself during a run applies from the
next frame, and `site.elevation` (the scintillation's $h$) is read on every frame.
```

### 3.4 Instrumental magnitude

$$
m_\text{inst} = -2.5 \log_{10} F
$$

undefined for $F \le 0$, which is reported as a missing measurement rather than
silently clamped. Its uncertainty follows from differentiating the logarithm,
with the scintillation of §3.3 in quadrature:

$$
\sigma_{m} = \frac{2.5}{\ln 10}\sqrt{\left(\frac{\sigma_F}{F_e}\right)^{2} + \sigma_\text{scint}^{2}}
\simeq 1.0857\,\sqrt{\left(\frac{\sigma_F}{F_e}\right)^{2} + \sigma_\text{scint}^{2}}
$$

### 3.5 Flags, and exactly what they do

**Saturation.** Any aperture pixel at or above `camera.linearity_max_adu`
(50 000 ADU by default) flags the measurement *saturated*.

```{admonition} What the 50 000 ADU threshold is, and is not
:class: warning

On the S30 Pro the file's values are 12-bit counts × 16, so the ADC's full scale
is $4095 \times 16 = 65\,520$ ADU and the threshold sits at 76 % of it. With the
measured e⁻/ADU (§3.3) it is about 11 400 e⁻ at gain 80 ($0.228 \times 50\,000$),
below the IMX585's 38 000 e⁻ full well; at gain 0 the scaled 0.573 e⁻/ADU puts the
12-bit full scale at 37 600 e⁻, about the full well (S73). So, with the measured
and scaled e⁻/ADU, the ADC and not the well clips first at every gain from 0 to
251 on this camera, and the flag fires before either. What the threshold is **not** is a measured linearity limit: the
sensor's response near 50 000 ADU was never measured. Judge a bright star from the
peak ADU against your own flats as well. (Before 0.5.0 this page called the
threshold "not reconciled" with `EGAIN` and `FULLWELL`: that came from the wrong
`EGAIN` values of S73.)
```

A second limitation: saturation is tested on the **averaged** green plane
$(G_1{+}G_2)/2$, so a star that saturates one green sample but not the other can
average below the threshold and escape the flag.

**Missing PSF support.** A real star spreads over neighbouring pixels; a hot
pixel or a cosmic-ray hit does not. When the brightest aperture pixel exceeds
the sky by more than $10\sigma_\text{sky}$ while its four neighbours average
less than 10 % of that excess, the point is marked *suspect*. Since the live
curve measures raw subs, an uncorrected hot pixel drifting through an aperture
would otherwise paint a convincing artificial dip with nothing to point at.
($\sigma_\text{sky}$ here is the annulus **standard deviation** before any
clipping, while the sky level is its clipped mean. A star sitting in the annulus
inflates that σ and makes the test fire less often — the threshold is more
conservative than it looks.)

**The other reasons a point is *suspect*** (each in its section): a tracker lock
that could not be verified (§2: S43, S56, S58), a comparison or check star off its
aperture centre (§2: S69), a dominant comparison its ensemble contradicts (§4.1:
S71), and a target without a detection (§5: S67, S85). A target point without a
detection is also marked `no_detection`.

```{admonition} What the flags actually gate — read this before trusting them
:class: warning

No flag removes a point from the curve or from its CSV. Both are recorded; only
some of them act.

| | *saturated* | *suspect* (hot pixel) |
|---|---|---|
| Excludes a **comparison** from the magnitude zero point | yes | **no** |
| Excludes a **comparison** from the relative-flux sum | yes | yes |
| Excludes it from automatic selection and from tracking anchors | yes | yes |
| Removes a flagged **target** point from the curve | **no** | **no** |
| Appears as a column in the curve CSV | yes | yes |
| Leaves a **target** point out of the AAVSO export | yes | yes |

An off-centre comparison (S69) leaves both ensembles for that frame. A
comparison flagged only for a hot pixel still contributes to the magnitude
ensemble, and a *suspect* target point is still measured, plotted (hollow in
Review) and written to the CSV. The AAVSO export leaves every flagged target
point out and says how many; a flagged check point never provides `KMAG`.
Filtering the CSV is still your decision, not ARGOS's.
```

## 4. The comparison ensemble

Implemented in {mod}`argos.core.photometry.differential` and
{mod}`argos.core.photometry.session`.

### 4.1 Zero point

Each comparison star $k$ contributes the difference between its catalogue
magnitude and its instrumental magnitude, with an error $\sigma_k$ that is its
instrumental error of §3.4 (scintillation included) with a 10 mmag floor
(`ensemble_zero_point`, S71):

$$
d_k = m_{\text{cat},k} - m_{\text{inst},k}, \qquad
\sigma_k^2 = \sigma_{m,k}^2 + (0.01\ \text{mag})^2, \qquad
w_k = 1/\sigma_k^2
$$

The zero point is their inverse-variance weighted mean, and its error is the
larger of the ensemble's photon error and its measured scatter:

$$
\text{ZP} = \frac{\sum_k w_k d_k}{\sum_k w_k}, \qquad
\sigma_\text{ZP} = \max\left(\sqrt{\frac{1}{\sum_k w_k}},\ \frac{\text{rms}_w}{\sqrt{n}}\right),
\qquad
\text{rms}_w = \sqrt{\frac{n}{n-1}\,\frac{\sum_k w_k (d_k - \text{ZP})^2}{\sum_k w_k}}
$$

The floor keeps one bright star from taking all the weight. Before 0.5.0 the zero
point was the plain mean: a comparison at SNR 1 counted as much as one at SNR 100
(XX Cyg 2026-08-29: its check star came out +0.28 ± 0.08 mag from its VSP $V$;
with the weights, and the rest of 0.5.0, +0.044 ± 0.020: S71, {doc}`validation`
§4.2).

Which comparisons enter it, on each frame: those with a catalogue magnitude in the
band, measured, not saturated and not off-centre (§2). The check star is never in
it: it is calibrated against the full ensemble, like the target, so a flat check
curve can certify the night. Each comparison is also calibrated against the
ensemble without itself (leave-one-out), for §6 only.

With a single comparison, $\text{rms}_w$ is 0 and $\sigma_\text{ZP}$ is that star's
own error with its floor: nothing measures whether that star is right. Never read a
one-comparison error bar as a check of the comparison. With few comparisons the
scatter branch is itself uncertain: on $n = 3$, $\text{rms}_w$ is uncertain by
roughly 50 % ($1/\sqrt{2(n-1)}$ for Gaussian errors).

**A dominant comparison.** Centred on the weighted median (§4.2), the clip never
drops a comparison that holds more than half the weight. When one does and at
least two others remain, its $d$ is compared with the weighted mean of the others;
beyond 2.5 combined σ the point is flagged *suspect* ("the comparison holding N % of
the weight disagrees with the others"), and the zero point is kept as computed
(`dominant_disagreement`, S71). Review warns when the comparisons' median SNR over a
run is below 10 (`faint_comparisons`): the zero point then rests on the brightest of
them.

```{admonition} The zero point is cross-band, by construction
:class: danger

There is no TG catalogue magnitude. AAVSO VSP sequences publish B, V, Rc and Ic;
ARGOS measures an untransformed green instrumental magnitude. So when the band
requested (`photometry.default_band`, `TG` by default) is not in the sequence,
the code falls back to **V** (`session._cat_mag`), and every zero point is a
weighted mean of

$$
V_\text{cat} - \text{TG}_\text{inst}
$$

This is the accepted practice for untransformed green photometry — it is what
`TG` *means*, and it is why the AAVSO defines the code. But it makes a colour
term the dominant systematic of the whole method, and it is not optional or
occasional: it is on every frame.

**The practical consequence.** Any difference in colour between your target and
your ensemble propagates straight into the differential magnitude, and its size
changes with airmass — so a red target against a blue ensemble drifts through
the night in a way that looks like variability. VSP publishes B and V for every
sequence star, so you can compute $B-V$: **match the ensemble's mean colour to
the target within roughly 0.3 mag in $B-V$** and this mostly goes away. ARGOS
does not choose for you: the Field band lists each candidate's $B-V$ and its
difference from the target's, and marks it "colour" when that difference exceeds
0.3 mag (a rule of thumb, not a measured limit); neither the ensemble nor the
zero point corrects for colour.
```

```{note}
The idea of an *ensemble* zero point rather than a single comparison is
Honeycutt's (1992). ARGOS does not implement his method: Honeycutt solves one
global least-squares system across a whole inhomogeneous set of exposures, while
ARGOS forms a clipped weighted mean independently on each frame — which is what a
live preview can do, frame by frame, with no knowledge of the frames still to come.
```

### 4.2 Robust rejection

With three or more comparisons, outliers are clipped about the **weighted
median** of the $d_k$ (the value with half the total weight on either side), each
in units of its own error:

$$
\left|d_k - \operatorname{wmed}(d)\right| \;>\; 2.5\,\sigma_k
$$

At most two passes run, and clipping stops if fewer than two comparisons would
remain. A median rather than a mean, because in a small ensemble a single bad
comparison drags the mean toward itself; the *weighted* median, because with
comparisons of very unequal errors the plain median sits among the noisy faint
ones and clips the one bright star that carries the zero point (XX Cyg 2026-08-29:
13 of 22 frames with the plain median; S71). The 10 mmag floor in $\sigma_k$ keeps
photon noise alone from rejecting a good comparison when the ensemble is
near-identical. Before 0.5.0 the clip was $\max(2.5 \times 1.4826\,\text{MAD},
0.01)$ about the plain median.

### 4.3 Differential magnitude

$$
m = m_{\text{inst,target}} + \text{ZP}
$$

with the formal uncertainty combining the target's own error (§3.4, scintillation
included) and the zero point's error:

$$
\sigma_\text{formal} = \sqrt{\sigma_{m,\text{target}}^{2} + \sigma_\text{ZP}^{2}}
$$

Fewer than `photometry.min_comparisons` (2 by default) kept comparisons does not
suppress the measurement; it annotates it. A curve built on one comparison star
is still shown, and still labelled as such.

### 4.4 Relative flux, for transits

A transit needs no catalogue magnitudes — only a stable ratio. ARGOS therefore
also computes

$$
\rho = \frac{F_\text{target}}{\sum_k F_{\text{comp},k}}
$$

against the **sum** of the comparison fluxes, which has the correct ratio
statistics. Propagating fractional errors,

$$
\frac{\sigma_\rho}{\rho} = \sqrt{
  \left(\frac{1}{\text{SNR}_\text{target}}\right)^{2} +
  \frac{\sum_k \left(F_k/\text{SNR}_k\right)^{2}}{\left(\sum_k F_k\right)^{2}}
}
$$

This error holds no scintillation: the SNR of §3.3 does not include it.

```{important}
Two different weightings are in play, and they are not equivalent. The zero
point of §4.1 weighs each comparison by $1/(\sigma_m^2 + 0.01^2)$, so no single
star carries more than its floor allows; the ratio $\rho$ is a **sum of fluxes**,
in which the brightest comparison dominates and a *suspect* comparison is left
out. If the two paths disagree on a night, look first at the brightest comparison.
```

$\rho$ as computed is deliberately **not** normalised to an out-of-transit
baseline and **not** detrended: both are post-processing decisions that depend
on the baseline you actually observed.

```{warning}
The **Relative flux** view of the light-curve plots (key M) does normalise — to
the median of the series shown, saturated points left out (before 0.5.0 they were
included). That is a *display* convenience and it has a failure mode: if most of
your run is in transit, the median sits inside the event, the baseline is pulled
down and the depth looks shallower than it is. Judge depth from an exported,
un-normalised series with a real out-of-transit baseline.
```

### 4.5 Automatic selection

When a target is chosen and the ensemble is still empty, ARGOS proposes up to
five comparisons from the AAVSO VSP sequence
({mod}`argos.core.catalog.photometry`, `auto_comparison_stars`). A star outside
the frame is dropped. Each candidate is measured on a pilot frame and must pass
every gate:

- not saturated, and not flagged *suspect* by the PSF-support test of §3.5;
- SNR $\ge 10$ on that pilot frame;
- **instrumental** magnitude within 1.5 mag of the target's — measured on the
  same frame, not compared through catalogue magnitudes, so the gate is about
  landing in the same part of the detector's response;
- separation under 25 arcmin.

The separation limit is deliberate — across a very wide raw field, remote
references are vulnerable to flat-field residuals and differential tracking
error, and a small validated ensemble beats a large scattered one.

Candidates that clear every gate are then **ranked**, and the ranking is not
what the gates suggest:

$$
\text{score} = 0.50\,S_\text{SNR} + 0.40\,S_{\Delta m} + 0.10\,S_\text{dist}
$$

with $S_\text{SNR} = \min(\text{SNR}/\max(20, 2\,\text{SNR}_\text{min}), 1)$,
$S_{\Delta m} = 1 - \Delta m_\text{inst}/\Delta m_\text{max}$ and
$S_\text{dist} = 1 - \theta/120'$. Because that last term is normalised over
120′ while the hard cut is at 25′, distance contributes at most 0.02 of the
final score inside the allowed region — proximity is essentially not a
criterion. Signal-to-noise and brightness match are. If a pilot measurement is
unavailable the code falls back to nearest-first instead.

A manually clicked star is never replaced by this proposal. It is kept, but
because it has no AUID and no catalogue magnitude it cannot contribute a zero
point, so ARGOS complements it rather than leaving the target unusable.

## 5. The run-level systematic floor

Implemented in {mod}`argos.core.photometry.uncertainty`. This is the part that
measures what the error model of §3-§4 misses.

The formal error counts photons, the sky estimate, scintillation and the zero
point's error. It does not count guiding jitter, aperture losses, flat-field
residuals, differential extinction or focus drift. With the 0.4.x model, the RR Lyr
star pairs of 2026-09-25 scattered 1.9-2.3 times their formal errors (median over
the pairs of each comparison set); with 0.5.0's, the pairs of the study runs scatter
0.86-1.12 times theirs ({doc}`validation` §6), and the floor below is often 0. It is
still estimated: it catches what the model misses.

ARGOS measures the real scatter instead of assuming it, using **second
differences**. For independent errors,

$$
\operatorname{Var}\left(m_{i-1} - 2m_i + m_{i+1}\right) = 6\,\sigma^{2}
$$

so a robust estimate of the per-point scatter is

$$
\sigma_\text{real} = \frac{1.4826\,\operatorname{MAD}\left(m_{i-1} - 2m_i + m_{i+1}\right)}{\sqrt{6}}
$$

The second difference is what makes this work on a *variable* star: it removes
any locally linear trend, so the intrinsic variation of the target does not
inflate the noise estimate. Estimating a variance from successive differences
rather than from residuals about a fitted model goes back to
[von Neumann (1941)](https://doi.org/10.1214/aoms/1177731677).

```{admonition} What this estimator can and cannot see
:class: danger

Differencing is a high-pass filter, and that cuts both ways. A component
varying on a timescale $T$ much longer than the cadence $\Delta t$ is suppressed
by roughly $(\Delta t / T)^2$ — which is exactly why the target's own
variability does not contaminate it, and exactly why **it cannot measure the
slow systematics listed above**.

- **Captured:** scintillation (white above ~1 s), frame-to-frame guiding jitter,
  aperture-loss noise, photon noise — everything varying frame to frame.
- **Not captured:** flat-field residuals as the field rotates, differential
  extinction, colour × airmass, focus drift — everything varying over the night.

$\sigma_\text{real}$ is therefore a **high-frequency** scatter, and
$\sigma_\text{sys}$ is the white excess over the formal error, not a measurement
of "scintillation plus flat-field plus tracking". For anything you measure over
a long baseline — a transit depth above all — the relevant uncertainty is set by
correlated red noise on that timescale, which this number does not contain and
will underestimate. Bin your residuals and watch whether the RMS falls as
$1/\sqrt{N}$; where it stops falling is your real floor
([Pont, Zucker & Queloz 2006](https://doi.org/10.1111/j.1365-2966.2006.11012.x)).

And because it comes from a MAD on a few tens of points, $\sigma_\text{real}$ is
itself uncertain: about ±47 % with 10 points (the fewest the estimate accepts),
±32 % with 20 and ±26 % with 30 (a simulation of this estimator on white noise,
20 000 runs, {doc}`validation` §6). On a short run the floor is a rough number.
```

The systematic term is what the observed scatter has in excess of the formal
errors, and the final uncertainty adds it in quadrature:

$$
\sigma_\text{sys} = \sqrt{\max\left(0,\ \sigma_\text{real}^{2} - \operatorname{med}(\sigma_\text{formal})^{2}\right)},
\qquad
\sigma_\text{final} = \sqrt{\sigma_\text{formal}^{2} + \sigma_\text{sys}^{2}}
$$

Each point keeps its own formal error, so a genuinely noisy frame stays noisier
than its neighbours; the floor is a run-level addition, not a replacement. It is
estimated per curve (one star, one filter, one run).

At least **ten** valid measurements are needed for the automatic estimate. Below
that, the floor is either taken from `photometry.systematic_floor_mag` or omitted
entirely, and the curve shows formal errors only.

**Points without a detection.** A target measured below SNR 3 on a frame holds no
detection there (clouds over it, or a field that moved): its point is kept, flagged
*suspect* and `no_detection`, left out of the estimate, and its own error still takes
the floor. The live curve applies this as each point is measured (S85); a re-run and
Review apply it from the run's frames and flight recorder (S67), together with a
frame-wide rule the live curve cannot apply while the run goes on (a target's zero
point more than 1 mag from its median over the run flags every star of that frame;
`review.NO_DETECTION_SNR`, `ZP_OUTLIER_MAG`). Review can apply these rules to a
recorded run only if its flight recorder was on (**Settings › Privacy &
diagnostics**, off by default); a re-run applies them to the frames it measures
whether or not it records them.
Live, the points without a detection are the only ones left out of the estimate.
A re-run also leaves out the points measured without a verified field (S43, S58)
and the off-centre rows (S69). Saturated points and the other *suspect* points are
kept in it.

```{admonition} The same floor as star_var_script — not the same error bars
:class: note

The floor estimator is `star_var_script`'s: robust second differences over
$\sqrt{6}$, the median formal error, at least ten points, the floor added in
quadrature (its `pipeline.py`, `estimate_lightcurve_scatter` and
`apply_error_floor`). The formal errors it is added to differ: ARGOS's hold
scintillation and the zero point's error, Siril's are its own photometric errors.
So the two floors measure different excesses and are not the same number for the
same night; compare the final errors, not the floors.
```

## 6. Is the ensemble any good? The leave-one-out check

Implemented in {mod}`argos.core.photometry.quality`.

A bad reference star poisons every point of the night, and it does so silently:
the target curve simply moves. ARGOS therefore assesses each comparison against
the others, without changing anything the observer selected.

The insight is that the work is already done. Every comparison star is itself
measured differentially against the *other* comparisons — a leave-one-out curve.
If that curve is not flat, something in the ensemble is wrong.

```{warning}
**The test detects, it does not localise** — not with the ensemble sizes ARGOS
works with. With three to five comparisons, one bad star sits in the reference
set of every *other* star's leave-one-out curve, so it makes all of them wander.
A single red flag usually means "this ensemble has a problem", not "this star is
the problem". Localisation needs an ensemble large enough that each
leave-one-out subset is still dominated by good stars.

What to do with a flagged ensemble: drop the worst offender, let the assessment
re-run, and see whether the others go quiet. If they do, you found it.
```

For each comparison, over its valid points (not saturated, with finite time,
magnitude and error), ARGOS computes the second-difference scatter
$\sigma_\text{real}$ of §5 and the median formal error, then classifies:

| Status | Condition |
|---|---|
| *insufficient data* | fewer valid points than the configured minimum (`photometry.comparison_validation_min_points`, 10 by default), or no scatter estimate |
| **Noisy** | median formal error $> 0.10$ mag — the star is too faint or too poorly measured to judge |
| **Unstable** | scatter $> 0.10$ mag — the star moves relative to the others |
| **Stable** | neither of the above |

The ensemble as a whole is then reported as *insufficient data* while any
comparison is still unassessed, **not ready** while fewer than three
comparisons are stable, and *live-preview consistent* otherwise.

The report is recomputed on every measured frame, in plain live preview as well
as during a sequence, and shown in the **Ensemble** panels of Observe and Review
with the ensemble verdict and its caveat. During a sequence it is also written to
`photometry_quality.json` in the session folder, with the criteria that produced
it and the filter it vets (S57). (Before 0.5.0 it was computed only once a
sequence had saved a frame.)

```{warning}
"Stable" means only that the *live preview* has enough internally consistent
samples. It is not a calibrated-photometry certification. Confirm the ensemble
on registered, calibrated frames in Siril and `star_var_script`.
```

## 7. Time and airmass

Implemented in {mod}`argos.core.photometry.airmass`,
{mod}`argos.core.imaging.sky_geometry` and {mod}`argos.core.session.review`.

**The instant.** A measurement is timed at the **exposure midpoint**, UTC: live,
the exposure's start plus half its duration; for a saved frame (Open FITS image,
a re-run), its `DATE-AVG`, else `DATE-OBS + EXPTIME/2`; for a frame written by
ARGOS before 0.5.0, always `DATE-OBS + EXPTIME/2`, because a 0.4.x sequence frame's
`DATE-AVG` is late by half the image download, seconds over Wi-Fi (S36, S39;
{mod}`argos.core.session.acquisition_engine` `fits_exposure_mid`, ported in
`argos/server/capture.py`). It is converted to a Julian date
with the Fliegel–Van Flandern day number:

$$
\text{JD} = \text{JDN} + \frac{h - 12}{24} + \frac{\text{min}}{1440} + \frac{s}{86400}
$$

The start of an exposure is the computer's clock as ARGOS reads it just before it
tells the camera to start (S36). The offset of that clock from UTC, and the delay
between the command and the start of the Seestar's exposure, were never measured:
the checks of {doc}`validation` §2 test the computation from the header, not the
header's own clock. Keep the computer's clock synchronised.

`BJD_TDB` — the publishable time standard, applying the barycentric
light-travel-time correction for the star's direction from the observing site — is
computed by astropy with its bundled Earth-orientation tables, so it works offline
(S37), for the star's position at the frame's date (S77) and the Settings site.
Without a site there is no `BJD_TDB` (a site at the 0/0 default counts as none: X2).

```{tip}
For **transit timing and long-baseline period work**, report `BJD_TDB` — not
`HJD`, not `JD_UTC`. The difference reaches several seconds for `HJD` and `UTC`
accumulates leap seconds
([Eastman, Siverd & Gaudi 2010](https://doi.org/10.1086/655938)).

For an **AAVSO submission**, `JD_UTC` is what is asked for, and it is what
ARGOS's AAVSO export writes (`#DATE=JD`). Both columns are in the curve CSVs;
use the one your destination expects.
```

**The formula.** Airmass uses the [Pickering (2002)](https://www.dioi.org/vols/wc0.pdf)
formula — better than 0.01 airmass down to 1° altitude, and finite at the horizon
where $\sec z$ diverges:

$$
X = \frac{1}{\sin\!\left(h + \dfrac{244}{165 + 47\,h^{1.1}}\right)}, \qquad h \text{ in degrees}
$$

It is undefined at or below the horizon — the function returns nothing rather
than a large number, so a frame taken through the treetops has no airmass rather
than a fictional one. When ARGOS computes a star's altitude, it precesses the
J2000 position to the date (IAU 1976, S51), then applies the sidereal time;
nutation, aberration and refraction are left out, and the altitude is within 0.01°
of astropy's (without refraction).

**Which airmass a point takes.** The header `AIRMASS` is the mount's: Pickering's
formula on the altitude the mount reports at the exposure start, for the field
centre. Where the Settings site is wrong (a site from an earlier trip), an airmass
computed for it is wrong too, while the mount's is right. So:

- **Review, Open curve CSV and a re-run** (S66, S78): the target takes the header
  `AIRMASS` of the ARGOS light whose mid-exposure is within 5 s of the point,
  whatever the Settings site; a comparison or check star takes its own airmass,
  computed for a site fitted to the lights' pointing (at least 3 pointings over
  10 minutes, rms under 0.1°), else for the Settings site if it reproduces the
  mount's pointing within 0.1°, else the header `AIRMASS`. A point with no such
  light keeps the airmass the run computed, and so does a light whose pointing is
  frozen (its `RA`, `DEC`, `ALTITUDE`, `AZIMUTH` and `AIRMASS` all those of a light
  60 s or more before it: a lost mount's last poll, X1). Files are never rewritten.
- **Live**: every star takes its own airmass for the site fitted to the mount's
  polls; before a fit exists, for the Settings site if it reproduces the mount's
  pointing within 0.1°, else the mount's airmass (S78).
- **The site check** (X3): the Settings site is compared with the mount when it
  connects, and Review warns when, over the run's lights, the direction their
  coordinates give from that site lies more than 5° (median) from the mount's
  altitude and azimuth. A site wrong by less than 5° is not warned; the per-star
  rule above keeps it out of the comparisons' airmass.

On the study runs the targets' airmass is within 0.00044 of astropy at
mid-exposure, and the comparisons' own airmass within 0.00007 on the runs with a
fitted site ({doc}`validation` §3).

```{admonition} Before 0.5.0
:class: warning

0.4.x computed every point's airmass for the Settings site, without precession
(on the owner's runs an airmass 0.004 low at 41° altitude, 0.029 at 12°: S51), and
with no check that the site was right. One of the owner's runs was recorded with a
Settings site 83° from the true one: its CSV airmass and AAVSO `AMASS` were wrong
by up to 3.05 (S66). Review and the AAVSO export now take the header `AIRMASS`;
the CSV files keep what they recorded.
```

## 8. What the exports contain

### 8.1 Curve CSVs

A run writes one CSV per star and filter in its `photometry/` folder;
**Export CSV…** in Review writes the multi-star form, which prefixes `star_id`,
`role`, `name` and `auid` and holds one filter (S61). The columns
({mod}`argos.core.photometry.lightcurve`):

| Column | Unit | Meaning |
|---|---|---|
| `jd_utc` | day | Julian date of the exposure **midpoint**, UTC (§7) |
| `bjd_tdb` | day | Barycentric JD in TDB — empty when the site is unknown |
| `mag` | mag | the differential magnitude of §4.3 |
| `mag_err` | mag | the **final** uncertainty: formal and systematic combined (§5) |
| `formal_mag_err` | mag | the formal error of §4.3, before the floor |
| `sigma_syst` | mag | the run-level systematic floor that was added |
| `airmass` | — | the airmass the point took when it was written (§7); Review and the AAVSO export may take the header `AIRMASS` instead |
| `fwhm` | green px | frame FWHM. **Multiply by 2 for full-resolution pixels**, then by the plate scale for arcsec |
| `sky_adu` | ADU | annulus 3σ-clipped mean for this star on this frame (the median before 0.5.0) |
| `comps_used` | count | comparisons behind `mag` in this row — the zero-point ensemble of §4.1 |
| `relative_flux` | — | $\rho$ of §4.4, un-normalised |
| `relative_flux_err` | — | its propagated error |
| `relative_comps_used` | count | comparisons behind $\rho$ in this row |
| `saturated` | bool | the §3.5 saturation flag |
| `suspect` | bool | any reason of §3.5: a hot pixel, an unverified lock, a star off its aperture centre, a contradicted dominant comparison, a target without a detection |

```{note}
**The two ensemble counts are both here because they genuinely differ.** The
ratio path rejects *suspect* comparisons and the magnitude path does not
(§3.5), so `relative_comps_used` is often smaller than `comps_used` on the same
row. Each count belongs to the quantity beside it: read `comps_used` with
`mag`, `relative_comps_used` with `relative_flux`.
```

A row is written whenever **either** product exists. A frame whose comparisons
were all flagged *suspect* still yields a differential magnitude, so it still
yields a row — with an empty `relative_flux` and `relative_comps_used = 0`.
Only a frame that produced neither a magnitude nor a ratio is dropped.

```{admonition} Before 0.4.2 — check your existing exports
:class: warning

Three of the columns above behaved differently in 0.4.1 and earlier, and none
of the differences were visible from the interface:

- `comps_used` carried the **flux-ratio** count, not the magnitude one. A file
  from 0.4.1 states the wrong ensemble size beside every `mag`.
- There was **no `suspect` column** and no `relative_comps_used`.
- A row was written **only when $\rho$ existed**. A run in which every
  comparison was flagged *suspect* silently lost its magnitudes — no row, no
  note. If an old curve has gaps you never explained, compare its row count
  against the frame count before concluding the star did something.

Re-running the measurement on the saved frames (**Re-run photometry…**)
regenerates the file correctly.
```

### 8.2 The AAVSO report

**Export AAVSO…** writes an AAVSO Extended File (`write_aavso`):

```text
#TYPE=EXTENDED
#OBSCODE=TST01
#SOFTWARE=Argos v0.5.0
#DELIM=,
#DATE=JD
#OBSTYPE=CCD
#NAME,DATE,MAG,MERR,FILT,TRANS,MTYPE,CNAME,CMAG,KNAME,KMAG,AMASS,GROUP,CHART,NOTES
```

(`TST01` stands for your observer code.) One row per target point:

| Field | What ARGOS writes |
|---|---|
| `NAME` | the target's name, upper case |
| `DATE` | `jd_utc`, 6 decimals (0.086 s steps) |
| `MAG`, `MERR` | `mag` and `mag_err` (the systematic floor included), 4 decimals |
| `FILT` | `photometry.default_band`, `TG` by default |
| `TRANS`, `MTYPE` | `NO` (untransformed), `STD` |
| `CNAME`, `CMAG` | `ENSEMBLE`, `na` |
| `KNAME`, `KMAG` | the first check star's AUID (else its name, up to 20 characters) and its magnitude on the same frame; `na`,`na` without a check star or when that frame's check point is flagged (the preview warns when there is no check) |
| `AMASS` | the point's airmass (§7: the target's header `AIRMASS` from Review), 3 decimals |
| `GROUP` | `na` |
| `CHART` | the comparisons' VSP chart, else `na` (S68) |
| `NOTES` | `na` |

The export **refuses** an empty observer code or `XXX` (Settings › Observer & site;
S11) and curves of two filters or more (one band per report, S53). It **leaves out**,
and counts in its message, the saturated and *suspect* target points (the points
without a detection named apart, S67) and any point dated before JD 2 400 000 or
not dated at all (S60). On a run recorded before 0.5.0, the points whose tracking
was checked on fewer than three stars are written, with a warning: re-run the
session first, which verifies those frames with a plate solve (S56, S58). A
flagged check point gives no `KMAG`. Comparison and
check curves are never written as rows. ARGOS writes `#OBSTYPE=CCD` for its CMOS
camera (S68); whether the AAVSO accepts or prefers another code for a CMOS camera
was not checked ({doc}`validation` §8).

## 9. The floor you cannot get under

Atmospheric **scintillation** sets a noise floor that no exposure time and no
photometric skill removes, and it scales as $D^{-2/3}$ in σ — punishing for a
30 mm objective. Since 0.5.0 it is in every star's error (§3.3, S74). With the
code's formula ($C_Y = 1.5$) at a site 200 m high, one star, one frame
(`scintillation_sigma`, values in mmag):

| Telescope | $X$ = 1.0, 20 s | $X$ = 1.5, 20 s | $X$ = 1.5, 60 s | $X$ = 2.0, 20 s |
|---|---|---|---|---|
| S30 / S30 Pro (30 mm) | 12 | **21** | 12 | 33 |
| S50 (50 mm) | 8 | **15** | 9 | 23 |

Read that as: on a 20-second sub at airmass 1.5, an S30 Pro's error carries about
20 mmag per frame *no matter how bright the star*. Scintillation is white on these
timescales and independent between stars more than a few arcseconds apart, so it
does not cancel in the differential and averaging helps: ten frames bring 21 mmag
to about 7. Observing high beats observing long: the $X^{3}$ in the variance costs
more than the exposure term buys.

This is a model, not a measurement of your telescope. One night measures it: the
bright RR Lyr star pairs of 2026-09-25 imply $C_Y$ of 1.1-1.4, so that night's
scintillation was 0.73-0.93 times the table's figures (S74). $C_Y$ varies from site to site and night to
night ([Osborn et al. 2015](https://doi.org/10.1093/mnras/stv1400)); a refit with
more nights is deferred to 0.5.x. Its practical use is as a sanity check: if your
measured scatter on a bright star is far *below* the figure above, suspect that
something is smoothing your data; if it is far above, the limit is not the
atmosphere and is worth chasing.
[Young (1967)](https://doi.org/10.1086/110303).

## 10. Known limits in 0.5.0

- **No calibration.** No dark, flat or bias. Flat-field residuals are the main
  reason the comparison ensemble is kept within 25 arcmin. The alt-az field
  rotation moves the comparisons across the sensor during a run, so a flat-field
  error can appear as a slow trend, which $\sigma_\text{sys}$ does not contain.
  Its size on the Seestar S30 Pro has not been measured. Calibration is planned
  for 0.6, once that effect has been measured with darks and flats.
- **A cross-band zero point.** $V_\text{cat} - \text{TG}_\text{inst}$, with no
  colour transformation (§4.1). This is the largest systematic in the method.
- **Error bars on the safe side for bright stars.** On the study runs the
  formal errors and AAVSO `MERR` of bright stars are 1.3-1.6 times their measured
  scatter, while faint stars are near 1 ({doc}`validation` §6). Three causes:
  $C_Y = 1.5$ (one night measures 1.1-1.4), and the zero point's error, whose
  scatter branch and 10 mmag floor carry the comparisons' constant catalogue
  disagreement into every frame. Splitting the formal error into a random part and
  a per-run calibration part, and refitting $C_Y$ with more nights, are deferred to
  0.5.x.
- **A high-frequency-only systematic floor.** $\sigma_\text{sys}$ does not
  contain red noise (§5), so long-baseline quantities — transit depths above all
  — carry error bars that are too small.
- **One measured camera.** The e⁻/ADU and read noise are those of one S30 Pro,
  measured at gains 80 and 100; other gains are scaled, the gain-65 frame is
  inconclusive, and the S30 and S50 profiles are unvalidated (reference e⁻/ADU, no
  black level).
- **A saturation threshold that is not a measured linearity limit** (§3.5).
- **Wide apertures.** 30-40″ radius on an S30 Pro, with no deblending and no PSF
  fitting (§3.1); crowded comparisons are named, not removed, and field stars
  outside the set are not tested.
- **Times from the computer's clock**, whose offset from UTC ARGOS does not check
  (§7).
- **Inputs read during a run.** An edit of the photon-transfer file, and
  `site.elevation`, apply from the next frame (§3.3).
- **Comparison curves are diagnostics.** The check star exists to expose
  ensemble drift. Never submit a comparison curve as an observation.
- **Not yet used live on a telescope.** The 0.5.0 desktop app was tested with its
  simulator and with replays of real nights; live use on a real Seestar is pending.
- **Checked on little data.** Three nights of one S30 Pro, two targets; XX Cyg has
  no independent reduction ({doc}`validation`).
- **Attended operation.** There is no weather safety and no restart recovery.

```{admonition} What you *can* honestly say
:class: tip

The list above is long, so here is the other side of it, plainly. An ARGOS run
is a legitimate **detection and monitoring** measurement: that a star varied,
by roughly how much, timed from the frame headers to the millisecond (as accurate as the
computer's clock), against
references you have evidence were stable. That is a real observation and worth
recording.

What it is not is a **calibrated** measurement: a transformed magnitude on a
standard scale, or a depth or amplitude quoted to a precision the error bars
here can support. That comes from the reduction, on the raw frames ARGOS kept
for you.
```

The corresponding hand-off is described in {doc}`guide` — copy the whole session
folder before reducing it.

(all-parameters)=
## 11. Every constant on this page

All of them are configuration keys, stored in the JSON config; the photometry
ones are on **Settings › Photometry**, the camera ones on **Settings › Instrument**.
The defaults below are those of 0.5.0.

| Key | Default | Sets |
|---|---|---|
| `photometry.aperture_fwhm_mult` | `2.5` | $k$, the aperture-to-FWHM factor — §3.1 (locked during a run) |
| `photometry.aperture_min_px` | `4` | $r_\text{min}$, the aperture floor in green px — §3.1 (locked during a run) |
| `photometry.annulus_in_px` | `8` | $r_\text{in}$, sky annulus inner radius — §3.1 (locked during a run) |
| `photometry.annulus_out_px` | `12` | $r_\text{out}$, sky annulus outer radius — §3.1 (locked during a run) |
| `photometry.noise_model` | `green_plane` | the noise model of §3.3; `pixel` is the 0.4.x formula, for comparison only (locked during a run) |
| `photometry.read_noise_e` | `1.5` | $R$ in e⁻ RMS when no read noise is measured with the e⁻/ADU — §3.3 (locked during a run) |
| `camera.egain_table` | `{}` (empty) | $g$ in e⁻/ADU per gain setting, first in the order of §3.3 (locked during a run) |
| `data_paths.camera_calibration_directory` | — | the folder of your photon-transfer file, second in that order (locked during a run) |
| `camera.linearity_max_adu` | `50000` | the saturation flag threshold — §3.5 (Settings › Instrument › Sensor limits, **Linearity limit**, of which this key is a copy) |
| `photometry.default_band` | `TG` | the band label written to the exports, and the catalogue band asked for (falls back to V) — §4.1 |
| `photometry.min_comparisons` | `2` | below this, a measurement is annotated, not hidden — §4.3 |
| `photometry.auto_comparisons` | `5` | how many comparisons the automatic proposal may add — §4.5 |
| `photometry.comparison_min_snr` | `10.0` | pilot-frame SNR gate — §4.5 |
| `photometry.comparison_max_delta_mag` | `1.5` | instrumental-magnitude gate, in mag — §4.5 |
| `photometry.comparison_max_separation_arcmin` | `25.0` | how far a reference may sit from the target — §4.5 |
| `photometry.comparison_validation_min_points` | `10` | points needed before a comparison can be judged — §6 |
| `photometry.comparison_validation_max_scatter_mag` | `0.10` | above this scatter, *Unstable* — §6 |
| `photometry.comparison_validation_max_formal_error_mag` | `0.10` | above this median error, *Noisy* — §6 |
| `photometry.systematic_floor_mag` | `None` | `None` derives the floor from the curve; a number imposes it — §5 |
| `photometry.track_apertures` | `True` | whether apertures follow the tracker of §2 or are placed through the last solution alone. Live, on a mount in EQ mode the fit is a translation only; the batch re-run does not know the mount mode (saved frames do not record it) and always fits the rigid transform |

Two values are the telescope profile's, not settings: the black level $b$ (1024 ADU
on the S30 Pro, 0 on the unvalidated profiles) and the photon-transfer measurement
of §3.3. The gates of §2 and §4 (SNR 3, 5 and 10, 1 px, 2°, 10 px, 1 %, 2.5σ,
10 mmag) are constants of the code, each an owner's decision recorded in its S
entry.

```{warning}
Changing these changes what the numbers mean. Widening
`comparison_max_separation_arcmin` buys more references at the cost of
flat-field residuals; raising `comparison_max_delta_mag` mixes stars from
different parts of the detector's response. If you change one, record it —
`photometry_quality.json` stores the validation criteria that were in force, and
the flight recorder the aperture a re-run used, but nothing else stores the
settings for you.
```
