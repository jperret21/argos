# Glossary

The terms this documentation uses without stopping to explain them. Roughly in
the order you meet them.

```{glossary}
Plate solving
  Working out, from the pattern of stars in an image, exactly where the
  telescope was pointing and at what scale and rotation. ARGOS delegates it to
  ASTAP and calls it **Identify field**. Without a solve, a click on a star is
  just a pixel; with one, it is a position on the sky and therefore an
  identity.

WCS
  *World Coordinate System.* The result of a plate solve: the transformation
  between pixel coordinates and $(\alpha, \delta)$ on the sky. ARGOS computes
  one per solved frame and **does not write it into the FITS file**; see
  {doc}`fits_headers`.

CFA · Bayer pattern
  *Colour Filter Array.* A colour sensor does not measure colour per pixel; it
  has a mosaic of red, green and blue filters, one per pixel. The Seestar's
  arrangement is `GRBG`. A raw frame is this mosaic, undebayered, which is why
  it looks grey and grainy at 1:1.

Green plane
  ARGOS's measurement grid: the average of the two green samples in each 2×2
  Bayer tile, giving an image half the width and half the height of the raw
  frame. Green is used because it is the densest sampling of the mosaic. All
  photometry and all astrometry happen here, so a pixel in the solution is the
  same pixel that is measured. Defined in {doc}`differential_photometry`.

ADU
  *Analogue-to-Digital Unit.* The raw number stored per pixel: what the
  converter reported, not a physical quantity. Multiply by the **electron
  gain** to get electrons, which is what noise calculations need. The S30 Pro's
  converter has 12 bits; its values are scaled by 16 in the files, so raw
  values step by 16 ADU.

Black level
  The constant offset the camera adds to every pixel so that noise never goes
  below zero: 1024 ADU on the S30 Pro at gain 80. It is not light. ARGOS
  subtracts it before counting the sky's photons.

Electron gain · e⁻/ADU
  How many photo-electrons one ADU stands for. It sets every signal-to-noise
  ratio and every formal error. ARGOS takes it, in this order, from the
  **Electron gain table** (**Settings › Instrument**), your own photon-transfer
  file, the telescope profile's measured value (0.228 e⁻/ADU at gain 80 for the
  S30 Pro), the camera driver, then a sensor reference curve, and writes the
  value used into each frame's `EGAIN`. S30 Pro frames written at gain 80 by
  ARGOS 0.4.1 and 0.4.2 carry 1.723 or 0.8, which are not this camera's.

Photon transfer
  Measuring the electron gain from the frames themselves: in a flat region,
  the noise variance grows with the signal level, and the slope of that line
  is one over the gain. It is how the S30 Pro's 0.228 e⁻/ADU at gain 80 was
  measured, on real frames of three nights.

TG
  The AAVSO code for an **untransformed green** magnitude. It is what ARGOS
  measures and reports. It is *not* Johnson $V$, and reporting it as $V$ is
  wrong.

Instrumental magnitude
  $-2.5\log_{10}(\text{flux})$, straight from the pixels. It is specific to your
  telescope, your filter and your night, and means nothing on its own. It
  becomes a real magnitude only by comparison with stars of known brightness.

Comparison star
  A star of known, published magnitude in the same field, used to convert your
  instrumental magnitudes into real ones. Several of them together are an
  **ensemble**.

Ensemble
  The set of comparison stars, taken together. Each one's offset between
  catalogue and instrumental magnitude, weighted by its own error, gives the
  **zero point** for that frame. More stars means the accident of any one being
  wrong matters less.

Zero point
  The number you add to an instrumental magnitude to get a real one, derived
  fresh on every frame from the ensemble. When the sky dims, every star dims,
  the zero point moves, and the target's magnitude stays put: that is the whole
  trick of differential photometry.

Check star
  A star you have every reason to think is constant, measured exactly like the
  target. It is a control: if the check star moves, the problem is your
  ensemble or your night, not the target. It does **not** check the focus.

AUID
  *AAVSO Unique Identifier.* A stable name for a star in AAVSO's system,
  independent of which catalogue you found it in. Comparison stars from a VSP
  sequence carry one; a star you clicked on your own does not, which is why it
  cannot contribute a zero point.

VSX · VSP
  Two AAVSO services. **VSX** is the variable-star index: identity, type,
  period, range. **VSP** is the Variable Star Plotter, which publishes
  *sequences*: comparison stars with calibrated magnitudes and AUIDs, chosen for
  a specific field, on a numbered *chart*.

Aperture · annulus
  The circle within which a star's light is summed, and the ring around it from
  which the sky background is measured (a 3σ-clipped mean of the ring's
  pixels). Their radii and what they cost you are in
  {doc}`differential_photometry`.

Anchor stars · tracker
  During a run, ARGOS moves every aperture from frame to frame by a fit on up
  to six well-measured, isolated comparison and check stars, the *anchors*.
  When the anchors are not where the fit puts them (a field jump, a cloud), the
  frame gets no point.

FWHM
  *Full Width at Half Maximum.* How wide a star image is: the working measure
  of seeing and focus. In ARGOS it is in **green-plane pixels**, twice the size
  of raw pixels.

HFD
  *Half-Flux Diameter.* The diameter enclosing half a star's light. It behaves
  better than FWHM when badly out of focus, which is why autofocus uses it.

SNR
  *Signal-to-noise ratio* of a star's measured flux. ARGOS's gates read it: a
  target below SNR 3 on a frame is a *no detection*.

Formal error
  A point's error computed from what the frame says: photon noise of the star
  and the sky, read noise, the error of the sky estimate and scintillation, plus
  the zero point's own error.

Scintillation
  The twinkling of stars: atmospheric turbulence makes the light collected by a
  small aperture fluctuate, whatever the star's brightness. On a 30 mm aperture
  it is often the largest error of a bright star. ARGOS models it from the
  aperture, the exposure, the airmass and the site's height.

Systematic floor · σ_syst
  A run-level term ARGOS measures from the curve itself: the point-to-point
  scatter (from second differences, as `star_var_script` does) beyond what the
  formal errors explain. It is added to every point's error once a curve has
  10 valid points. Points without a detection never set it (nor, in a re-run,
  points without a verified field and off-centre rows); saturated and other
  suspect points do.

Flags
  Labels on a point that say it should not be trusted as is: **saturated**
  (the aperture's brightest pixel reached the linearity limit), **suspect** (a
  hot pixel, an unverified lock, an aperture off its star, or a comparison
  holding more than half the ensemble's weight that the others contradict) and
  **no detection** (the target below SNR 3, flagged as it is measured; or, in
  Review and a re-run, a frame whose zero point is more than 1 mag from the
  run's median). Flagged points stay in the CSV and never reach an AAVSO
  report; the one exception is a run recorded before 0.5.0, whose points with
  a lock checked on fewer than three stars are written with a warning until a
  re-run verifies them.

Run lock
  While a sequence runs, the aperture geometry, the noise model and the
  electron gain inputs cannot change, so one curve has one error model.

MAD
  *Median Absolute Deviation.* A measure of scatter that a single wild value
  cannot inflate, unlike a standard deviation. ARGOS uses it wherever one bad
  frame or one bad star must not be allowed to dominate.

Airmass
  How much atmosphere you are looking through, relative to straight up. 1.0 at
  the zenith, 2.0 at about 30° altitude. Everything gets dimmer, redder and
  noisier as it rises. ARGOS's Review takes the target's airmass from each
  frame's header `AIRMASS`, written from the mount's own position; comparison
  and check stars take their own, computed for a site fitted to the mount's
  pointing. The airmass computed for the Settings site is used only when the
  header has none or cannot be trusted (a mount that was disconnected).

BJD_TDB
  A timestamp corrected to the solar system's centre of mass and on a uniform
  time scale: the standard for anything where seconds matter, such as transit
  timing. ARGOS computes it offline, and needs the observing site to do so.
  AAVSO submissions use plain JD UTC instead; both are in the CSV.

Sub · sub-exposure
  One individual frame of a series, as opposed to a stack. ARGOS measures subs,
  never stacks.

Session folder
  The folder a run writes under the sessions folder,
  `<UTC start>_<OBJECT>/`: the raw frames in `lights/` (and `darks/`, `flats/`,
  `biases/`), `session.json`, the target set and the curves. Its layout is the
  one Siril expects; see {doc}`guide`.

Re-run
  **Review › Re-run photometry…**: measuring a session's saved light frames
  again with the current code, into a new `photometry_rerun_<UTC>/` folder,
  without touching the earlier files.

AAVSO Extended File Format
  The text format of an AAVSO photometry report: a header of `#` lines, then
  one comma-separated row per observation. ARGOS's **Export AAVSO…** writes it;
  see {doc}`guide`.

Simulator
  A simulated Seestar built into ARGOS (Connection › Link › **Simulator**), for
  trying the interface indoors. Its synthetic frames cannot be plate-solved; a
  replay of real frames (`run_web.py --replay`) can.
```

```{seealso}
{doc}`references` for the papers and catalogues behind these terms.
```
