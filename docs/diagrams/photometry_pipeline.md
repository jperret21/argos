# Photometry Pipeline

The differential photometry pipeline runs per solved frame. It projects saved catalog
stars onto the green plane, measures their flux, and calibrates targets against the
comparison ensemble.

```{graphviz} photometry_pipeline.dot
:align: center
```

## Steps

1. **Project** — {func}`~seercontrol.core.imaging.platesolve.FrameWCS.world_to_pixel_deg`
   converts each {class}`~seercontrol.core.catalog.targets.TargetStar`'s RA/Dec to
   green-plane pixel coordinates.
2. **Measure** — {func}`~seercontrol.core.photometry.aperture.measure_aperture` performs
   circular-aperture photometry with sky annulus at each projected position, returning
   {class}`~seercontrol.core.photometry.aperture.AperturePhot` (instrumental mag).
3. **Calibrate** — {func}`~seercontrol.core.photometry.differential.differential_mag`
   computes an ensemble zero-point from the comparison stars' (instrumental − catalog)
   and applies it to the target, returning {class}`~seercontrol.core.photometry.differential.DiffResult`.
4. **Accumulate** — Each {class}`~seercontrol.core.photometry.differential.DiffResult` is
   appended as a {class}`~seercontrol.core.photometry.lightcurve.LcPoint` to the
   target's {class}`~seercontrol.core.photometry.lightcurve.LightCurve`.
5. **Export** — The light curve can be written as CSV or AAVSO Extended Format.

See {doc}`../photometry_plan` §6 for the full specification.
