=============
API Reference
=============

Generated from the source docstrings by ``sphinx.ext.autodoc``. Each page below
covers one package; every module in it is documented inline, with a link to its
source.

.. admonition:: The layer rule
   :class: important

   ARGOS is layered so the science can be tested without a telescope and
   without a display. Read a module's layer before reading the module: it tells
   you what the module is allowed to do.

.. grid:: 1 1 3 3
   :gutter: 2

   .. grid-item-card:: core — the science

      Pure Python: no Qt, no event loop, no hidden network calls. Imaging,
      photometry, catalogues, hardware profiles and protocol clients live here,
      and so does every equation in :doc:`../differential_photometry`.

   .. grid-item-card:: workers — the bridges

      ``QThread`` wrappers that run ``core`` work off the interface thread and
      report back through signals. They hold no science of their own.

   .. grid-item-card:: ui — the presentation

      PyQt6 widgets, docks and windows. They render state and emit intent; they
      never compute a measurement.

.. note::

   One documented exception: ``argos.core.session`` imports PyQt6 for its
   signal plumbing, so the "``core`` is Qt-free" rule holds everywhere except
   that package. :doc:`../ARCHITECTURE` states where and why.

Where to start reading
----------------------

Every module below has equal visual weight, which is unhelpful on a first pass.
These five carry most of the system:

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Module
     - Why it matters
   * - :mod:`argos.core.config`
     - Every setting, its default and its migrations. Most questions of the form
       "where does this number come from" end here.
   * - :mod:`argos.core.session.acquisition_engine`
     - The heart of a run: the frame loop, the photometry call, the light-curve
       points and the session record.
   * - :mod:`argos.core.imaging.fits_writer`
     - Everything that reaches disk — the naming scheme, the folder layout and
       all 65 header keywords.
   * - :mod:`argos.workers.preview_processor`
     - The latest-frame-wins preview chain, and the pattern the other workers
       follow.
   * - :mod:`argos.ui.shell`
     - The menus, the sidebar and how a user action becomes an intent.

Core layer
----------

.. toctree::
   :maxdepth: 1

   core
   alpaca
   catalog
   hardware
   session
   exoplanet
   imaging
   photometry
   seestar
   stellarium
   support

Workers layer
-------------

.. toctree::
   :maxdepth: 1

   workers

UI layer
--------

.. toctree::
   :maxdepth: 1

   ui
