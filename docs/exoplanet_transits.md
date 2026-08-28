# Exoplanet transit preparation

Argos can prepare an uninterrupted acquisition sequence for a confirmed
exoplanet transit. It is a capture and live-preview tool: it does **not**
perform dark, flat or bias calibration, nor transit fitting. Reduce the raw
FITS in Siril, then produce and model the final relative-flux light curve in
the appropriate post-processing workflow.

## Before the night

1. In **Settings**, search and save the observing site. Coordinates and
   elevation are needed for the BJD_TDB prediction used by the planner.
2. In **Sequencer → Exoplanet transit**, enter a planet designation such as
   `HD 189733 b` and choose **Find planet**.
3. Argos queries the NASA Exoplanet Archive's `PSCompPars` table once and
   caches the successful result locally. It displays the host-star name,
   period, duration, depth and published transit-midpoint reference.
4. Confirm that the reported epoch is **BJD_TDB** and verify the ephemeris
   close to the observing night. Argos refuses an epoch whose time standard is
   not explicitly BJD_TDB rather than applying an implicit conversion.
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
  least as long as exposure. During the sequence Argos deducts acquisition and
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
for an up-to-date transit-and-observatory visibility calculation. The displayed
coverage is in BJD_TDB, and the observer remains responsible for whether the
event is observable at sufficient altitude and for checking uncertainty growth
in an old ephemeris.

Argos's Photometry window remains a raw-sub preview. Its measurements are
useful to see that the target, comparison stars and cadence behave sensibly in
the field, but they are not a claim of a publishable transit light curve.
The **Relative flux** switch shows `F_target / sum(F_comparisons)` normalised
to the displayed series median. This path does not require catalogue
magnitudes, so it remains available for a manual transit comparison ensemble.
It is deliberately not an out-of-transit normalisation or detrending result.

When the sequence starts, Argos stores `observation.json` beside `session.json`
and the raw FITS. For a transit it preserves the planet and host names, archive
source, period, BJD_TDB epoch, predicted contact/coverage times, duration and
published depth. It is a post-processing hand-off record, not a measurement.

## Data and privacy

NASA is contacted only after the observer requests a planet lookup. Results
are cached locally under `~/Argos/cache/exoplanets.json`; Argos sends no
telemetry and never uploads session data.

The source fields ignore case and common missing spaces: `hd189733b`,
`HD 189733 B` and `hd 189733 b` identify the same planet. Cached source names
appear in the completion menu without a network connection. A new planet or a
partial first search still needs the NASA archive; repeat an online search to
refresh a cached ephemeris. Settings → Local diagnostics lists the local cache
locations and the online/offline behaviour of CDS, NASA and AAVSO catalogues.

### Target naming and Stellarium

The FITS `OBJECT` value identifies the imaged target, not the observing
session. Selecting a Scientific source supplies its canonical catalogue name
to Capture and the acquisition plan. For a planet, it is the **host star**
(`HD 189733`), while the planet designation (`HD 189733 b`) and ephemeris are
kept in `observation.json`.

Stellarium's telescope protocol sends only ICRS coordinates. After a GoTo,
Argos may offer nearby locally cached catalogue names, but it never changes
`OBJECT` automatically: the observer must choose the intended candidate. In
the Stellarium connection card, **Look up target names online after a GoTo**
explicitly permits a CDS/SIMBAD query only when no local match exists; it is
off by default and no session data are uploaded.
