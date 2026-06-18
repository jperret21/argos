Welcome to Argos's documentation
========================================

Argos is a cross-platform desktop application for **ensemble differential
photometry** with the ZWO Seestar S30 Pro — from raw GRBG mosaic straight off
the sensor to an AAVSO-ready light curve, all in one session.

What it does
------------

The Seestar S30 Pro is a remarkable little telescope for its price — but its
native software saves FITS with minimal metadata and offers no scientific
workflow beyond "save an image". Argos fills the gap:

* **ASCOM Alpaca driver layer** — talks to the Seestar over Wi-Fi and to
  any ASCOM-compatible focuser / filter wheel / camera through the Alpaca
  protocol. The Alpaca layer is generic: the same code works with the
  Seestar, a simulator, or any Alpaca device.
* **Plate solving via ASTAP** — recovers a WCS from each frame (solved on
  the green half-res plane), so star positions are known in celestial
  coordinates. Used to drive an RA/Dec grid overlay and to project variable-
  star and comparison-star markers from the AAVSO VSP catalogue.
* **Live star detection and focus metrics** — HFD, FWHM, eccentricity, and
  star count computed per frame on the green plane, written to FITS headers
  and to a JSON session log for post-processing.
* **Aperture photometry** — circular aperture + sky annulus, CCD-equation
  uncertainty budget (source + sky + read noise), instrumental magnitudes.
* **Ensemble differential photometry** — zero-point from a comparison-star
  ensemble (Honeycutt 1992), field-error estimate that includes everything
  the CCD equation does not (flat residuals, cirrus, seeing variations).
* **Sequence engine** — multi-step plans (Light/Dark/Flat/Bias) with repeats,
  autofocus cadence, and Siril-compatible folder layout.
* **AAVSO workflow** — target lookup from VSX, comparison stars from VSP,
  light-curve export in AAVSO Extended File Format.

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

* :ref:`sec-getting-started` — build instructions, simulator test drive.
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
   simulator_testing.md

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

.. toctree::
   :maxdepth: 1
   :caption: Status

   STATUS.md


Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
