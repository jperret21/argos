# Exoplanet transit preparation

ARGOS can prepare an uninterrupted acquisition sequence for a confirmed
exoplanet transit. It is a capture and live-preview tool: it does **not**
perform dark, flat or bias calibration, nor transit fitting. Reduce the raw
FITS in [Siril](https://siril.org), then produce and model the final
relative-flux light curve in the appropriate post-processing workflow —
[AstroImageJ](https://www.astro.louisville.edu/software/astroimagej/) is the
usual free choice, and its paper
([Collins et al. 2017](https://doi.org/10.3847/1538-3881/153/2/77)) is worth
reading before your first attempt.

```{admonition} What depth is realistic
:class: important

A 30 mm aperture collects very little light. The target class that works is a
**deep transit on a bright host** — the hot Jupiters whose published depth runs
around one to two per cent. Before committing a night, compare the archive's depth column against the
scatter you can actually reach **on the transit timescale** — not the
point-to-point scatter.

That distinction is the whole game. ARGOS's run-level scatter
([§5](differential_photometry.md#5-the-run-level-systematic-floor)) is a
*high-frequency* number and will flatter you: it does not contain the correlated
drifts that dominate anything measured over two or three hours. The honest test
is to bin your out-of-transit residuals into bins the length of the ingress and
see where the RMS stops falling as $1/\sqrt{N}$
([Pont, Zucker & Queloz 2006](https://doi.org/10.1111/j.1365-2966.2006.11012.x)).
That floor is what your depth must beat, several times over.

For orientation: atmospheric scintillation alone puts about 15 mmag on a
20-second sub through a 30 mm aperture at airmass 1.5
([§9](differential_photometry.md#9-the-floor-you-cannot-get-under)). A 1 %
transit is 10 mmag deep. You are binning many frames to see it, and the red
noise is what decides whether the binning helps.
```

## Before the night

1. In **Settings**, search and save the observing site. Coordinates and
   elevation are needed for the BJD_TDB prediction used by the planner.
2. In **Sequencer → Exoplanet transit**, enter a planet designation such as
   `HD 189733 b` and choose **Find planet**.
3. ARGOS queries the [NASA Exoplanet
   Archive](https://exoplanetarchive.ipac.caltech.edu/)'s `PSCompPars` table
   once and caches the successful result locally. It displays the host-star
   name, period, duration, depth and published transit-midpoint reference.
4. Confirm that the reported epoch is **BJD_TDB** and verify the ephemeris
   close to the observing night. ARGOS refuses an epoch whose time standard is
   not explicitly BJD_TDB rather than applying an implicit conversion — a
   silent HJD-to-BJD confusion is worth seconds of timing error
   ([Eastman, Siverd & Gaudi 2010](https://doi.org/10.1086/655938)).
5. The selected telescope target is the **host star**, not the planet. Review
   it in Telescope and use the existing explicit GoTo action when ready.
   The **Target visibility** plot switches to the transit night and shades the
   requested coverage interval; the transit card also shows its local midpoint.

## Prepare the acquisition

Choose the observing settings in the transit panel:

* **Baseline** is out-of-transit time before ingress and after egress. The
  default is 60 minutes on each side; increase it when the event and night
  allow it.
* **Exposure** and **cadence** are start-to-start values. Cadence must be at
  least as long as exposure. During the sequence ARGOS deducts acquisition and
  download time from the cadence budget rather than adding an idle delay after
  every frame; if the hardware cannot keep up, it takes the next frame as soon
  as possible and does not pretend the requested cadence was achieved.
* Use one **filter** throughout the series. The generated plan has one Light
  step, no dithering, no autofocus and no filter changes so the cadence and
  flux time series remain stable.

Choose **Prepare transit sequence**. It replaces the editable sequence table
with the calculated number of Light frames covering the selected baseline and
published duration. This does not schedule or automatically start the mount:
review the event, target altitude, focus, framing, exposure level and actual
start time before pressing **Start sequence**.

## Scientific limits

The panel predicts timing from the archive ephemeris; it is not a replacement
for an up-to-date transit-and-observatory visibility calculation — cross-check
against the [Exoplanet Transit Database](https://var2.astro.cz/ETD) or the
[Swarthmore transit finder](https://astro.swarthmore.edu/transits/). The displayed
coverage is in BJD_TDB, and the observer remains responsible for whether the
event is observable at sufficient altitude and for checking uncertainty growth
in an old ephemeris.

ARGOS's Photometry window remains a raw-sub preview. Its measurements are
useful to see that the target, comparison stars and cadence behave sensibly in
the field, but they are not a claim of a publishable transit light curve.
The **Relative flux** switch shows `F_target / sum(F_comparisons)` normalised
to the displayed series median. This path does not require catalogue
magnitudes, so it remains available for a manual transit comparison ensemble.

```{warning}
That median normalisation is a **display** convenience, not an out-of-transit
baseline, and the difference bites exactly here: if most of your run is inside
the transit, the median sits inside the event, the baseline is dragged down and
the depth on screen looks shallower than it is. This is one more reason to hold
a real baseline on each side. Measure depth from the exported, un-normalised
`relative_flux` column against your own out-of-transit segment.
```

When the sequence starts, ARGOS stores `observation.json` beside `session.json`
and the raw FITS. For a transit it preserves the planet and host names, archive
source, period, BJD_TDB epoch, predicted contact/coverage times, duration and
published depth. It is a post-processing hand-off record, not a measurement.

## Data and privacy

NASA is contacted only after the observer requests a planet lookup. Results
are cached locally under `~/Argos/cache/exoplanets.json`; ARGOS sends no
telemetry and never uploads session data.

The source fields ignore case and common missing spaces: `hd189733b`,
`HD 189733 B` and `hd 189733 b` identify the same planet. Cached source names
appear in the completion menu without a network connection. A new planet or a
partial first search still needs the NASA archive; repeat an online search to
refresh a cached ephemeris. Settings → Catalogues · data lists the local cache
locations and the online/offline behaviour of CDS, NASA and AAVSO catalogues.

### Target naming and Stellarium

The FITS `OBJECT` value identifies the imaged target, not the observing
session. Selecting a Scientific source supplies its canonical catalogue name
to Capture and the acquisition plan. For a planet, it is the **host star**
(`HD 189733`), while the planet designation (`HD 189733 b`) and ephemeris are
kept in `observation.json`.

Stellarium's telescope protocol sends only J2000 RA/Dec. After a GoTo,
ARGOS may offer nearby locally cached catalogue names, but it never changes
`OBJECT` automatically: the observer must choose the intended candidate. In
the Stellarium connection card, **Look up target names online after a GoTo**
explicitly permits a CDS/SIMBAD query only when no local match exists; it is
off by default and no session data are uploaded.

```{seealso}
- {doc}`differential_photometry` — in particular the relative-flux ratio
  $\rho$ and its error propagation, which is what a transit run actually uses.
- {doc}`guide` — the rest of the session, from connection to hand-off.
- {doc}`references` — the archive, the time-standard paper and AstroImageJ.
```
