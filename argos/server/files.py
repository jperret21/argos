"""Review's frame inspector on files (rows A71-A75): pixels, header, measure, solve, catalogue.

Qt-free ports of the Frame Viewer (``argos/ui/analysis_window.py``) over the
unchanged core and the wave 4 server ports, for any FITS file the observer may
browse; nothing is published on ``/ws/frames`` (the live image stays) and no
file is written.

- A71 :meth:`FileService.frame_bytes`: ``load_fits_frame`` (the v1 Open FITS
  display conversions) encoded in the ``/ws/frames`` layout (``frames.py``).
- A72 :meth:`FileService.header`: ``read_fits_header_text`` and
  ``read_fits_meta`` (``analysis_window.py:68-133``).
- A73 :meth:`FileService.measure`: ``measure_star_at`` (``metrics.py:225-276``)
  on the array of ``read_fits_2d`` (``analysis_window.py:54-65``), the
  Frame Viewer's click (``_on_star_clicked`` / ``_remeasure_selection``,
  ``analysis_window.py:874-899``) through ``FrameMeasurer`` (identical numbers,
  the green plane and sky computed once per file).
- A74 :meth:`FileService.start_solve`: ``_on_solve`` / ``_on_solved``
  (``analysis_window.py:460-505``) with ``build_solve_settings(live=False)``,
  ``wcs_from_result``, ``overlay_for``; ASTAP through ``field_solve.solve_green``
  (killed on cancel).
- A75 :meth:`FileService.start_catalogue`: ``_fetch_field_catalogues``
  (``analysis_window.py:588-629``) with ``field_catalog.run_request`` and the
  Observe projection ``project_field``.
"""

from __future__ import annotations

import logging
import math
import threading
from collections import OrderedDict
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

from argos.core import catalog as core_catalog
from argos.core.catalog.targets import ROLE_TARGET, TargetSet
from argos.core.hardware import active
from argos.core.imaging.astrometry_session import (
    build_solve_settings,
    full_res_scale,
    overlay_for,
    wcs_from_result,
)
from argos.core.imaging.green import green_plane
from argos.core.imaging.metrics import TRACK_SNAP_SEARCH, arcsec_per_green_px
from argos.core.imaging.platesolve import format_dec_dms, format_ra_hms
from argos.server import field_catalog as fc
from argos.server.capture import fits_exposure_mid
from argos.server.errors import ApiError
from argos.server.field_measure import FrameMeasurer
from argos.server.field_solve import (
    SolveCancelled,
    frame_shape_of,
    frame_wcs_record,
    grid_record,
    header_hint,
    solve_green,
    to_frame,
    to_green,
    wire_mirrored,
)
from argos.server.fits_source import (
    FITS_SUFFIXES,
    MAX_ELEMENTS,
    MAX_SIDE,
    FitsReadError,
    load_fits_frame,
)
from argos.server.frames import encode_frame
from argos.server.jobs import JobCancelled, JobContext
from argos.server.state import utc_iso

if TYPE_CHECKING:  # pragma: no cover
    from argos.server.hub import Hub

logger = logging.getLogger(__name__)

#: Keywords of ``read_fits_meta`` (``analysis_window.py:68-123``), in its order.
META_KEYS = (
    "OBJECT",
    "DATE-OBS",
    "EXPTIME",
    "EXPOSURE",
    "IMAGETYP",
    "FILTER",
    "GAIN",
    "INSTRUME",
    "OBSERVER",
    "SITENAME",
    "CRPIX1",
    "CRPIX2",
    "CRVAL1",
    "CRVAL2",
    "CD1_1",
    "CD2_2",
    "CCD-TEMP",
    "HFD",
    "FWHM",
    "NSTARS",
    "SKYLEVEL",
    "PEAKADU",
    "ECCENT",
    "EGAIN",
    "RDNOISE",
    "AIRMASS",
    "MOONSEP",
    "FRAME",
    "FRAMENO",
    "IMGNUM",
    "NFRAMES",
    "SEQUENCE",
    "ORIGIN",
)
#: Solutions kept (one per file).
_SOLUTIONS = 16
#: Poll period while a catalogue query runs (cancel latency).
_POLL_S = 0.1


