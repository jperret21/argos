"""Session flight recorder — machine-readable per-frame diagnostics (JSONL).

One line of JSON per record, one file per run, next to the session outputs.
Postprod loads it with ``pandas.read_json(path, lines=True)`` and can audit
what Argos measured and decided on every frame: each comparison star's raw
behaviour, the ensemble zero-point health, the aperture tracker's state, and
sparse session events. The human-oriented log tells the story; this file is
the evidence.

Record shape: ``{"t": iso8601-utc, "kind": ..., ["frame": n,] **fields}``.
Kinds in use: ``star``, ``ensemble``, ``tracking``, ``frame``, ``event``
(see docs/photometry_hardening_plan.md §P11).

Failure-safe by design: the recorder must never take a session down. Any
write error disables it with a single warning; every method is a no-op when
disabled. Qt-free.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

#: Float precision in records — enough for px / mag / deg diagnostics while
#: keeping a night's file in the megabytes.
_NDIGITS = 4


def _clean(value: Any) -> Any:
    """Round floats, recurse containers, and pass through JSON scalars."""
    if isinstance(value, float):
        return round(value, _NDIGITS)
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    return value


class SessionDiagnostics:
    """Append-only JSONL writer for one run (live session or batch re-run).

    The file is opened lazily on the first record so an enabled-but-unused
    recorder leaves nothing behind. It is an opt-in local diagnostic file and
    has no network transport. ``enabled=False`` (config ``diagnostics.enabled``)
    makes every call a no-op.
    """

    def __init__(self, path: Path | str, enabled: bool = True) -> None:
        self._path = Path(path)
        self._enabled = bool(enabled)
        self._fh = None

    @property
    def path(self) -> Path:
        return self._path

    @property
    def enabled(self) -> bool:
        return self._enabled

    def record(self, kind: str, frame: int | None = None, **fields: Any) -> None:
        """Write one record; drops None-valued fields, rounds floats."""
        if not self._enabled:
            return
        doc: dict[str, Any] = {
            "t": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "kind": kind,
        }
        if frame is not None:
            doc["frame"] = int(frame)
        doc.update({k: _clean(v) for k, v in fields.items() if v is not None})
        try:
            if self._fh is None:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                self._fh = open(self._path, "a", encoding="utf-8")
            self._fh.write(json.dumps(doc, ensure_ascii=False) + "\n")
            self._fh.flush()  # a crash must not eat the black box
        except OSError as exc:
            logger.warning("Diagnostics disabled (write failed): %s", exc)
            self._enabled = False
            self._close_quietly()

    def star(self, frame: int, star, phot, x: float, y: float) -> None:
        """One measured star on one frame — target, comparison or check.

        ``star`` is a TargetStar, ``phot`` an AperturePhot or None (aperture
        off-frame). Recording every comparison's *raw* instrumental behaviour
        is the point: a drifting or clouded comp is invisible in the
        calibrated target curve but obvious here.
        """
        self.record(
            "star",
            frame=frame,
            auid=star.auid or None,
            name=star.display_name,
            role=star.role,
            x=float(x),
            y=float(y),
            flux_adu=phot.flux_adu if phot else None,
            sky_adu=phot.sky_adu if phot else None,
            peak_adu=phot.peak_adu if phot else None,
            snr=phot.snr if phot else None,
            inst_mag=phot.inst_mag if phot else None,
            inst_mag_err=phot.inst_mag_err if phot else None,
            saturated=bool(phot.saturated) if phot else None,
            suspect=bool(getattr(phot, "suspect", False)) or None if phot else None,
            measured=phot is not None,
        )

    def close(self) -> None:
        self._close_quietly()

    def _close_quietly(self) -> None:
        if self._fh is not None:
            try:
                self._fh.close()
            except OSError:
                pass
            self._fh = None

    def __enter__(self) -> "SessionDiagnostics":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()
