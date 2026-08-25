"""Telescope hardware profiles — what instrument Argos is driving.

Before this package, the physical description of the telescope was a set of
module-level constants scattered across ``core/alpaca/camera.py``,
``core/imaging/fits_writer.py``, ``core/imaging/metrics.py`` and four more
files — with the focal length defined twice and the aperture nowhere, which is
how the FITS writer came to report f/3.2 for an f/5.3 telescope.

Public surface::

    from argos.core.hardware import active, catalog

    active.profile().arcsec_per_full_px   # the value, at the point of use
    active.load_from_config(config)       # called once, at startup
    catalog.PROFILES                      # the built-in registry
"""

from argos.core.hardware.profile import TelescopeProfile

__all__ = ["TelescopeProfile"]
