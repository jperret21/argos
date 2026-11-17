ARGOS documentation
===================

ARGOS is desktop observing software that turns a smart telescope into a
time-series photometry instrument. It records raw FITS with a detailed
scientific header (timing, gain and its source, airmass, site, sensor geometry:
:doc:`fits_headers`), solves the field, measures a differential light curve while
the sequence runs, reviews and re-measures finished sessions, writes the AAVSO
report, and leaves behind a session folder you can reduce independently.

The Seestar S30 Pro is the reference profile; the S30 and S50 profiles remain
explicitly unvalidated for precision photometry.

.. admonition:: 0.5.0 is the first beta of the new ARGOS
   :class: warning

   0.5.0 is a stable version with the new interface: a web interface in a
   desktop app for macOS and Linux, with the ARGOS server running beside it on
   the same computer. The PyQt6 app is retired. It comes with a batch of
   optimisations and bug fixes, the photometry ones checked against Siril,
   astropy, the AAVSO VSP catalogue and the frames' own noise
   (:doc:`validation`). It was tested with its built-in simulator and with
   replays of real nights; **it has not yet been used live on a telescope**.
   Patch releases 0.5.x will follow.

   It is meant for observers who keep their raw frames and reduce them
   themselves. There is no weather safety and no restart recovery, so operate
   the telescope attended, and do not treat the live curve as a publishable
   measurement. What it does and does not mean is stated in
   :doc:`differential_photometry`; what changed is in :doc:`release_0_5_0`.

Start here
----------

.. grid:: 1 2 2 2
   :gutter: 3

   .. grid-item-card:: Install ARGOS
      :link: install
      :link-type: doc

      Twenty minutes indoors: the package, the ASTAP solver and its star
      database, and the link between them.

   .. grid-item-card:: Observing with ARGOS
      :link: guide
      :link-type: doc

      One complete session, from the settings you fill in indoors to the
      review, the AAVSO report and the folder you hand to Siril.

   .. grid-item-card:: What changed in 0.5.0
      :link: release_0_5_0
      :link-type: doc

      The new desktop app and the fixes, grouped by task, and which files
      written by 0.4.x to check before you reuse them.

   .. grid-item-card:: How the results were checked
      :link: validation
      :link-type: doc

      Times, airmass, magnitudes and error bars against astropy, Siril, the
      AAVSO VSP catalogue and the frames' own noise, with what was not checked.

   .. grid-item-card:: Method and equations
      :link: differential_photometry
      :link-type: doc

      What is actually computed (apertures, ensemble zero point, uncertainty
      budget), with every formula as implemented.

   .. grid-item-card:: FITS headers
      :link: fits_headers
      :link-type: doc

      The 65 keywords ARGOS writes (38 on every frame, 27 when the value is
      known), the file naming scheme and the session layout Siril expects.

   .. grid-item-card:: Glossary
      :link: glossary
      :link-type: doc

      AUID, check star, ensemble, zero point, green plane, TG: every term this
      documentation uses, defined once.

   .. grid-item-card:: Developer guide

      :doc:`Architecture <ARCHITECTURE>`: the server, the web interface, the
      desktop shell and the shared core. :doc:`Testing without a telescope
      <simulator_testing>`: the simulator and replays.
      :doc:`API reference <api/index>`: every module, from its docstrings.

What it does
------------

The Seestar S30 Pro is a remarkable little telescope for its price, but its
native software writes FITS with minimal metadata and offers no scientific
workflow beyond "save an image". ARGOS fills that gap.

.. grid:: 1 1 2 2
   :gutter: 2

   .. grid-item-card:: Talks to the telescope

      An ASCOM Alpaca driver layer reaches the Seestar over Wi-Fi, jog
      included. Without a telescope, a built-in simulator stands in for it,
      and replays of recorded frames run a real night through the same
      screens.

   .. grid-item-card:: Knows where it is pointing

      ASTAP recovers a WCS from the green plane, so pixel positions can be
      matched against Gaia DR3, AAVSO VSX and VSP, SIMBAD and the NASA
      Exoplanet Archive, and drawn as overlays on the image.

   .. grid-item-card:: Measures while it observes

      Circular apertures on the green plane that follow the field, a sky
      annulus, a noise model built on the camera's measured e⁻/ADU, an
      inverse-variance weighted ensemble zero point with robust rejection, and
      a run-level systematic floor measured from the curve itself.

   .. grid-item-card:: Leaves an auditable trail

      Per-frame HFD, FWHM, eccentricity, star count and sky level in the FITS
      headers and in a JSON session record, plus Review to read the night back
      offline, re-run the photometry on the raw frames and export the AAVSO
      report.

.. admonition:: The two-pipeline rule
   :class: important

   **Display and data are separate pipelines.** The raw 16-bit CFA array that
   comes off the sensor is never modified: it is exactly what gets written to
   FITS. The screen stretch (linear, log or asinh), the colour view
   (super-pixel colour, the raw mosaic or one colour plane) and the histogram
   are all computed from a *copy*. You can tune the display all night without
   ever touching the science frame.

Where the boundary is
---------------------

ARGOS measures raw, uncalibrated sub-exposures. That is enough to see that a
variable is varying and that the night is usable — it is not a calibrated
measurement. Darks, flats, registration and final photometry belong downstream,
to `Siril <https://siril.org>`__ and the companion ``star_var_script``, working
on the raw frames ARGOS preserves. The handover is described in :doc:`guide`,
and the limits in :doc:`differential_photometry`.

.. toctree::
   :hidden:
   :caption: Observing with ARGOS
   :name: sec-guide

   ARGOS home and download <https://perretjules.com/argos/>
   install.md
   guide.md
   field_identification.md
   exoplanet_transits.md
   field_connectivity.md
   release_0_5_0.md

.. toctree::
   :hidden:
   :caption: Method and data
   :name: sec-method

   differential_photometry.md
   validation.md
   fits_headers.md
   glossary.md
   references.md

.. toctree::
   :hidden:
   :caption: Developer guide
   :name: sec-developer

   ARCHITECTURE.md
   CONTRIBUTING.md
   simulator_testing.md
   seestar_protocol.md

.. toctree::
   :hidden:
   :caption: API reference
   :name: sec-api

   api/index
