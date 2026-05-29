"""ASCOM Alpaca telescope wrapper — backed by alpyca.

Uses the official alpyca library (ASCOM Initiative) instead of raw HTTP
calls. Key benefits:
  - Automatic ImageBytes support (8x faster image transfers)
  - Typed exceptions with error codes
  - Thread-safe (safe to call from QThread workers)

All methods are synchronous and must run inside a QThread worker.
Never call them from the Qt main thread.

Seestar S30 Pro known limitations:
  - SlewToAltAzAsync→ DriverException (error 1024) — not implemented
  - Unpark          → does not open the arm physically
  - MoveAxis        → confirmed working on firmware 7.18+ (tested 2026-05)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from alpaca.telescope import Telescope as _AlpacaTelescope
from alpaca.exceptions import DriverException, NotConnectedException

from seercontrol.core.alpaca.client import AlpacaError

logger = logging.getLogger(__name__)


def _wrap(exc: Exception) -> AlpacaError:
    """Convert an alpyca exception into our internal AlpacaError."""
    if isinstance(exc, DriverException):
        return AlpacaError(exc.number, str(exc))
    return AlpacaError(0, str(exc))


@dataclass
class MountPosition:
    """Current pointing position of the mount."""

    ra: float           # Right Ascension in decimal hours (J2000)
    dec: float          # Declination in decimal degrees (J2000)
    altitude: float     # Altitude in degrees
    azimuth: float      # Azimuth in degrees
    tracking: bool      # Tracking enabled
    slewing: bool       # Slew in progress

    def ra_str(self) -> str:
        total_seconds = int(self.ra * 3600)
        h = total_seconds // 3600
        m = (total_seconds % 3600) // 60
        s = total_seconds % 60
        return f"{h:02d}h {m:02d}m {s:02d}s"

    def dec_str(self) -> str:
        sign = "+" if self.dec >= 0 else "-"
        d = abs(self.dec)
        deg = int(d)
        minutes = int((d - deg) * 60)
        seconds = int(((d - deg) * 60 - minutes) * 60)
        return f"{sign}{deg:02d}° {minutes:02d}' {seconds:02d}\""

    def alt_str(self) -> str:
        return f"{self.altitude:.2f}°"

    def az_str(self) -> str:
        return f"{self.azimuth:.2f}°"


class Telescope:
    """ASCOM Alpaca telescope controller, backed by alpyca.

    Args:
        host: IP address of the Seestar.
        port: Alpaca HTTP port (discovered via UDP, typically 4700).
    """

    def __init__(self, host: str, port: int) -> None:
        self._scope = _AlpacaTelescope(f"{host}:{port}", 0)
        self._connected = False
        self._can_slew_async = True

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def connect(self) -> str:
        """Connect to the mount and return its name.

        Sequence:
          1. Connected = True
          2. Sync UTC date (fixes Seestar clock-sync bug on firmware < 3.0.2)
          3. Check CanSlewAsync

        Raises:
            AlpacaError: Connection or device error.
        """
        try:
            self._scope.Connected = True
        except Exception as exc:
            raise _wrap(exc) from exc

        self._connected = True

        # Sync clock — fixes GoTo failures on firmware < 3.0.2
        # Follow NINA's pattern: try reading first; some mounts require a write before the first read.
        try:
            utc_now = datetime.now(timezone.utc)
            utc_str = utc_now.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
            try:
                mount_utc = self._scope.UTCDate
                diff = abs((mount_utc - utc_now.replace(tzinfo=None)).total_seconds())
                logger.info("Mount UTC: %s  System UTC: %s  diff=%.1fs", mount_utc, utc_now, diff)
                if diff > 10:
                    logger.warning("Mount clock is %.1f seconds off — syncing", diff)
            except Exception:
                logger.debug("UTCDate read failed — writing first (some firmware requires this)")
            self._scope.UTCDate = utc_str
            logger.info("UTC date synced: %s", utc_str)
        except Exception as exc:
            logger.warning("UTC date sync failed (non-fatal): %s", exc)

        try:
            self._can_slew_async = bool(self._scope.CanSlewAsync)
            if not self._can_slew_async:
                logger.warning("Mount reports CanSlewAsync=False — will poll Slewing property")
        except Exception:
            self._can_slew_async = True

        try:
            from alpaca.telescope import TelescopeAxes
            can_primary = self._scope.CanMoveAxis(TelescopeAxes.axisPrimary)
            can_secondary = self._scope.CanMoveAxis(TelescopeAxes.axisSecondary)
            logger.info("CanMoveAxis Primary=%s Secondary=%s", can_primary, can_secondary)
        except Exception as exc:
            logger.debug("CanMoveAxis query failed (non-fatal): %s", exc)

        try:
            name = self._scope.Name or "Unknown"
        except Exception:
            name = "Unknown"

        logger.info("Telescope connected: %s (CanSlewAsync=%s)", name, self._can_slew_async)
        return name

    def disconnect(self) -> None:
        """Disconnect from the mount."""
        try:
            self._scope.Connected = False
        except Exception as exc:
            logger.warning("Error during disconnect: %s", exc)
        finally:
            self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def get_position(self) -> MountPosition:
        """Read the current position from the mount.

        Raises:
            AlpacaError: Communication or device error.
        """
        try:
            return MountPosition(
                ra=float(self._scope.RightAscension),
                dec=float(self._scope.Declination),
                altitude=float(self._scope.Altitude),
                azimuth=float(self._scope.Azimuth),
                tracking=bool(self._scope.Tracking),
                slewing=bool(self._scope.Slewing),
            )
        except Exception as exc:
            raise _wrap(exc) from exc

    def get_altaz(self) -> tuple[float, float]:
        """Return current (altitude, azimuth) in degrees."""
        try:
            return float(self._scope.Altitude), float(self._scope.Azimuth)
        except Exception as exc:
            raise _wrap(exc) from exc

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    def slew_to(self, ra: float, dec: float) -> None:
        """Start an asynchronous GoTo slew (mirrors NINA sequence).

        1. Check AtPark — raise if parked
        2. Enable tracking
        3. Set TargetRightAscension / TargetDeclination (log failures, don't hide them)
        4. Call SlewToCoordinatesAsync
        5. Verify Slewing=True was set (warn if not — some mounts report False when
           already at target, which is acceptable)

        Args:
            ra:  Target RA in decimal hours (J2000), 0–24.
            dec: Target Dec in decimal degrees (J2000), -90 to +90.

        Raises:
            AlpacaError: Mount parked or slew rejected.
        """
        import time

        try:
            if self._scope.AtPark:
                raise AlpacaError(0, "Mount is parked — unpark before slewing")

            # Tracking must be enabled BEFORE setting targets
            logger.info("Enabling tracking")
            self._scope.Tracking = True

            # Set target coordinates — log if unsupported, but continue
            try:
                self._scope.TargetRightAscension = ra
                self._scope.TargetDeclination = dec
                logger.info("Target set: RA=%.6f Dec=%.6f", ra, dec)
            except Exception as exc:
                logger.warning("TargetRA/Dec not writable on this firmware: %s", exc)

            logger.info("SlewToCoordinatesAsync RA=%.6f Dec=%.6f", ra, dec)
            self._scope.SlewToCoordinatesAsync(ra, dec)

            # Brief delay then verify slew started
            time.sleep(0.3)
            if not self._scope.Slewing:
                logger.warning(
                    "Mount did not report Slewing=True — already at target or slew rejected"
                )

            # For synchronous mounts (CanSlewAsync=False): poll until slew completes (NINA pattern)
            if not self._can_slew_async:
                deadline = time.time() + 300.0
                while self._scope.Slewing and time.time() < deadline:
                    time.sleep(1.0)
                if time.time() >= deadline:
                    logger.error("Slew timeout after 300s")
                else:
                    logger.info("Slew complete (sync-mount polling)")

        except AlpacaError:
            raise
        except Exception as exc:
            raise _wrap(exc) from exc

    def set_tracking(self, enabled: bool) -> None:
        """Enable or disable sidereal tracking."""
        try:
            self._scope.Tracking = enabled
            logger.info("Tracking: %s", enabled)
        except Exception as exc:
            raise _wrap(exc) from exc

    def abort_slew(self) -> None:
        """Immediately stop any ongoing slew."""
        try:
            self._scope.AbortSlew()
            logger.info("Slew aborted")
        except Exception as exc:
            raise _wrap(exc) from exc

    def is_parked(self) -> bool:
        """Return True if the mount reports being parked."""
        try:
            return bool(self._scope.AtPark)
        except Exception as exc:
            raise _wrap(exc) from exc

    def park(self) -> None:
        """Park the mount (closes the mechanical arm on Seestar S30 Pro).

        If atpark=True (e.g. native app opened arm without Alpaca Unpark),
        sends Unpark first so the subsequent Park triggers physical movement.

        Raises:
            AlpacaError: Mount does not support Park, or driver error.
        """
        try:
            if not self._scope.CanPark:
                raise AlpacaError(0, "Mount does not support Park")

            if self._scope.AtPark:
                logger.info("Mount reports already parked — sending Unpark first")
                self._scope.Unpark()

            logger.info("Park command sent")
            self._scope.Park()
        except AlpacaError:
            raise
        except Exception as exc:
            raise _wrap(exc) from exc

    def unpark(self) -> None:
        """Unpark via Alpaca.

        Note: does not open the arm physically on the Seestar S30 Pro.
        """
        try:
            self._scope.Unpark()
            logger.info("Unpark sent")
        except Exception as exc:
            raise _wrap(exc) from exc

    def sync_to(self, ra: float, dec: float) -> None:
        """Sync the mount's pointing model to the given coordinates.

        Used after plate solving to correct the pointing model.

        Raises:
            AlpacaError: Tracking not enabled, or sync rejected by mount.
        """
        try:
            if not self._scope.Tracking:
                raise AlpacaError(0, "Tracking must be enabled before syncing — enable tracking first")
            logger.info("Syncing to RA=%.6f Dec=%.6f", ra, dec)
            self._scope.SyncToCoordinates(ra, dec)
        except AlpacaError:
            raise
        except Exception as exc:
            raise _wrap(exc) from exc

    def move_axis(self, axis: int, rate: float) -> None:
        """Start continuous jog on one axis at the given rate (deg/s).

        The mount keeps moving until ``stop_axis()`` is called.

        Args:
            axis: 0 = Primary (RA/Az), 1 = Secondary (Dec/Alt).
            rate: Speed in deg/s. Positive = North/East, negative = South/West.
                  Pass 0.0 to stop.

        Raises:
            AlpacaError: Device error or axis not supported.
        """
        try:
            from alpaca.telescope import TelescopeAxes
            ax = TelescopeAxes.axisPrimary if axis == 0 else TelescopeAxes.axisSecondary
            self._scope.MoveAxis(ax, rate)
            logger.debug("MoveAxis axis=%d rate=%.3f", axis, rate)
        except Exception as exc:
            raise _wrap(exc) from exc

    def stop_axis(self, axis: int) -> None:
        """Stop a jogging axis (sets rate to 0).

        Args:
            axis: 0 = Primary (RA/Az), 1 = Secondary (Dec/Alt).
        """
        self.move_axis(axis, 0.0)

    def pulse_guide(self, direction: int, duration_ms: int) -> None:
        """Send a PulseGuide command (guide-rate only — not for manual jogging).

        Args:
            direction: 0=North, 1=South, 2=East, 3=West (ASCOM constants).
            duration_ms: Duration in milliseconds.
        """
        try:
            self._scope.PulseGuide(direction, duration_ms)
        except Exception as exc:
            raise _wrap(exc) from exc

    # ------------------------------------------------------------------
    # Tracking rate, target hint, side of pier
    # ------------------------------------------------------------------

    def set_tracking_rate(self, rate: int) -> None:
        """Select the tracking rate model.

        Args:
            rate: ASCOM ``DriveRates`` enum value:
                  0=Sidereal, 1=Lunar, 2=Solar, 3=King.

        Raises:
            AlpacaError: Mount rejected the rate (e.g. only Sidereal supported).
        """
        try:
            from alpaca.telescope import DriveRates
            self._scope.TrackingRate = DriveRates(rate)
            logger.info("Tracking rate set to %s", DriveRates(rate).name)
        except Exception as exc:
            raise _wrap(exc) from exc

    def get_tracking_rate(self) -> int | None:
        """Return the current ASCOM ``DriveRates`` value, or None if unsupported."""
        try:
            return int(self._scope.TrackingRate)
        except Exception as exc:
            logger.debug("TrackingRate read failed: %s", exc)
            return None

    def set_target(self, ra: float, dec: float) -> None:
        """Set the mount's TargetRightAscension/TargetDeclination without slewing.

        Useful before a slew or sync so the mount's pointing model records what
        we were aiming at — independent of the actual pointing it eventually
        achieves. Failures are logged and re-raised; some firmwares do not allow
        writing these properties (in which case the slew code path tolerates
        the failure on its own).
        """
        try:
            self._scope.TargetRightAscension = ra
            self._scope.TargetDeclination = dec
            logger.debug("Target hint set: RA=%.6f Dec=%.6f", ra, dec)
        except Exception as exc:
            raise _wrap(exc) from exc

    def side_of_pier(self) -> str | None:
        """Return 'EAST' / 'WEST' / 'UNKNOWN', or None if the mount can't tell.

        For an alt-az like the Seestar this concept is meaningless — the
        property may simply not be exposed.
        """
        try:
            value = int(self._scope.SideOfPier)
        except Exception:
            return None
        # ASCOM PierSide: -1 unknown, 0 east, 1 west
        return {0: "EAST", 1: "WEST"}.get(value, "UNKNOWN")
