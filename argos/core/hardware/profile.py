"""TelescopeProfile — the physical description of one instrument.

Every hardware number Argos needs to do science lives in one frozen dataclass:
optics, sensor geometry, ADC behaviour, filter slots, network defaults. Code
asks the *active* profile (see :mod:`argos.core.hardware.active`) instead of
importing a module-level constant, which is how the same focal length used to
exist in two files and the aperture in none.

**Derived quantities are never stored.** Focal ratio and plate scale are
computed from the primitives, so they cannot drift apart from them — the bug
this package exists to kill was a hard-coded ``FOCALLEN / 50.0`` that reported
f/3.2 for an f/5.3 telescope, because the aperture was never a field anywhere.

Qt-free by construction: this module is imported by ``core``, ``workers`` and
``ui`` alike.
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: Arcseconds per radian ÷ 1000 — the small-angle constant for plate scale,
#: ``206.265 = 180 × 3600 / π / 1000``, used with µm pixels and mm focal length.
ARCSEC_CONSTANT = 206.265


@dataclass(frozen=True)
class TelescopeProfile:
    """One telescope model: what it is, and what its camera actually does.

    Args:
        key: Stable identifier used in config and on the command line.
        name: Human name, written to the FITS ``TELESCOP`` header.
        validated: True once every field has been checked against the real
            instrument. Unvalidated profiles are usable but must be surfaced
            as such — see :attr:`caveats`.
        caveats: Short notes naming the fields that are *not* confirmed on
            hardware. Empty for a validated profile.
        aperture_mm: Clear aperture. Together with the focal length this is
            the only source of the focal ratio.
        focal_length_mm: Written to FITS ``FOCALLEN``, and the denominator of
            the plate scale.
        sensor: Sensor model name, written to FITS ``INSTRUME`` and used to
            select the matching fallback EGAIN/read-noise reference curve.
        pixel_size_um: Unbinned physical pixel pitch, FITS ``XPIXSZ``/``YPIXSZ``.
        sensor_width_px: Full-frame width. A *fallback* only — the Alpaca
            driver's ``CameraXSize`` wins at connect.
        sensor_height_px: Full-frame height, same rule.
        bayer_pattern: CFA layout, FITS ``BAYERPAT``. Getting this wrong
            silently corrupts photometry, so it is called out in
            :attr:`caveats` on every unvalidated profile.
        adc_bits: Real ADC depth before the driver scales to 16-bit.
        full_well_adu: Saturation threshold in ADU, for the clipping indicator.
        linearity_max_adu: Upper bound of the trusted linear range — the
            saturation flag in aperture photometry uses this, not full well.
        filter_names: Internal filter-wheel slots in position order. Empty
            when the model has no internal wheel.
        ap_host: Fixed address the telescope serves on when running its own
            access point in the field. The connection port is not a profile
            field: every model uses 32323 and the user's actual port lives
            in the per-network connection profiles under ``alpaca``.
    """

    key: str
    name: str
    validated: bool
    caveats: tuple[str, ...] = field(default=())

    # Optics
    aperture_mm: float = 0.0
    focal_length_mm: float = 0.0

    # Sensor
    sensor: str = ""
    pixel_size_um: float = 0.0
    sensor_width_px: int = 0
    sensor_height_px: int = 0
    bayer_pattern: str = "GRBG"
    adc_bits: int = 12
    full_well_adu: int = 60000
    linearity_max_adu: int = 50000

    # Filter wheel
    filter_names: tuple[str, ...] = field(default=())

    # Network
    ap_host: str = "10.0.0.1"

    # -- derived ---------------------------------------------------------

    @property
    def focal_ratio(self) -> float:
        """f/number — computed, never stored, so it cannot contradict the optics."""
        if self.aperture_mm <= 0:
            raise ValueError(f"profile {self.key!r} has no aperture; focal ratio undefined")
        return self.focal_length_mm / self.aperture_mm

    @property
    def arcsec_per_full_px(self) -> float:
        """Plate scale in ″ per **full-resolution sensor pixel**."""
        if self.focal_length_mm <= 0:
            raise ValueError(f"profile {self.key!r} has no focal length; scale undefined")
        return ARCSEC_CONSTANT * self.pixel_size_um / self.focal_length_mm

    @property
    def arcsec_per_green_px(self) -> float:
        """Plate scale per **green-plane pixel** — one green sample per 2×2 tile."""
        return self.arcsec_per_full_px * 2.0

    @property
    def fov_deg(self) -> tuple[float, float]:
        """Nominal ``(width, height)`` field of view in degrees, at full frame."""
        scale = self.arcsec_per_full_px
        return (
            self.sensor_width_px * scale / 3600.0,
            self.sensor_height_px * scale / 3600.0,
        )

    @property
    def has_filter_wheel(self) -> bool:
        return bool(self.filter_names)

    def describe(self) -> str:
        """One-line summary for logs, the status bar and the splash screen."""
        return (
            f"{self.name} — {self.aperture_mm:g} mm f/{self.focal_ratio:.1f}, "
            f"{self.sensor}, {self.arcsec_per_full_px:.2f}″/px"
        )
