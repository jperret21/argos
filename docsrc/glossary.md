# Glossary

The terms this documentation uses without stopping to explain them. Roughly in
the order you meet them.

```{glossary}
Plate solving
  Working out, from the pattern of stars in an image, exactly where the
  telescope was pointing and at what scale and rotation. ARGOS delegates it to
  ASTAP. Without a solve, a click on a star is just a pixel; with one, it is a
  position on the sky and therefore an identity.

WCS
  *World Coordinate System.* The result of a plate solve: the transformation
  between pixel coordinates and $(\alpha, \delta)$ on the sky. ARGOS computes
  one per solved frame and **does not write it into the FITS file** — see
  {doc}`fits_headers`.

CFA · Bayer pattern
  *Colour Filter Array.* A colour sensor does not measure colour per pixel; it
  has a mosaic of red, green and blue filters, one per pixel. The Seestar's
  arrangement is `GRBG`. A raw frame is this mosaic, undebayered — which is why
  it looks grey and grainy at 1:1.

Green plane
  ARGOS's measurement grid: the average of the two green samples in each 2×2
  Bayer tile, giving an image half the width and half the height of the raw
  frame. Green is used because it is the densest sampling of the mosaic. All
  photometry and all astrometry happen here, so a pixel in the solution is the
  same pixel that is measured. Defined in {doc}`differential_photometry` §1.

ADU
  *Analogue-to-Digital Unit.* The raw number stored per pixel — what the
  converter reported, not a physical quantity. Multiply by the **electron gain**
  to get electrons, which is what noise calculations need.

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
  The set of comparison stars, taken together. Their average offset between
  catalogue and instrumental magnitude is the **zero point** for that frame.
  More stars means the accident of any one being wrong matters less.

Zero point
  The number you add to an instrumental magnitude to get a real one, derived
  fresh on every frame from the ensemble. When the sky dims, every star dims,
  the zero point moves, and the target's magnitude stays put — which is the
  whole trick of differential photometry.

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
  Two AAVSO services. **VSX** is the variable-star index — identity, type,
  period, range. **VSP** is the Variable Star Plotter, which publishes
  *sequences*: comparison stars with calibrated magnitudes and AUIDs, chosen for
  a specific field.

Aperture · annulus
  The circle within which a star's light is summed, and the ring around it from
  which the sky background is measured. Their radii and what they cost you are
  in {doc}`differential_photometry` §3.1.

FWHM
  *Full Width at Half Maximum.* How wide a star image is — the working measure
  of seeing and focus. In ARGOS it is in **green-plane pixels**, twice the size
  of raw pixels.

HFD
  *Half-Flux Diameter.* The diameter enclosing half a star's light. It behaves
  better than FWHM when badly out of focus, which is why autofocus uses it.

MAD
  *Median Absolute Deviation.* A measure of scatter that a single wild value
  cannot inflate, unlike a standard deviation. ARGOS uses it wherever one bad
  frame or one bad star must not be allowed to dominate.

Airmass
  How much atmosphere you are looking through, relative to straight up. 1.0 at
  the zenith, 2.0 at about 30° altitude. Everything gets dimmer, redder and
  noisier as it rises.

BJD_TDB
  A timestamp corrected to the solar system's centre of mass and on a uniform
  time scale — the standard for anything where seconds matter, such as transit
  timing. AAVSO submissions use plain `JD_UTC` instead; both are exported.

Sub · sub-exposure
  One individual frame of a series, as opposed to a stack. ARGOS measures subs,
  never stacks.
```

```{seealso}
{doc}`references` for the papers and catalogues behind these terms.
```
