"""Light-curve accumulator + CSV export (docs/photometry_plan.md §6 C3).

One :class:`LightCurve` per target; points are appended as subs are measured and
written to ``photometry.csv`` (the hand-off to post-processing). Qt-free.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

_COLUMNS = (
    "jd_utc",
    "mag",
    "mag_err",
    "airmass",
    "fwhm",
    "sky_adu",
    "comps_used",
    "saturated",
)


@dataclass
class LcPoint:
    """One light-curve point (exposure-midpoint JD_UTC)."""

    jd_utc: float
    mag: float
    mag_err: float
    airmass: float | None = None
    fwhm: float | None = None
    sky_adu: float | None = None
    comps_used: int = 0
    saturated: bool = False


@dataclass
class LightCurve:
    """A target's differential light curve (preview)."""

    auid: str = ""
    name: str = ""
    points: list[LcPoint] = field(default_factory=list)

    def append(self, point: LcPoint) -> None:
        self.points.append(point)

    def to_csv(self, path) -> None:
        """Write the curve to ``path`` (parent dirs created)."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(_COLUMNS)
            for p in self.points:
                writer.writerow(
                    [
                        p.jd_utc,
                        p.mag,
                        p.mag_err,
                        "" if p.airmass is None else p.airmass,
                        "" if p.fwhm is None else p.fwhm,
                        "" if p.sky_adu is None else p.sky_adu,
                        p.comps_used,
                        int(p.saturated),
                    ]
                )
