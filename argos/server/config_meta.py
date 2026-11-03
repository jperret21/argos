"""Metadata of every configuration key the web UI may read or write (row A8).

The source is ``web/spec/02-connection-and-settings.md`` appendix A, which
inventories every key of ``~/.argos/config.json`` with its default
(``argos/core/config.py:19-176``), its Qt editor and widget range, and every
reader. Each :class:`KeyMeta` carries what the Settings form needs (type,
default, range, step, options, unit, label, help, category) and the
"About this setting" column needs (``used_by``).

Ranges are the Qt widgets' where one exists (cited per key); keys the Qt app
never exposed (Q-C4, now under "advanced") get a range wide enough for any
sensible value, stated here.

This module also validates one value against its meta
(:func:`validate_value`): strict types (``80.0`` is not an int, ``True`` is
not a number), ranges, options, path checks. Validation never touches the
network; path checks only stat the filesystem.
"""

from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from argos.core.hardware import catalog

KeyType = Literal["bool", "int", "float", "str", "path", "host", "list", "object"]
Category = Literal[
    "connection",
    "observer_site",
    "instrument",
    "plate_solving",
    "catalogues",
    "photometry",
    "data_storage",
    "privacy_diagnostics",
    "appearance",
    "observe",
]

_HOME = Path.home()


@dataclass(frozen=True)
class KeyMeta:
    key: str
    type: KeyType
    default: Any
    label: str
    help: str
    category: Category
    used_by: tuple[str, ...] = ()
    min: float | None = None
    max: float | None = None
    step: float | None = None
    #: ``(value, label)`` pairs; the value must be one of them.
    options: tuple[tuple[Any, str], ...] | None = None
    unit: str | None = None
    nullable: bool = False
    advanced: bool = False
    read_only: bool = False
    #: Why a ``read_only`` key cannot be changed through ``PATCH /api/config``
    #: (shown under the field; wave 2).
    read_only_reason: str | None = None
    #: ``path`` keys: what the path names, and whether "" (auto) is allowed.
    path_kind: Literal["dir", "file", "exe"] = "dir"
    allow_empty: bool = False
    max_length: int = 200
    #: ``str`` keys: a full-match pattern and an upper-casing normaliser.
    pattern: str | None = None
    upper: bool = False
    #: The observer's own value (name, AAVSO code, site): its shipped default
    #: ("" or 0) is a placeholder, not a value to go back to. The web form
    #: offers no "Reset to the default" and Restore defaults skips it, so one
    #: click never moves the site to 0°, 0° (the class of the 2026-09-25
    #: wrong-site incident) or blanks the AAVSO code (wave 2 fix).
    personal: bool = False
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "default": self.default,
            "nullable": self.nullable,
            "min": self.min,
            "max": self.max,
            "step": self.step,
            "options": (
                [{"value": v, "label": label} for v, label in self.options]
                if self.options is not None
                else None
            ),
            "unit": self.unit,
            "label": self.label,
            "help": self.help,
            "used_by": list(self.used_by),
            "category": self.category,
            "advanced": self.advanced,
            "read_only": self.read_only,
            "read_only_reason": self.read_only_reason,
            # Wave 2 (integration): what a ``path`` key names, so the in-app
            # FilePicker opens in the right mode; null for other types.
            "path_kind": self.path_kind if self.type == "path" else None,
            "personal": self.personal,
        }


def _k(key: str, type_: KeyType, default: Any, label: str, help_: str, category: Category, **kw):
    return KeyMeta(
        key=key, type=type_, default=default, label=label, help=help_, category=category, **kw
    )


#: AAVSO filter codes offered for ``photometry.default_band`` (AAVSO WebObs
#: filter list); a colour sensor's channels first, then Johnson-Cousins,
#: unfiltered, Sloan and near-infrared.
_AAVSO_BANDS: tuple[tuple[str, str], ...] = (
    ("TG", "TG · Tri-colour green"),
    ("TB", "TB · Tri-colour blue"),
    ("TR", "TR · Tri-colour red"),
    ("V", "V · Johnson V"),
    ("B", "B · Johnson B"),
    ("U", "U · Johnson U"),
    ("R", "R · Cousins R"),
    ("I", "I · Cousins I"),
    ("CV", "CV · Clear, V zero point"),
    ("CR", "CR · Clear, R zero point"),
    ("CBB", "CBB · Clear, blue-blocking"),
    ("SU", "SU · Sloan u"),
    ("SG", "SG · Sloan g"),
    ("SR", "SR · Sloan r"),
    ("SI", "SI · Sloan i"),
    ("SZ", "SZ · Sloan z"),
    ("J", "J · NIR 1.2 µm"),
    ("H", "H · NIR 1.6 µm"),
    ("K", "K · NIR 2.2 µm"),
)

