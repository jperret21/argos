"""Process-wide effects of the configuration (row A3, part of A9).

The Qt app applies these when its Settings page is built
(``configuration_page.py:823-824``) and when a field changes
(``:1040-1084``), and the log level once in ``main.py:144``. The headless
server applies them at start-up, before the first request, and again on
every config commit that touches them. They change module-level state of
the core, so only a server that owns its process does this
(``Settings.manage_process``); in-process tests leave them alone.
"""

from __future__ import annotations

import logging
import os
import re
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Callable

from argos.core import support_bundle
from argos.core.catalog import aavso, exoplanets, field_objects, gaia, object_resolver
from argos.core.imaging import imx585, sensor_reference

logger = logging.getLogger(__name__)

#: Same bounds as the Qt app's journal (support_bundle.py:30-32).
LOG_FILENAME = "argos.log"
_MAX_LOG_BYTES = 2_000_000
_LOG_BACKUPS = 5

_LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
}


def apply_data_paths(get: Callable[[str, Any], Any]) -> None:
    """Point the core modules at the configured cache and calibration folders.

    Port of ``ConfigurationPage._apply_catalogue_paths`` and
    ``_apply_local_data_paths`` (``configuration_page.py:1040-1084``): same
    targets, same ``expanduser``; nothing is created or read here.
    """

    def path(key: str) -> Path | None:
        value = get(key, None)
        if not isinstance(value, str) or not value.strip():
            return None
        return Path(value.strip()).expanduser()

    object_path = path("data_paths.object_catalogue_cache")
    exoplanet_path = path("data_paths.exoplanet_cache")
    aavso_path = path("data_paths.aavso_cache_directory")
    gaia_path = path("data_paths.gaia_cache_directory")
    field_path = path("data_paths.field_catalogue_cache_directory")
    calibrations = path("data_paths.camera_calibration_directory")
    if object_path is not None:
        object_resolver.configure_cache_path(object_path)
    if exoplanet_path is not None:
        exoplanets.configure_cache_path(exoplanet_path)
    if aavso_path is not None:
        aavso.configure_cache_directory(aavso_path)
    if gaia_path is not None:
        gaia.configure_cache_directory(gaia_path)
    if field_path is not None:
        field_objects.configure_cache_directory(field_path)
        exoplanets.configure_field_cache_directory(field_path)
    if calibrations is not None:
        sensor_reference.configure_calibration_directory(calibrations)
        imx585.configure_calibration_directory(calibrations)


def apply_log_level(level: Any) -> None:
    """``ui.log_level`` for the whole process (``main.py:144``), applied live."""
    name = str(level or "INFO").upper()
    logging.getLogger().setLevel(_LEVELS.get(name, logging.INFO))


class RedactTokens(logging.Filter):
    """Keep the bearer token out of logs (uvicorn logs WebSocket URLs with ``?token=``)."""

    _TOKEN = re.compile(r"(token=)[^&\s\"']+")

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        if "token=" in message:
            record.msg, record.args = self._TOKEN.sub(r"\1***", message), None
        return True


def default_log_dir() -> Path:
    """``$ARGOS_LOG_DIR``, else the platform folder of the Qt app (support_bundle.py:57-64)."""
    env = os.environ.get("ARGOS_LOG_DIR")
    return Path(env).expanduser() if env else support_bundle.diagnostics_directory()


def default_config_dir() -> Path:
    """``$ARGOS_CONFIG_DIR``, else ``~/.argos`` (the Qt app's folder, config.py:16)."""
    env = os.environ.get("ARGOS_CONFIG_DIR")
    return Path(env).expanduser() if env else Path.home() / ".argos"


def add_file_log(directory: Path, formatter: logging.Formatter) -> Path | None:
    """Rotating ``argos.log`` in *directory*, as ``configure_local_logging``.

    ``support_bundle.configure_local_logging`` cannot be reused as is: it
    replaces every root handler (``basicConfig(force=True)``), dropping the
    token redaction and stderr routing the CLI set up. A failure only loses
    the file; the server keeps logging to stderr.
    """
    try:
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / LOG_FILENAME
        handler = RotatingFileHandler(
            path, maxBytes=_MAX_LOG_BYTES, backupCount=_LOG_BACKUPS, encoding="utf-8"
        )
    except OSError as exc:
        logger.warning("Could not open the log file in %s: %s", directory, exc)
        return None
    handler.setFormatter(formatter)
    handler.addFilter(RedactTokens())
    logging.getLogger().addHandler(handler)
    return path


def install_crash_reporter(directory: Path) -> None:
    """Uncaught exceptions of any thread leave a report (support_bundle.py:124-145)."""
    support_bundle.install_crash_reporter(directory)


def python_version() -> str:
    return sys.version.split()[0]
