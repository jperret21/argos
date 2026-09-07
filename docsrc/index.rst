ARGOS technical documentation
=============================

ARGOS is desktop observing software for time-series photometry with smart
telescopes. It records raw FITS acquisition, solved-field context, selected
photometry roles and a reviewable session record. The Seestar S30 Pro is the
reference profile; S30 and S50 profiles remain explicitly unvalidated for
precision photometry.

ARGOS 0.4.1 is a field-validation release. It is intended for technically
confident observers who retain raw FITS and independently reduce the data; it
is not unattended-observatory software and does not present quick-look curves
as final scientific results.

What it does
------------

The Seestar S30 Pro is a remarkable little telescope for its price — but its
native software saves FITS with minimal metadata and offers no scientific
workflow beyond "save an image". Argos fills the gap:

* **ASCOM Alpaca driver layer** — talks to the Seestar over Wi-Fi and to
  compatible focuser, filter-wheel and camera services through the Alpaca
  protocol. The same layer works with the Seestar and the local simulator.
* **Plate solving and field identification** — ASTAP recovers a WCS so pixel
  positions can be compared with local and optional catalogue data. The image
  can display a coordinate grid, general stars, variables, deep-sky entries,
  exoplanet hosts, VSP references and the selected ensemble.
* **Live star detection and focus metrics** — HFD, FWHM, eccentricity, and
  star count computed per frame on the green plane, written to FITS headers
  and to a JSON session log for post-processing.
* **Aperture photometry** — circular aperture + sky annulus, CCD-equation
  uncertainty budget (source + sky + read noise), instrumental magnitudes.
* **Ensemble differential photometry** — zero-point from a comparison-star
  ensemble (Honeycutt 1992), field-error estimate that includes everything
  the CCD equation does not (flat residuals, cirrus, seeing variations).
* **Sequence and Review workspaces** — multi-step Light/Dark/Flat/Bias plans,
  a durable session record, and an offline review surface for quality trends,
  preview curves, metadata and source frames.
* **Catalogue-aware workflow** — target lookup, VSP candidate retrieval and
  cached catalogue queries for field use, with the selected roles retained as
  session data.

The two-pipeline rule
---------------------

A core design choice documented throughout: **display and data are separate
pipelines**. The raw 16-bit CFA array that hits the sensor is never modified
— it is what gets written to FITS. The screen stretch (linear / log / asinh),
the colour demosaicing (super-pixel / bilinear / raw), and the histogram are
all computed from a *copy* of the data. This means you can tweak the display
to your heart's content without ever touching the science frame.

What this documentation covers
------------------------------

* :ref:`sec-getting-started` — field guide, source setup and simulator test
  drive.
* :ref:`sec-architecture` — how the layers fit together: Alpaca → workers →
  UI → photometry pipeline.
* :ref:`sec-design` — detailed design documents for the photometry plan, the
  capture pipeline, and the acquisition sequencer.
* **API reference** (:ref:`sec-api`) — every module, class and function
  documented from its source code docstrings.

.. toctree::
   :maxdepth: 2
   :caption: Getting Started
   :name: sec-getting-started

   CONTRIBUTING.md
   guide_terrain_0_4_1.md
   field_identification.md
   exoplanet_transits.md
   simulator_testing.md
   field_connectivity.md

.. toctree::
   :maxdepth: 2
   :caption: Architecture
   :name: sec-architecture

   ARCHITECTURE.md

.. toctree::
   :maxdepth: 2
   :caption: Reference
   :name: sec-reference

   seestar_protocol.md
   fits_headers.md

.. toctree::
   :maxdepth: 2
   :caption: API Reference
   :name: sec-api

   api/index

.. toctree::
   :maxdepth: 2
   :caption: Design
   :name: sec-design

   capture_panel.md
   photometry_plan.md
   acquisition_sequence.md

.. toctree::
   :maxdepth: 1
   :caption: Internal

   DOCUMENTATION_GUIDE.md
   hardware_test_plan.md
   photometry_hardening_plan.md
   release_0_4_1.md
   ui_design.md
   ui_design_pass.md
   ui_interaction_architecture.md
   ui_redesign_todo.md
   website_documentation_plan.md

.. toctree::
   :maxdepth: 1
   :caption: Status

   STATUS.md


Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