_PROFILE_OPTIONS = tuple(
    (p.key, p.name if p.validated else f"{p.name} (unvalidated)") for p in catalog.PROFILES.values()
)

#: Every exposed key, in Settings-form order within each category.
# fmt: off
KEYS: tuple[KeyMeta, ...] = (
    # -- Connection (Link card, Planetarium card) --------------------------------
    _k("alpaca.host", "host", "", "Seestar address",
       "IPv4 address or host name of the Seestar's Alpaca server on the current network.",
       "connection", used_by=("device connect", "discovery candidate", "reachability probe"),
       allow_empty=True),
    _k("alpaca.port", "int", 32323, "Alpaca port",
       "Alpaca HTTP port: 32323 on the Seestar (4700 is its native JSON-RPC port, not this one).",
       "connection", used_by=("device connect", "discovery", "reachability probe"),
       min=1, max=65535, step=1),
    _k("stellarium.host", "host", "127.0.0.1", "Stellarium bridge host",
       "Interface the Stellarium Telescope Control server listens on. 127.0.0.1 keeps it on "
       "this computer; a network address lets Stellarium on another computer drive the mount.",
       "connection", used_by=("Stellarium bridge",)),
    _k("stellarium.port", "int", 10001, "Stellarium bridge port",
       "TCP port Stellarium's Telescope Control plugin connects to.",
       "connection", used_by=("Stellarium bridge",), min=1024, max=65535, step=1),
    _k("stellarium.online_target_lookup", "bool", False,
       "Look up target names online after a GoTo",
       "When no local catalogue match exists, send the GoTo coordinates to CDS/SIMBAD to "
       "suggest a target name. ARGOS always asks before changing FITS metadata.",
       "connection", used_by=("Stellarium GoTo name suggestion",)),
    # -- Observer & site ----------------------------------------------------------
    _k("observer.name", "str", "", "Observer name", "Written to the FITS OBSERVER keyword.",
       "observer_site", used_by=("FITS OBSERVER",), max_length=68, personal=True),
    _k("observer.obscode", "str", "", "AAVSO observer code",
       "Stamped on every AAVSO export. Letters and digits, upper-cased.",
       "observer_site", used_by=("AAVSO export OBSCODE",), max_length=10,
       pattern=r"[A-Z0-9]*", upper=True, personal=True),
    _k("site.name", "str", "", "Site name", "Name of the default observing site.",
       "observer_site", used_by=("Plan visibility",), max_length=80, personal=True),
    _k("site.latitude", "float", 0.0, "Latitude",
       "Geodetic latitude, north positive. Written to FITS SITELAT; used for altitude, "
       "airmass and target visibility.",
       "observer_site", used_by=("FITS SITELAT", "airmass", "Plan visibility"),
       min=-90.0, max=90.0, step=0.00001, unit="°", personal=True),
    _k("site.longitude", "float", 0.0, "Longitude",
       "Geodetic longitude, east positive. Written to FITS SITELONG; used for altitude, "
       "airmass and target visibility.",
       "observer_site", used_by=("FITS SITELONG", "airmass", "Plan visibility"),
       min=-180.0, max=180.0, step=0.00001, unit="°", personal=True),
    _k("site.elevation", "float", 0.0, "Elevation",
       "Height above sea level. Written to FITS SITEELEV.",
       "observer_site", used_by=("FITS SITEELEV", "airmass"),
       min=-500.0, max=9000.0, step=0.1, unit="m", personal=True),  # configuration_page.py:179
    _k("site.favorites", "list", [], "Saved sites",
       "Saved observing sites: name, latitude, longitude, elevation.",
       "observer_site", used_by=("Settings › Observer & site",)),
    # -- Instrument -------------------------------------------------------------------
    _k("hardware.profile", "str", catalog.DEFAULT_PROFILE.key, "Telescope",
       "The instrument model: plate scale, sensor geometry and FITS identity. Changed on the "
       "Connection screen (Instrument card); locked while equipment is connected.",
       "instrument", used_by=("plate scale", "FITS TELESCOP / FOCALLEN / BAYERPAT", "discovery"),
       options=_PROFILE_OPTIONS, read_only=True,
       # Set with PUT /api/profile; the reason is shown to the observer.
       read_only_reason="Changed on the Connection screen (Instrument card), which checks "
                        "that no equipment is connected."),
    _k("hardware.overrides.full_well_adu", "int", None, "Saturation (full well)",
       "Saturation threshold of your unit; empty uses the telescope profile's value. The Qt "
       "app reads the same value.",
       "instrument", used_by=("saturation overlay",), min=0, max=65535, step=1, unit="ADU",
       nullable=True),  # configuration_page.py:617
    _k("hardware.overrides.linearity_max_adu", "int", None, "Linearity limit",
       "Upper bound of the trusted linear range; empty uses the telescope profile's value. The "
       "Qt app reads the same value.",
       "instrument", used_by=("photometry saturation flag",), min=0, max=65535, step=1,
       unit="ADU", nullable=True),  # configuration_page.py:623
    _k("hardware.overrides.adc_bits", "int", None, "ADC depth",
       "Bits of the sensor's analogue-to-digital converter, from the telescope profile.",
       "instrument", used_by=("effective ADC depth note",), min=8, max=16, step=1, unit="bit",
       nullable=True, advanced=True, read_only=True,
       # Decision Q-C1 (web/spec/README.md 8.2); the reason is shown to the observer.
       read_only_reason="The ADC depth is the sensor's, set by the telescope profile."),
    _k("hardware.overrides.ap_host", "host", None, "Access-point address",
       "Address the telescope serves on in its own Wi-Fi access-point mode; empty uses the "
       "profile's value. Probed by discovery when the broadcast is silent.",
       "instrument", used_by=("discovery candidate",), nullable=True, advanced=True),
    _k("camera.full_well_adu", "int", 60000, "Qt app saturation",
       "The copy of Saturation (full well) the Qt app reads.",
       "instrument", used_by=("Qt saturation overlay",), min=0, max=65535, unit="ADU",
       read_only=True, advanced=True,
       read_only_reason="Follows Saturation (full well) above, so the Qt app reads the same "
                        "value."),  # Q-C1
    _k("camera.linearity_max_adu", "int", 50000, "Qt app linearity limit",
       "The copy of Linearity limit the Qt app reads.",
       "instrument", used_by=("Qt photometry saturation flag",), min=0, max=65535, unit="ADU",
       read_only=True, advanced=True,
       read_only_reason="Follows Linearity limit above, so the Qt app reads the same "
                        "value."),  # Q-C1
    _k("camera.egain_table", "object", {}, "Electron gain table",
       "Measured electrons per ADU at each gain setting; empty uses the driver's value or the "
       "sensor reference curve.",
       "instrument", used_by=("photometry noise model",), advanced=True),
    _k("data_paths.camera_calibration_directory", "path", str(_HOME / ".argos"),
       "Photon-transfer calibrations",
       "Folder searched for camera_calibration*.json, used only when the driver gives no "
       "electron gain.",
       "instrument", used_by=("electron gain fallback",)),
    # -- Plate solving -------------------------------------------------------------------
    _k("astrometry.astap_path", "path", "", "ASTAP executable",
       "Empty: auto-detect (astap_cli on PATH).",
       "plate_solving", used_by=("plate solving",), path_kind="exe", allow_empty=True),
    _k("astrometry.database", "str", "", "Database set",
       "ASTAP star database to use; ignored while a star database folder is set.",
       "plate_solving", used_by=("plate solving",),
       options=(("", "Auto"),) + tuple(
           (name, name) for name in ("D05", "D20", "D50", "D80", "G17", "H17", "H18", "V17", "W08")
       )),  # configuration_page.py:52
    _k("astrometry.database_path", "path", "", "Star database folder",
       "When set, ASTAP uses this folder (-d) and ignores the database set.",
       "plate_solving", used_by=("plate solving",), allow_empty=True),
    _k("astrometry.downsample", "int", 2, "Downsample",
       "Image reduction before solving; Auto lets ASTAP choose.",
       "plate_solving", used_by=("plate solving",),
       options=((0, "Auto"), (1, "1×"), (2, "2×"), (3, "3×"), (4, "4×"))),  # :54
    _k("astrometry.search_radius_deg", "int", 30, "Search radius",
       "Radius searched around the pointing hint; 0 = blind, whole sky.",
       "plate_solving", used_by=("plate solving",), min=0, max=180, step=1, unit="°"),  # :690
    _k("astrometry.use_scale_hint", "bool", True, "Use the known plate scale as a hint",
       "Pass the profile's plate scale to ASTAP (faster solve).",
       "plate_solving", used_by=("plate solving",)),
    _k("astrometry.grid_spacing_arcmin", "int", 0, "Coordinate grid spacing",
       "Spacing of the RA/Dec grid drawn on a solved image; 0 = adaptive.",
       "plate_solving", used_by=("sky grid overlay",), min=0, max=120, step=1,
       unit="′"),  # astrometry_settings.py:119
    _k("astrometry.live_search_radius_deg", "float", 5, "Live search radius",
       "Search radius of the automatic solve, which has the mount position as a hint.",
       "plate_solving", used_by=("automatic field identification",), min=0.0, max=180.0,
       step=1.0, unit="°", advanced=True),
    _k("astrometry.live_resolve_s", "float", 20, "Re-solve at most every",
       "Ceiling of the automatic re-solve cadence.",
       "plate_solving", used_by=("automatic field identification",), min=1.0, max=3600.0,
       step=1.0, unit="s", advanced=True),
    _k("astrometry.live_resolve_arcmin", "float", 2, "Re-solve after a move of",
       "The automatic solve runs again once the mount has moved this far.",
       "plate_solving", used_by=("automatic field identification",), min=0.1, max=600.0,
       step=0.5, unit="′", advanced=True),
    _k("astrometry.live_timeout_s", "float", 25, "Automatic solve timeout",
       "Bound on one automatic solve, so the cadence never stalls.",
       "plate_solving", used_by=("automatic field identification",), min=1.0, max=600.0,
       step=1.0, unit="s", advanced=True),
    # -- Catalogues --------------------------------------------------------------------
    _k("catalog.identification_max_objects", "int", 400, "Identification budget",
       "Online identities for one field, shared by Gaia and SIMBAD: fast 100 or 200, "
       "balanced 400, detailed 800, dense field 1\u202f600.",
       "catalogues", used_by=("field catalogue fetch",), unit="objects",
       # Numbers as labels, so the five fit side by side (02 2.2: a Segmented
       # 100 / 200 / 400 / 800 / 1 600); the names are in the help.
       options=((100, "100"), (200, "200"), (400, "400"), (800, "800"),
                (1600, "1\u202f600"))),  # configuration_page.py:396-406
    _k("catalog.mag_limit", "float", 15.0, "VSX faint limit",
       "Faintest variable star (maximum brightness) fetched from AAVSO VSX.",
       "catalogues", used_by=("variable-star catalogue",), min=5.0, max=20.0, step=0.5,
       unit="mag"),  # astrometry_settings.py:140
    _k("catalog.max_results", "int", 250, "Maximum variables",
       "Most variable stars fetched for one field.",
       "catalogues", used_by=("variable-star catalogue",), min=10, max=2000,
       step=10),  # :147
    _k("catalog.include_suspected", "bool", True, "Include suspected variables",
       "Also list VSX entries flagged as suspected variables.",
       "catalogues", used_by=("variable-star catalogue",)),
    _k("catalog.field_stars_enabled", "bool", True, "Identify field stars with Gaia DR3",
       "Fetch Gaia DR3 sources for a solved field (cached).",
       "catalogues", used_by=("field catalogue fetch", "star identification")),
    _k("catalog.field_stars_mag_limit", "float", 18.0, "Gaia depth",
       "Faintest Gaia G magnitude fetched and cached for a field.",
       "catalogues", used_by=("field catalogue fetch",), min=3.0, max=20.0, step=0.5,
       unit="mag"),  # :179
    _k("catalog.field_stars_detected_only", "bool", False,
       "Only draw Gaia sources detected in the image",
       "Hide catalogue stars the local peak detector did not find.",
       "catalogues", used_by=("field overlay",)),
    _k("catalog.show_essential_objects", "bool", True, "Show bundled Messier, NGC and IC objects",
       "Local catalogue shipped with ARGOS; never online.",
       "catalogues", used_by=("field overlay",)),
    _k("catalog.show_cached_exoplanets", "bool", True, "Show cached exoplanet hosts",
       "Exoplanet hosts already in the local cache; never online.",
       "catalogues", used_by=("field overlay",)),
    _k("catalog.named_objects_enabled", "bool", True, "Identify named objects with SIMBAD",
       "Name galaxies, nebulae, clusters and other objects of a solved field.",
       "catalogues", used_by=("field catalogue fetch",)),
    _k("catalog.named_objects_allow_network", "bool", True, "Query SIMBAD when not cached",
       "Allow a network query to CDS/SIMBAD when the field is not in the cache.",
       "catalogues", used_by=("field catalogue fetch",)),
    _k("catalog.exoplanet_hosts_enabled", "bool", True, "Find confirmed exoplanet hosts",
       "Mark confirmed exoplanet host stars in a solved field.",
       "catalogues", used_by=("field catalogue fetch",)),
    _k("catalog.exoplanet_hosts_allow_network", "bool", True, "Query NASA when not cached",
       "Allow a network query to the NASA Exoplanet Archive when the field is not cached.",
       "catalogues", used_by=("field catalogue fetch",)),
    # -- Observe (point-of-use values kept in the server config) ---------------------------
    _k("catalog.display_mag_limit", "float", 18.0, "Display depth",
       "Faintest Gaia star drawn on the image (filters the cached field locally).",
       "observe", used_by=("field overlay",), min=3.0, max=20.0, step=0.1, unit="mag"),
    _k("imaging.star_radius_px", "int", 5, "Star aperture",
       "Radius of the star-measurement aperture, in green-plane pixels.",
       "observe", used_by=("star measurement", "frame metrics"), min=2, max=30, step=1,
       unit="px"),  # histogram_dock.py:163; metrics.py:28
    _k("ui.display.rotation", "str", "auto", "Qt app image rotation",
       "Display rotation the Qt app uses; the web UI seeds its per-viewer rotation from it once.",
       "observe", used_by=("viewer (seed)",),
       options=(("auto", "Auto"), ("0", "0°"), ("90", "90°"), ("180", "180°"),
                ("270", "270°"))),
    # -- Photometry ----------------------------------------------------------------------
    _k("photometry.aperture_fwhm_mult", "float", 2.5, "Aperture radius",
       "Aperture radius as a multiple of the measured FWHM.",
       "photometry", used_by=("aperture photometry",), min=1.0, max=6.0, step=0.25,
       unit="× FWHM"),  # photometry_window.py:65-66
    _k("photometry.aperture_min_px", "float", 4, "Aperture radius floor",
       "Lower limit of the aperture radius, in green-plane pixels.",
       "photometry", used_by=("aperture photometry",), min=2.0, max=30.0, step=0.5,
       unit="px"),  # :75
    _k("photometry.annulus_in_px", "float", 8, "Sky annulus inner radius",
       "Inner radius of the local-sky annulus, in green-plane pixels.",
       "photometry", used_by=("aperture photometry",), min=3.0, max=60.0, step=0.5,
       unit="px"),  # :82
    _k("photometry.annulus_out_px", "float", 12, "Sky annulus outer radius",
       "Outer radius of the local-sky annulus, in green-plane pixels.",
       "photometry", used_by=("aperture photometry",), min=5.0, max=80.0, step=0.5,
       unit="px"),  # :89
    _k("photometry.auto_comparisons", "int", 5, "Automatic comparison stars",
       "Comparison stars picked automatically when a target is chosen.",
       "photometry", used_by=("comparison selection",), min=1, max=20,
       step=1),  # astrometry_settings.py:263
    _k("photometry.default_band", "str", "TG", "AAVSO band",
       "FILT value of every AAVSO report. TG for the green channel of a colour (Bayer) "
       "sensor such as the Seestar's.",
       "photometry", used_by=("AAVSO export FILT",), max_length=4, pattern=r"[A-Za-z0-9]+",
       # A list, not free text: a typo would write a wrong FILT into every report.
       # AAVSO filter codes (WebObs "Filters"): the colour-sensor channels first.
       options=_AAVSO_BANDS),
    _k("photometry.comparison_min_snr", "float", 10.0, "Comparison minimum SNR",
       "Pilot-frame SNR a comparison star needs to be selected automatically.",
       "photometry", used_by=("comparison selection",), min=3.0, max=100.0, step=1.0,
       unit="SNR"),  # photometry_window.py:97
    _k("photometry.comparison_max_delta_mag", "float", 1.5, "Comparison magnitude range",
       "Largest magnitude difference from the target for an automatic comparison.",
       "photometry", used_by=("comparison selection",), min=0.2, max=5.0, step=0.1,
       unit="mag"),  # :110
    _k("photometry.comparison_max_separation_arcmin", "float", 25.0, "Comparison distance",
       "Largest distance from the target for an automatic comparison.",
       "photometry", used_by=("comparison selection",), min=5.0, max=120.0, step=5.0,
       unit="′"),  # :125
    _k("photometry.systematic_floor_mag", "float", None, "Systematic floor",
       "Run-level error floor added to every point; empty derives it from the light curve "
       "after ten valid points.",
       "photometry", used_by=("light-curve errors",), min=0.0, max=1.0, step=0.001, unit="mag",
       nullable=True),
    _k("photometry.track_apertures", "bool", True, "Track apertures",
       "Follow field rotation and drift across a batch.",
       "photometry", used_by=("batch photometry",)),
    _k("photometry.read_noise_e", "float", 1.5, "Read noise",
       "Read noise used in the photometric error model.",
       "photometry", used_by=("photometry noise model",), min=0.0, max=100.0, step=0.1,
       unit="e⁻", advanced=True),
    _k("photometry.min_comparisons", "int", 2, "Minimum comparisons",
       "Fewest comparison stars for a valid ensemble measurement.",
       "photometry", used_by=("ensemble photometry",), min=1, max=20, step=1, advanced=True),
    _k("photometry.comparison_validation_min_points", "int", 10, "Validation: minimum points",
       "Points a comparison needs before its scatter is judged.",
       "photometry", used_by=("comparison quality report",), min=2, max=10000, step=1,
       advanced=True),
    _k("photometry.comparison_validation_max_scatter_mag", "float", 0.10,
       "Validation: maximum scatter",
       "Largest leave-one-out scatter of an accepted comparison.",
       "photometry", used_by=("comparison quality report",), min=0.001, max=5.0, step=0.01,
       unit="mag", advanced=True),
    _k("photometry.comparison_validation_max_formal_error_mag", "float", 0.10,
       "Validation: maximum formal error",
       "Largest formal error of an accepted comparison.",
       "photometry", used_by=("comparison quality report",), min=0.001, max=5.0, step=0.01,
       unit="mag", advanced=True),
    # -- Data & storage ------------------------------------------------------------------
    _k("sessions_path", "path", str(_HOME / "Argos" / "sessions"), "Sessions folder",
       "Each observation gets its own subfolder: FITS frames, metadata, products and logs.",
       "data_storage", used_by=("frame saving", "Review sessions", "support bundle")),
    _k("data_paths.sequence_presets_directory", "path", str(_HOME / "Argos" / "sequences"),
       "Sequence presets", "Folder of the saved sequence presets.",
       "data_storage", used_by=("Plan presets",)),
    _k("data_paths.object_catalogue_cache", "path",
       str(_HOME / "Argos" / "cache" / "object_resolver.json"), "Target names cache",
       "CDS/SIMBAD name lookups (file).",
       "data_storage", used_by=("object resolver",), path_kind="file"),
    _k("data_paths.exoplanet_cache", "path", str(_HOME / "Argos" / "cache" / "exoplanets.json"),
       "Transit ephemerides cache", "NASA Exoplanet Archive ephemerides (file).",
       "data_storage", used_by=("transit planning",), path_kind="file"),
    _k("data_paths.aavso_cache_directory", "path", str(_HOME / ".argos" / "cache" / "catalog"),
       "Variables cache", "AAVSO VSX / VSP field responses.",
       "data_storage", used_by=("variable-star catalogue",)),
    _k("data_paths.gaia_cache_directory", "path", str(_HOME / ".argos" / "cache" / "gaia"),
       "Field stars cache", "Gaia DR3 field responses.",
       "data_storage", used_by=("field catalogue fetch",)),
    _k("data_paths.field_catalogue_cache_directory", "path",
       str(_HOME / ".argos" / "cache" / "field_catalogue"), "Field identities cache",
       "SIMBAD named objects (simbad/) and NASA exoplanet hosts (nasa/).",
       "data_storage", used_by=("field catalogue fetch",)),
    # -- Privacy & diagnostics --------------------------------------------------------------
    _k("diagnostics.enabled", "bool", False, "Save per-frame diagnostic records",
       "Local JSONL flight recorder inside each session. Never sent anywhere.",
       "privacy_diagnostics", used_by=("session diagnostics",)),
    _k("ui.log_level", "str", "INFO", "Log level",
       "Detail of the server log (stderr and argos.log); applied at once.",
       "privacy_diagnostics", used_by=("server log",),
       options=(("DEBUG", "DEBUG"), ("INFO", "INFO"), ("WARNING", "WARNING"), ("ERROR", "ERROR"))),
    # -- Appearance ------------------------------------------------------------------------
    _k("ui.theme.preset", "str", "Observatory", "Qt app theme",
       "Colour theme of the Qt app; the web UI seeds its per-viewer theme from it once.",
       "appearance", used_by=("Qt theme", "web theme (seed)"),
       options=(("Observatory", "Observatory"), ("Charcoal", "Charcoal"),
                ("Night (Red)", "Night Red"))),  # palettes.py:74, 100, 136
)
# fmt: on

