================
``argos.server``
================

The headless server of ARGOS 0.5.0: it owns the devices, the state, the jobs,
the sequences, the live photometry, Review and the exports, and serves the web
interface over REST and two WebSockets. In the desktop app it runs as the
frozen sidecar. Where it sits among the other parts: :doc:`../ARCHITECTURE`.

.. note::

   The wire contract (every route, payload, event and error) is
   `argos/server/protocol.md <https://github.com/jperret21/argos/blob/main/argos/server/protocol.md>`__,
   written before the code. The pages below are the Python side, generated
   from the docstrings; the first line of each module's docstring says what
   it owns. FastAPI, Starlette, pydantic, uvicorn and anyio are mocked for this
   build (``docsrc/conf.py``), so route decorators and pydantic bases are not
   rendered.

.. automodule:: argos.server
   :members:

Process and contract
====================

The command line, the application and its routes, authentication, the error shape, the contract's records, the event bus and the frame wire format, jobs and the log.

.. automodule:: argos.server.settings
   :members:
   :show-inheritance:

.. automodule:: argos.server.app
   :members:
   :show-inheritance:

.. automodule:: argos.server.auth
   :members:
   :show-inheritance:

.. automodule:: argos.server.errors
   :members:
   :show-inheritance:

.. automodule:: argos.server.state
   :members:
   :show-inheritance:

.. automodule:: argos.server.events
   :members:
   :show-inheritance:

.. automodule:: argos.server.frames
   :members:
   :show-inheritance:

.. automodule:: argos.server.jobs
   :members:
   :show-inheritance:

.. automodule:: argos.server.logbook
   :members:
   :show-inheritance:

.. automodule:: argos.server.runtime
   :members:
   :show-inheritance:

Devices and connection
======================

The hub that owns the four device slots, the Alpaca adapter and the built-in simulator, discovery, the network monitor, telescope profiles and the Stellarium bridge.

.. automodule:: argos.server.hub
   :members:
   :show-inheritance:

.. automodule:: argos.server.devices
   :members:
   :show-inheritance:

.. automodule:: argos.server.devices.base
   :members:
   :show-inheritance:

.. automodule:: argos.server.devices.alpaca
   :members:
   :show-inheritance:

.. automodule:: argos.server.devices.sim_camera
   :members:
   :show-inheritance:

.. automodule:: argos.server.devices.sim_mount
   :members:
   :show-inheritance:

.. automodule:: argos.server.devices.sim_aux
   :members:
   :show-inheritance:

.. automodule:: argos.server.devices.sim_replay
   :members:
   :show-inheritance:

.. automodule:: argos.server.discovery
   :members:
   :show-inheritance:

.. automodule:: argos.server.network
   :members:
   :show-inheritance:

.. automodule:: argos.server.profiles
   :members:
   :show-inheritance:

.. automodule:: argos.server.stellarium
   :members:
   :show-inheritance:

Settings and files
==================

The configuration file and the metadata of every key the interface may read or write, the site check, the folder browser, the sessions list and the support bundle.

.. automodule:: argos.server.config_store
   :members:
   :show-inheritance:

.. automodule:: argos.server.config_meta
   :members:
   :show-inheritance:
   :exclude-members: personal

.. automodule:: argos.server.settings_helpers
   :members:
   :show-inheritance:

.. automodule:: argos.server.site_check
   :members:
   :show-inheritance:

.. automodule:: argos.server.fs
   :members:
   :show-inheritance:

.. automodule:: argos.server.sessions
   :members:
   :show-inheritance:

.. automodule:: argos.server.support
   :members:
   :show-inheritance:

Observe
=======

Take shot and the FITS save, the filter wheel, the focuser and the autofocus, the jog and its dead-man, the conditions, the observation metadata and Open FITS.

.. automodule:: argos.server.capture
   :members:
   :show-inheritance:

.. automodule:: argos.server.wheel
   :members:
   :show-inheritance:

.. automodule:: argos.server.focuser
   :members:
   :show-inheritance:

.. automodule:: argos.server.autofocus
   :members:
   :show-inheritance:

.. automodule:: argos.server.jog
   :members:
   :show-inheritance:

.. automodule:: argos.server.conditions
   :members:
   :show-inheritance:

.. automodule:: argos.server.observation
   :members:
   :show-inheritance:

.. automodule:: argos.server.fits_source
   :members:
   :show-inheritance:

Field
=====

Plate solving with ASTAP, the field catalogue, frame-to-frame tracking, measurements on the field and the target set.

.. automodule:: argos.server.field
   :members:
   :show-inheritance:

.. automodule:: argos.server.field_solve
   :members:
   :show-inheritance:

.. automodule:: argos.server.field_catalog
   :members:
   :show-inheritance:

.. automodule:: argos.server.field_track
   :members:
   :show-inheritance:

.. automodule:: argos.server.field_measure
   :members:
   :show-inheritance:

.. automodule:: argos.server.targets
   :members:
   :show-inheritance:

Photometry, plan and run
========================

Live photometry (the method is the core's), sequence plans, the run and its mount interlock, visibility and transits.

.. automodule:: argos.server.photometry
   :members:
   :show-inheritance:

.. automodule:: argos.server.sequence_plan
   :members:
   :show-inheritance:

.. automodule:: argos.server.sequence
   :members:
   :show-inheritance:

.. automodule:: argos.server.planning
   :members:
   :show-inheritance:

The night
=========

Attention rules (alerts, never an action on the mount), keep-awake during a run, the end-of-night wrap-up.

.. automodule:: argos.server.attention
   :members:
   :show-inheritance:
   :exclude-members: object

.. automodule:: argos.server.keepawake
   :members:
   :show-inheritance:

.. automodule:: argos.server.wrapup
   :members:
   :show-inheritance:

Review
======

Sessions and curves (read by the core's own reader), the frame inspector, the AAVSO and CSV exports and the batch re-run.

.. automodule:: argos.server.review
   :members:
   :show-inheritance:

.. automodule:: argos.server.review_routes
   :members:
   :show-inheritance:

.. automodule:: argos.server.files
   :members:
   :show-inheritance:

.. automodule:: argos.server.exports
   :members:
   :show-inheritance:

.. automodule:: argos.server.export_routes
   :members:
   :show-inheritance:

.. automodule:: argos.server.rerun
   :members:
   :show-inheritance:

Desktop
=======

What only the desktop app uses: shutdown, reveal in the file manager, the end of the shell's stdin.

.. automodule:: argos.server.desktop
   :members:
   :show-inheritance:
