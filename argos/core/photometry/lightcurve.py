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
    "bjd_tdb",
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
    """One light-curve point (exposure-midpoint JD_UTC; BJD_TDB when site known)."""

    jd_utc: float
    mag: float
    mag_err: float
    bjd_tdb: float | None = None
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
                        "" if p.bjd_tdb is None else p.bjd_tdb,
                        p.mag,
                        p.mag_err,
                        "" if p.airmass is None else p.airmass,
                        "" if p.fwhm is None else p.fwhm,
                        "" if p.sky_adu is None else p.sky_adu,
                        p.comps_used,
                        int(p.saturated),
                    ]
                )

    def to_aavso(self, path, **kwargs) -> None:
        """Write this curve in AAVSO Extended File Format (ensemble photometry)."""
        write_aavso(path, [self], **kwargs)

    @classmethod
    def from_csv(cls, path, auid: str = "", name: str = "") -> "LightCurve":
        """Reload a curve written by :meth:`to_csv` (round-trips it).

        Lets a finished session be reopened for review/export without re-running
        the night. Unknown/blank optional columns become ``None``; unparseable
        rows are skipped rather than raising, so a partial file still loads.
        """
        path = Path(path)
        lc = cls(auid=auid, name=name or Path(path).stem)
        with path.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                try:
                    lc.append(
                        LcPoint(
                            jd_utc=float(row["jd_utc"]),
                            mag=float(row["mag"]),
                            mag_err=float(row["mag_err"]),
                            bjd_tdb=_opt_float(row.get("bjd_tdb")),
                            airmass=_opt_float(row.get("airmass")),
                            fwhm=_opt_float(row.get("fwhm")),
                            sky_adu=_opt_float(row.get("sky_adu")),
                            comps_used=int(row.get("comps_used") or 0),
                            saturated=bool(int(row.get("saturated") or 0)),
                        )
                    )
                except (TypeError, ValueError):
                    continue
        return lc


def _opt_float(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def write_aavso(path, curves, *, obscode: str = "XXX", filt: str = "TG",
                software: str = "Argos") -> None:
    """Write one or more :class:`LightCurve` to an AAVSO Extended File.

    A *preview* export — DATE is the JD_UTC midpoint, MTYPE=STD, comparison is the
    ensemble (CNAME=ENSEMBLE). Calibrated mags + BJD_TDB come from post-processing.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        f.write("#TYPE=EXTENDED\n")
        f.write(f"#OBSCODE={obscode}\n")
        f.write(f"#SOFTWARE={software}\n")
        f.write("#DELIM=,\n#DATE=JD\n#OBSTYPE=CCD\n")
        f.write(
            "#NAME,DATE,MAG,MERR,FILT,TRANS,MTYPE,CNAME,CMAG,KNAME,KMAG,"
            "AMASS,GROUP,CHART,NOTES\n"
        )
        for lc in curves:
            name = (lc.name or lc.auid or "TARGET").upper()
            for p in lc.points:
                amass = "na" if p.airmass is None else f"{p.airmass:.3f}"
                f.write(
                    f"{name},{p.jd_utc:.6f},{p.mag:.4f},{p.mag_err:.4f},{filt},NO,STD,"
                    f"ENSEMBLE,na,na,na,{amass},na,na,na\n"
                )