META: dict[str, KeyMeta] = {m.key: m for m in KEYS}

#: Keys of ``web/spec/02-connection-and-settings.md`` appendix A that are
#: deliberately not exposed, with the reason (``ConfigSnapshot.omitted``).
#: With :data:`META` this covers every key of that table (wave 2 exit
#: criterion); the file keeps them untouched.
OMITTED: tuple[tuple[str, str], ...] = (
    ("observer.latitude", "Legacy site key, migrated to site.latitude on load (config.py:328-342)."),
    ("observer.longitude", "Legacy site key, migrated to site.longitude on load."),
    ("observer.elevation", "Legacy site key, migrated to site.elevation on load."),
    ("ui.window_state", "Dead default: no reader (decision Q-C7)."),
    ("ui.window_geometry", "Dead default: no reader (decision Q-C7)."),
    ("ui.language", "No translation exists; the selector is dropped (decisions Q-G12, Q-C7)."),
    ("ui.shell.geometry", "Qt window state; the web UI keeps its layout per viewer."),
    ("ui.shell.state", "Qt window state; the web UI keeps its layout per viewer."),
    ("ui.shell.mode", "Qt window state; the web UI keeps its section per viewer."),
    ("ui.imaging.layout", "Qt dock layout; the web UI keeps its layout per viewer."),
    ("ui.sequencer.layout", "Qt dock layout; the web UI keeps its layout per viewer."),
    ("ui.review.layout", "Qt dock layout; the web UI keeps its layout per viewer."),
    ("camera.adc_bits", "Deprecated (config.py:75-77), no reader; the profile gives the ADC "
                        "depth (decision Q-C7)."),
    ("catalog.field_stars_max_results", "Dead: no reader (decision Q-C7)."),
    ("catalog.named_objects_max_results", "Dead: no reader (decision Q-C7)."),
    ("catalog.display_limit_version", "Internal migration marker (config.py:354)."),
    ("diagnostics.local_opt_in_v1", "Internal marker, written with diagnostics.enabled "
                                    "(configuration_page.py:1200-1206)."),
)  # fmt: skip

#: Keys that change process-wide data locations (applied to core modules).
DATA_PATH_KEYS = frozenset(
    {
        "data_paths.camera_calibration_directory",
        "data_paths.object_catalogue_cache",
        "data_paths.exoplanet_cache",
        "data_paths.aavso_cache_directory",
        "data_paths.gaia_cache_directory",
        "data_paths.field_catalogue_cache_directory",
    }
)

#: Override key -> the legacy ``camera.*`` key the Qt app still reads (Q-C1).
LEGACY_MIRROR = {
    "hardware.overrides.full_well_adu": ("camera.full_well_adu", "full_well_adu"),
    "hardware.overrides.linearity_max_adu": ("camera.linearity_max_adu", "linearity_max_adu"),
}

_HOST = re.compile(r"[A-Za-z0-9._:%\[\]-]+")
_LOOPBACK = frozenset({"127.0.0.1", "localhost", "::1"})


class InvalidValue(ValueError):
    """A value refused for one key; the message is shown under the field."""


def is_loopback_host(host: str) -> bool:
    return host.strip("[]").lower() in _LOOPBACK or host.startswith("127.")


def _number(meta: KeyMeta, value: Any, integer: bool) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InvalidValue("must be an integer" if integer else "must be a number")
    if integer and not isinstance(value, int):
        raise InvalidValue("must be an integer")
    if not integer:
        if not math.isfinite(value):
            raise InvalidValue("must be a finite number")
        value = float(value)
    if meta.min is not None and value < meta.min:
        raise InvalidValue(f"must be at least {meta.min:g}{_unit(meta)}")
    if meta.max is not None and value > meta.max:
        raise InvalidValue(f"must be at most {meta.max:g}{_unit(meta)}")
    return value


def _unit(meta: KeyMeta) -> str:
    if not meta.unit:
        return ""
    return meta.unit if meta.unit in ("°", "′") else f" {meta.unit}"


def _check_options(meta: KeyMeta, value: Any) -> None:
    if meta.options is None:
        return
    allowed = [v for v, _ in meta.options]
    # 1 == True in Python: compare types too, so true is not option 1.
    if not any(type(v) is type(value) and v == value for v in allowed):
        shown = ", ".join(repr(v) if isinstance(v, str) else str(v) for v in allowed)
        raise InvalidValue(f"must be one of {shown}")


def _host(meta: KeyMeta, value: Any) -> str:
    if not isinstance(value, str):
        raise InvalidValue("must be a string")
    text = value.strip()
    if not text:
        if meta.allow_empty:
            return ""
        raise InvalidValue("must not be empty")
    if len(text) > 253 or not _HOST.fullmatch(text):
        raise InvalidValue("must be an IP address or a host name")
    return text


def _nearest_existing(path: Path) -> Path | None:
    for candidate in (path, *path.parents):
        try:
            if candidate.exists():
                return candidate
        except OSError:
            return None
    return None


def _path(meta: KeyMeta, value: Any) -> tuple[str, str | None]:
    """Validate a path; returns ``(stored text, warning or None)``."""
    if not isinstance(value, str):
        raise InvalidValue("must be a string")
    text = value.strip()
    if not text:
        if meta.allow_empty:
            return "", None
        raise InvalidValue("must not be empty")
    if len(text) > 4096 or "\0" in text:
        raise InvalidValue("is not a valid path")
    path = Path(text).expanduser()
    if not path.is_absolute():
        raise InvalidValue("must be an absolute path")
    try:
        exists = path.exists()
        is_dir = path.is_dir()
    except OSError as exc:
        raise InvalidValue(f"cannot be examined ({exc.strerror or exc})") from exc
    if meta.path_kind == "exe":
        if not exists:
            return str(path), "not found: plate solving will fail until it exists"
        if is_dir or not os.access(path, os.X_OK):
            return str(path), "is not an executable file"
        return str(path), None
    folder = path if meta.path_kind == "dir" else path.parent
    if meta.path_kind == "file" and is_dir:
        raise InvalidValue("is a folder; a file name is expected")
    if meta.path_kind == "dir" and exists and not is_dir:
        raise InvalidValue("is a file; a folder is expected")
    if folder.exists():
        if not os.access(folder, os.W_OK | os.X_OK):
            raise InvalidValue("not writable")
        return str(path), None
    anchor = _nearest_existing(folder)
    if anchor is None or not anchor.is_dir() or not os.access(anchor, os.W_OK | os.X_OK):
        raise InvalidValue("not writable")
    what = "does not exist" if meta.path_kind == "dir" else "folder does not exist"
    return str(path), f"{what}, it will be created"


def _favorites(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise InvalidValue("must be a list")
    if len(value) > 200:
        raise InvalidValue("at most 200 saved sites")
    out = []
    ranges = {
        "latitude": (-90.0, 90.0),
        "longitude": (-180.0, 180.0),
        "elevation": (-500.0, 9000.0),
    }
    for i, item in enumerate(value):
        if not isinstance(item, dict) or set(item) != {"name", *ranges}:
            raise InvalidValue(f"item {i} must have exactly name, latitude, longitude, elevation")
        name = item["name"]
        if not isinstance(name, str) or not name.strip() or len(name) > 80:
            raise InvalidValue(f"item {i}: name must be 1 to 80 characters")
        entry: dict[str, Any] = {"name": name.strip()}
        for field_name, (low, high) in ranges.items():
            number = item[field_name]
            if isinstance(number, bool) or not isinstance(number, (int, float)):
                raise InvalidValue(f"item {i}: {field_name} must be a number")
            if not math.isfinite(number) or not low <= number <= high:
                raise InvalidValue(f"item {i}: {field_name} must be between {low:g} and {high:g}")
            entry[field_name] = float(number)
        out.append(entry)
    return out


def _egain_table(value: Any) -> dict[str, float]:
    if not isinstance(value, dict):
        raise InvalidValue("must be an object {gain: e/ADU}")
    out: dict[str, float] = {}
    for gain, egain in value.items():
        if not str(gain).isdigit() or int(gain) > 10000:
            raise InvalidValue(f"gain {gain!r} must be an integer 0…10000")
        if isinstance(egain, bool) or not isinstance(egain, (int, float)):
            raise InvalidValue(f"gain {gain}: e/ADU must be a number")
        if not math.isfinite(egain) or not 0 < egain <= 100:
            raise InvalidValue(f"gain {gain}: e/ADU must be in (0, 100]")
        out[str(int(gain))] = float(egain)
    return out


def validate_value(meta: KeyMeta, value: Any) -> tuple[Any, str | None]:
    """Check *value* for *meta*; returns ``(normalised value, warning or None)``.

    Raises :class:`InvalidValue` with a message meant for the observer.
    """
    if value is None:
        if meta.nullable:
            return None, None
        raise InvalidValue("must not be empty")
    warning = None
    if meta.type == "bool":
        if not isinstance(value, bool):
            raise InvalidValue("must be true or false")
        result: Any = value
    elif meta.type in ("int", "float"):
        result = _number(meta, value, integer=meta.type == "int")
    elif meta.type == "str":
        if not isinstance(value, str):
            raise InvalidValue("must be a string")
        result = value.strip()
        if meta.upper:
            result = result.upper()
        if len(result) > meta.max_length:
            raise InvalidValue(f"must be at most {meta.max_length} characters")
        if meta.pattern and result and not re.fullmatch(meta.pattern, result):
            raise InvalidValue("contains characters that are not allowed")
    elif meta.type == "host":
        result = _host(meta, value)
        if meta.key == "stellarium.host" and not is_loopback_host(result):
            warning = (
                "reachable from the network: Stellarium on another computer can drive the mount"
            )
    elif meta.type == "path":
        result, warning = _path(meta, value)
    elif meta.key == "site.favorites":
        result = _favorites(value)
    elif meta.key == "camera.egain_table":
        result = _egain_table(value)
    else:  # pragma: no cover - every list/object key is handled above
        raise InvalidValue("cannot be set")
    _check_options(meta, result)
    return result, warning
