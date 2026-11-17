=============
API Reference
=============

Generated from the source docstrings by ``sphinx.ext.autodoc``. Each page below
covers one package; every module in it is documented inline, with a link to its
source.

.. admonition:: Which part a module belongs to
   :class: important

   Read a module's part before the module: it tells you what the module is
   allowed to do. :doc:`../ARCHITECTURE` gives the rules between the parts.

.. grid:: 1 1 3 3
   :gutter: 2

   .. grid-item-card:: server: the 0.5.0 runtime

      The headless FastAPI server behind the web interface and the desktop
      app's sidecar. It owns the devices, the jobs, the runs, the live
      photometry, Review and the exports. It never imports Qt.

   .. grid-item-card:: core: the science

      Imaging, photometry, catalogues, hardware profiles, the Alpaca clients and
      the FITS writer, shared by the server and the retired Qt app; every
      equation of :doc:`../differential_photometry` lives here.

   .. grid-item-card:: workers and ui: legacy

      The retired PyQt6 app: ``QThread`` workers and widgets. Not shipped since
      0.5.0, kept as the reference of the parity tests.

.. note::

   One documented exception: ``argos.core.session`` imports PyQt6 for its
   signal plumbing, so "``core`` is Qt-free" holds everywhere except that
   package. The server imports nothing from it except ``review.py``, which it
   loads by file path. :doc:`../ARCHITECTURE` states where and why.

Where to start reading
----------------------

Every module below has equal visual weight, which is unhelpful on a first pass.
These carry most of the system:

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Module
     - Why it matters
   * - :mod:`argos.server.app`
     - The application: every route, thin, each calling one method of the hub.
   * - :mod:`argos.server.hub`
     - The four device slots, their generations, and the only writer of the
       contract's records.
   * - :mod:`argos.server.events`
     - The event bus between the threads and the event loop, and its bounded
       per-client buffers.
   * - :mod:`argos.server.sequence`
     - A run, sub by sub, and its interlocks.
   * - :mod:`argos.core.config`
     - Every setting, its default and its migrations. Most questions of the form
       "where does this number come from" end here.
   * - :mod:`argos.core.imaging.fits_writer`
     - Everything that reaches disk: the naming scheme, the folder layout and
       the header keywords.

Server
------

.. toctree::
   :maxdepth: 1

   server

Core
----

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

Legacy Qt app (parity reference)
--------------------------------

The PyQt6 app that ARGOS shipped up to 0.4.2. Its pages stay because the
parity tests run its fixed code against the server's; nothing here is part of
the 0.5.0 desktop app.

.. toctree::
   :maxdepth: 1

   workers
   ui