def _stamp(path: Path) -> tuple[int, int] | None:
    try:
        st = path.stat()
    except OSError:
        return None
    return (st.st_mtime_ns, st.st_size)


def _num(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _json_value(value: Any) -> Any:
    """A header value as a JSON scalar (astropy's undefined value becomes null)."""
    if isinstance(value, (bool, int, str)) or value is None:
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return _num(value)
    if isinstance(value, complex):
        return str(value)
    return None if type(value).__name__ == "Undefined" else str(value)


def _check_size(header) -> None:
    naxis = int(header.get("NAXIS", 0) or 0)
    axes = [int(header.get(f"NAXIS{i}", 0) or 0) for i in range(1, naxis + 1)]
    if not axes:
        return
    elements = int(np.prod(axes, dtype=np.int64))
    if elements > MAX_ELEMENTS or max(sorted(axes)[-2:]) > MAX_SIDE:
        shape = "×".join(str(n) for n in axes)
        raise FitsReadError(
            f"image too large to display ({shape}; limits {MAX_SIDE} px per side, "
            f"{MAX_ELEMENTS // 1_000_000} M samples)"
        )


def read_fits_2d(path: Path) -> np.ndarray | None:
    """``read_fits_2d`` (``analysis_window.py:54-65``): float32, NaN zeroed, a cube averaged.

    The first image HDU, chosen from the headers and its size checked before the
    pixels are read (touching ``.data`` loads them: a 17 000 px frame cost 400 MB
    before it was refused, W7 technical review), as ``fits_source.load_fits_frame``.
    """
    from astropy.io import fits

    with fits.open(path, memmap=False) as hdul:
        hdu = next(
            (
                h
                for h in hdul
                if getattr(h, "is_image", False) and int(h.header.get("NAXIS", 0) or 0) > 0
            ),
            None,
        )
        if hdu is None:
            return None
        _check_size(hdu.header)
        data = hdu.data
        if data is None:
            return None
    arr = np.nan_to_num(np.asarray(data, dtype=np.float32), nan=0.0)
    if arr.ndim == 3:
        arr = arr.mean(axis=0) if arr.shape[0] <= 4 else arr.mean(axis=2)
    return arr if arr.ndim == 2 else None


def to_counts(arr: np.ndarray) -> tuple[np.ndarray, bool]:
    """A calibrated float frame in [0, 1] (Siril, PixInsight) scaled by 65535.

    As the display (``fits_source._to_uint16``) and the Frame Viewer (S65) do, so a
    measurement reads counts (an unscaled one gave SNR 0, peak 0) and ASTAP sees a
    visible plane. Returns the array and whether it was scaled.
    """
    peak = float(np.max(arr)) if arr.size else 0.0
    if 0.0 < peak <= 1.0:
        return arr * np.float32(65535.0), True
    return arr, False


def read_primary_header(path: Path):
    """The primary header, or :class:`FitsReadError`."""
    from astropy.io import fits

    try:
        return fits.getheader(path, 0)
    except Exception as exc:
        raise FitsReadError(f"not a readable FITS file ({exc})") from exc


def read_fits_meta(header) -> dict[str, str]:
    """``read_fits_meta`` (``analysis_window.py:68-123``) on a read header."""
    return {key: str(header[key]).strip() for key in META_KEYS if key in header}


def header_text(header) -> str:
    """The header one card per line, ``END`` last (Qt showed ``str(header)``: the same
    cards run together on one line)."""
    return header.tostring(sep="\n", endcard=True, padding=False).rstrip()


def _session_targets(path: Path) -> TargetSet:
    """``_load_session_targets`` (``analysis_window.py:343-348``)."""
    for folder in (path.parent, *path.parents):
        if (folder / "session.json").is_file():
            return TargetSet.load(folder / "targets.json")
    return TargetSet()


@dataclass
class FileSolution:
    stamp: tuple[int, int] | None
    wcs: Any  # FrameWCS, green px
    green_shape: tuple[int, int]
    record: dict[str, Any]


class FileService:
    """Frame-inspector tools on files (rows A71-A75); thread-safe."""

    def __init__(self, hub: "Hub") -> None:
        self._hub = hub
        self._lock = threading.Lock()
        self._seq = 0
        #: The last measured file: ``(path, stamp, FrameMeasurer)`` (one, for memory).
        self._measurer: tuple[str, Any, FrameMeasurer] | None = None
        self._solutions: "OrderedDict[str, FileSolution]" = OrderedDict()
        #: The catalogue query functions (``argos.core.catalog``; tests replace them).
        self.catalog_api: Any = core_catalog

    # -- paths -----------------------------------------------------------------------

    def resolve(self, raw: str) -> Path:
        real, _root = self._hub.fs_roots.resolve(raw, what="FITS file")
        if real.suffix.lower() not in FITS_SUFFIXES:
            raise ApiError(400, "invalid_argument", f"{real.name} is not a .fit/.fits/.fts file")
        if not real.is_file():
            raise ApiError(404, "not_found", f"No file {real}")
        return real

    def _cfg(self, key: str, default: Any) -> Any:
        value = self._hub.config.get(key, default)
        return default if value is None else value

    # -- A71 -------------------------------------------------------------------------

    def frame_bytes(self, raw: str, view: str = "raw") -> bytes:
        if view != "raw":
            raise ApiError(
                400,
                "invalid_argument",
                "view must be raw: the colour and channel previews are made by the viewer",
            )
        path = self.resolve(raw)
        try:
            header = read_primary_header(path)
            pixels, exposure_s, timestamp = load_fits_frame(path)
        except FitsReadError as exc:
            raise ApiError(400, "invalid_fits", f"{path.name}: {exc}") from exc
        bitpix = int(header.get("BITPIX", 0) or 0)
        two_d = pixels.ndim == 2
        bayer = header.get("BAYERPAT")
        if bayer:
            bayer = str(bayer).strip() or None
        elif two_d and bitpix in (8, 16):
            bayer = active.profile().bayer_pattern
        else:
            bayer = None
        mid = fits_exposure_mid(header)
        date_obs = header.get("DATE-OBS")
        with self._lock:
            self._seq += 1
            seq = self._seq
        extra = {
            "origin": "file",
            "path": str(path),
            "file_name": path.name,
            "date_obs": str(date_obs).strip() if date_obs else None,
            "epoch_utc": utc_iso(mid) if mid is not None else None,
            "bayer": bayer,
            "filter": _json_value(header.get("FILTER")),
            "image_type": _json_value(header.get("IMAGETYP")),
            "object": _json_value(header.get("OBJECT")),
            "green_shape": [int(pixels.shape[0]) // 2, int(pixels.shape[1]) // 2],
            "raw": bool(two_d and bitpix in (8, 16)),
        }
        return encode_frame(
            pixels,
            seq=seq,
            exposure_s=exposure_s,
            timestamp=timestamp,
            source="file",
            extra=extra,
        )

    # -- A72 -------------------------------------------------------------------------

    def header(self, raw: str) -> dict[str, Any]:
        path = self.resolve(raw)
        try:
            header = read_primary_header(path)
        except FitsReadError as exc:
            raise ApiError(400, "invalid_fits", f"{path.name}: {exc}") from exc
        cards = []
        for card in header.cards:
            cards.append(
                {"key": card.keyword, "value": _json_value(card.value), "comment": card.comment}
            )
        return {
            "path": str(path),
            "file_name": path.name,
            "text": header_text(header),
            "cards": cards,
            "keywords": read_fits_meta(header),
        }

    # -- A73 -------------------------------------------------------------------------

    def _frame_measurer(self, path: Path) -> FrameMeasurer:
        stamp = _stamp(path)
        with self._lock:
            held = self._measurer
        if held is not None and held[0] == str(path) and held[1] == stamp:
            return held[2]
        try:
            arr = read_fits_2d(path)
        except FitsReadError as exc:
            raise ApiError(400, "invalid_fits", f"{path.name}: {exc}") from exc
        except Exception as exc:
            raise ApiError(400, "invalid_fits", f"{path.name}: not a readable FITS image") from exc
        if arr is None:
            raise ApiError(400, "invalid_fits", f"{path.name}: no 2-D image in the file")
        arr, scaled = to_counts(arr)
        measurer = FrameMeasurer(arr)
        measurer.scaled = scaled  # type: ignore[attr-defined]
        with self._lock:
            self._measurer = (str(path), stamp, measurer)
        return measurer

    def measure(
        self, raw: str, x: float, y: float, radius: int | None = None, snap: bool = True
    ) -> dict[str, Any]:
        path = self.resolve(raw)
        measurer = self._frame_measurer(path)
        h, w = measurer.raw.shape
        if not (0.0 <= x < w and 0.0 <= y < h):
            raise ApiError(400, "invalid_argument", f"({x:g}, {y:g}) is outside the {w}×{h} frame")
        gx, gy = to_green(x, y)
        r = int(radius) if radius is not None else self._hub._star_radius()
        meas = measurer.measure_star_at(gx, gy, r, search=None if snap else TRACK_SNAP_SEARCH)
        if meas is None:
            return {"found": False, "message": f"No star near ({x:.0f}, {y:.0f})."}
        solution = self._solution(path)
        scale_green = None
        if solution is not None:
            scale_green = _green_scale_arcsec(solution.wcs)
        scale_source = "solution" if scale_green else "profile"
        scale_green = scale_green or arcsec_per_green_px()
        fx, fy = to_frame(meas.x, meas.y)
        ra = dec = None
        if solution is not None:
            ra, dec = solution.wcs.pixel_to_radec(meas.x, meas.y)
        return {
            "found": True,
            "message": None,
            "x": round(fx, 2),
            "y": round(fy, 2),
            "x_green": float(meas.x),
            "y_green": float(meas.y),
            "fwhm_px": 2.0 * meas.fwhm if meas.fwhm is not None else None,
            "hfd_px": 2.0 * meas.hfd if meas.hfd is not None else None,
            "fwhm_arcsec": meas.fwhm * scale_green if meas.fwhm is not None else None,
            "hfd_arcsec": meas.hfd * scale_green if meas.hfd is not None else None,
            "scale_arcsec_px": scale_green / 2.0,
            "scale_source": scale_source,
            "eccentricity": _num(meas.eccentricity),
            "snr": float(meas.snr),
            "peak_adu": int(meas.peak_adu),
            "sky_adu": float(meas.sky_adu),
            "flux": float(meas.flux),
            "radius_green_px": int(meas.radius),
            "scale": "converted" if getattr(measurer, "scaled", False) else "raw",
            "ra_hours": float(ra) if ra is not None else None,
            "dec_deg": float(dec) if dec is not None else None,
            "ra_text": format_ra_hms(ra) if ra is not None else None,
            "dec_text": format_dec_dms(dec) if dec is not None else None,
        }

    # -- A74 -------------------------------------------------------------------------

    def _solution(self, path: Path) -> FileSolution | None:
        with self._lock:
            held = self._solutions.get(str(path))
        if held is None or held.stamp != _stamp(path):
            return None
        return held

    def solution(self, raw: str) -> dict[str, Any]:
        path = self.resolve(raw)
        held = self._solution(path)
        if held is None:
            raise ApiError(404, "not_found", f"{path.name} has not been solved")
        return held.record

    def start_solve(self, raw: str) -> dict[str, Any]:
        path = self.resolve(raw)

        def run(ctx: JobContext) -> dict[str, Any]:
            return self._solve(path, ctx)

        return self._hub.jobs.start("file_solve", run, resource=str(path), stage="reading")

    def _solve(self, path: Path, ctx: JobContext) -> dict[str, Any]:
        stamp = _stamp(path)
        try:
            header = read_primary_header(path)
            arr = read_fits_2d(path)
        except FitsReadError as exc:
            raise ApiError(400, "invalid_fits", f"{path.name}: {exc}") from exc
        except Exception as exc:  # a truncated file: astropy's ValueError (reshape)
            raise ApiError(400, "invalid_fits", f"{path.name}: not a readable FITS image") from exc
        if arr is None:
            raise ApiError(400, "invalid_fits", f"{path.name}: no 2-D image in the file")
        ctx.check()
        # A calibrated float frame in [0, 1] (Siril) is scaled as the display does
        # (fits_source._to_uint16), else ASTAP would see a black plane.
        arr, _scaled = to_counts(arr)
        green = np.clip(green_plane(arr), 0, 65535)
        gs = (int(green.shape[0]), int(green.shape[1]))
        hint = header_hint(header)
        settings = build_solve_settings(self._cfg, gs, live=False, mount_radec=hint)
        hint_text = (
            f"(hint RA {hint[0]:.3f}h Dec {hint[1]:+.2f}° from the FITS header)"
            if hint
            else "(blind)"
        )
        self._hub.log(
            "cmd",
            f"Plate-solving {path.name}… {hint_text}",
            source="review",
            topic="field",
        )
        try:
            result = solve_green(
                green, settings, ctx.cancel_event, progress=lambda text: ctx.progress(stage=text)
            )
            # A cancel that came as ASTAP was ending still cancels: nothing is kept.
            ctx.check()
        except (SolveCancelled, JobCancelled):
            self._hub.log("info", f"Solving {path.name} cancelled.", source="review", topic="field")
            raise JobCancelled() from None
        if not result.solved:
            message = result.message or "ASTAP found no solution"
            self._hub.log(
                "error", f"{path.name}: field not identified — {message}", source="review"
            )
            raise ApiError(422, "not_solved", message)
        wcs = wcs_from_result(result, gs)
        if wcs is None or _green_scale_arcsec(wcs) is None:
            raise ApiError(422, "not_solved", "the solution could not be used (no valid WCS)")
        overlay = overlay_for(wcs, gs, self._cfg)
        scale = full_res_scale(result)
        bits = [f"RA {result.ra_hours:.4f}h", f"Dec {result.dec_deg:+.4f}°"]
        if scale is not None:
            bits.append(f"{scale:.2f}″/px")
        if result.rotation_deg is not None:
            bits.append(f"rot {result.rotation_deg:.1f}°")
        summary = "Field identified — " + "   ".join(bits)  # analysis_window.py:486-494
        record = {
            "path": str(path),
            "file_name": path.name,
            "solution": {
                "ra_hours": _num(result.ra_hours),
                "dec_deg": _num(result.dec_deg),
                "scale_arcsec_px": _num(scale),
                "rotation_deg": _num(result.rotation_deg),
                "mirrored": wire_mirrored(wcs),
                "frame_shape": frame_shape_of(gs),
                "hint": (
                    {"ra_hours": hint[0], "dec_deg": hint[1], "source": "header"} if hint else None
                ),
                "solved_utc": utc_iso(),
                "summary": summary,
            },
            "wcs": frame_wcs_record(wcs, gs),
            "grid": grid_record(overlay),
        }
        with self._lock:
            self._solutions[str(path)] = FileSolution(stamp, wcs, gs, record)
            self._solutions.move_to_end(str(path))
            while len(self._solutions) > _SOLUTIONS:
                self._solutions.popitem(last=False)
        self._hub.log("ok", f"{path.name}: {summary}", source="review", topic="field")
        return record

    # -- A75 -------------------------------------------------------------------------

    def start_catalogue(self, raw: str) -> dict[str, Any]:
        path = self.resolve(raw)
        solution = self._solution(path)
        if solution is None:
            raise ApiError(
                409,
                "not_solved",
                "Identify the field first: the catalogue is fetched around a plate solution.",
            )

        def run(ctx: JobContext) -> dict[str, Any]:
            return self._catalogue(path, solution, ctx)

        return self._hub.jobs.start("file_catalogue", run, resource=str(path), stage="querying")

    def _catalogue(self, path: Path, solution: FileSolution, ctx: JobContext) -> dict[str, Any]:
        cfg = self._cfg
        tset = _session_targets(path)
        target = next(iter(tset.by_role(ROLE_TARGET)), None)
        request = fc.build_request(cfg, solution.wcs, solution.green_shape, target)
        if request is None:
            raise ApiError(422, "not_solved", "the solution gives no field geometry")
        if target is None:  # analysis_window.py:612-614: the header's OBJECT names the field
            try:
                obj = read_primary_header(path).get("OBJECT")
            except FitsReadError:
                obj = None
            request = replace(request, comparison_target_name=str(obj).strip() if obj else None)
        box: dict[str, Any] = {}
        done = threading.Event()

        def fetch() -> None:
            try:
                box["result"] = fc.run_request(request, self.catalog_api)
            except BaseException as exc:  # pragma: no cover - run_request catches its own
                box["error"] = exc
            finally:
                done.set()

        threading.Thread(target=fetch, name="argos-file-catalogue", daemon=True).start()
        while not done.wait(_POLL_S):
            ctx.check()  # cancel: the answer, when it comes, is dropped
        ctx.check()
        if "error" in box:
            raise box["error"]
        result = box["result"]
        if not result.ok:
            raise ApiError(502, "lookup_failed", result.error)
        mag_max = float(cfg("catalog.field_stars_mag_limit", 18.0))
        display = float(cfg("catalog.display_mag_limit", mag_max))
        context = fc.FieldContext(
            wcs=solution.wcs, green_shape=solution.green_shape, detected=[], result=result
        )
        # Every fetched Gaia star is sent (the client filters by the display limit,
        # Qt's slider); the counts apply the configured display limit, as Qt's chips.
        projection = fc.project_field(context, cfg, tset, display_mag_limit=mag_max)
        counts = dict(projection.counts)
        counts["stars"] = sum(
            1
            for m in projection.layers["stars"]
            if m.get("g_mag") is None or float(m["g_mag"]) <= display
        )
        ra_deg, dec_deg = request.ra_deg, request.dec_deg
        return {
            "path": str(path),
            "frame_shape": frame_shape_of(solution.green_shape),
            "display_mag_limit": display,
            "layers": projection.layers,
            "counts": counts,
            "catalog": {
                "centre": {"ra_hours": ra_deg / 15.0, "dec_deg": dec_deg},
                "radius_deg": request.radius_deg,
                "counts": {
                    "variables": len(result.variables),
                    "comparisons": len(result.comparisons),
                    "field_stars": len(result.field_stars),
                    "named_objects": len(result.named_objects),
                    "exoplanet_hosts": len(result.exoplanet_hosts),
                },
                "limits": {
                    "field_stars": result.field_star_limit,
                    "named_objects": result.named_object_limit,
                },
                "warnings": [*result.warnings, *result.source_warnings],
            },
        }


def _green_scale_arcsec(wcs) -> float | None:
    """Arcseconds per green px of a solution (its CD matrix), as ``field.py``."""
    try:
        a, b, c, d = (float(v) for v in wcs.cd)
    except (AttributeError, TypeError, ValueError):
        return None
    det = abs(a * d - b * c)
    return math.sqrt(det) * 3600.0 if det > 0 and math.isfinite(det) else None


__all__ = ["FileService", "read_fits_2d", "read_fits_meta", "header_text"]
