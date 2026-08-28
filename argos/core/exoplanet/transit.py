"""Predict transit coverage and make cadence-preserving acquisition plans.

All event times are BJD_TDB.  This module deliberately does not fit a transit,
reduce frames, or change their calibration: those are external post-processing
responsibilities.
"""

from __future__ import annotations

from dataclasses import dataclass
import math

from argos.core.catalog.exoplanets import ExoplanetTarget
from argos.core.imaging.sequencer import SequencePlan, SequenceStep


@dataclass(frozen=True)
class TransitWindow:
    """One predicted event and the requested pre/post-transit baseline."""

    epoch_number: int
    mid_bjd_tdb: float
    ingress_bjd_tdb: float
    egress_bjd_tdb: float
    coverage_start_bjd_tdb: float
    coverage_end_bjd_tdb: float
    baseline_minutes: float

    @property
    def coverage_hours(self) -> float:
        return (self.coverage_end_bjd_tdb - self.coverage_start_bjd_tdb) * 24.0


def predict_next_transit(
    target: ExoplanetTarget,
    from_bjd_tdb: float,
    *,
    baseline_minutes: float = 60.0,
) -> TransitWindow:
    """Return the first full transit whose midpoint is not before ``from_bjd_tdb``.

    The caller must convert its requested instant to BJD_TDB.  Rejecting a
    non-positive baseline here catches accidental empty-coverage plans before
    a telescope run begins.
    """
    epoch_system = target.epoch_system.upper().replace("-", "_").replace(" ", "_")
    if "BJD" not in epoch_system or "TDB" not in epoch_system:
        raise ValueError("A BJD_TDB transit epoch is required for prediction.")
    if baseline_minutes < 0:
        raise ValueError("baseline_minutes must not be negative")
    if target.duration_hours is None or target.duration_hours <= 0:
        raise ValueError("A published transit duration is required to prepare coverage.")
    epoch_number = math.ceil((from_bjd_tdb - target.epoch_bjd_tdb) / target.period_days)
    mid = target.epoch_bjd_tdb + epoch_number * target.period_days
    half_duration_days = target.duration_hours / 48.0
    baseline_days = baseline_minutes / 1440.0
    return TransitWindow(
        epoch_number=epoch_number,
        mid_bjd_tdb=mid,
        ingress_bjd_tdb=mid - half_duration_days,
        egress_bjd_tdb=mid + half_duration_days,
        coverage_start_bjd_tdb=mid - half_duration_days - baseline_days,
        coverage_end_bjd_tdb=mid + half_duration_days + baseline_days,
        baseline_minutes=baseline_minutes,
    )


def make_transit_sequence(
    target: ExoplanetTarget,
    window: TransitWindow,
    *,
    exposure_s: float,
    gain: int,
    filter_name: str,
    cadence_s: float | None = None,
) -> SequencePlan:
    """Build a single-light-step plan covering the requested transit window.

    Autfocus and dithering are disabled on purpose: flux time-series work needs
    stable cadence and pointing.  The UI labels this a preparation; the observer
    still reviews exposure, filter and actual start time before running it.
    """
    if exposure_s <= 0:
        raise ValueError("exposure_s must be positive")
    cadence_s = cadence_s if cadence_s is not None else exposure_s
    if cadence_s < exposure_s:
        raise ValueError("cadence_s cannot be shorter than exposure_s")
    coverage_s = window.coverage_hours * 3600.0
    count = max(1, math.ceil(coverage_s / cadence_s))
    return SequencePlan(
        object_name=target.host_name,
        steps=[
            SequenceStep(
                frame_type="Light",
                filter_name=filter_name,
                exposure_s=exposure_s,
                gain=gain,
                count=count,
                interval_s=cadence_s - exposure_s,
                dither_every=0,
            )
        ],
        repeat=1,
        autofocus_every_n=0,
        autofocus_on_filter_change=False,
        on_complete="Nothing",
        metadata={
            "observation_type": "exoplanet_transit",
            "planet_name": target.planet_name,
            "host_name": target.host_name,
            "ephemeris_source": target.source,
            "epoch_bjd_tdb": target.epoch_bjd_tdb,
            "period_days": target.period_days,
            "duration_hours": target.duration_hours,
            "depth_percent": target.depth_percent,
            "mid_transit_bjd_tdb": window.mid_bjd_tdb,
            "ingress_bjd_tdb": window.ingress_bjd_tdb,
            "egress_bjd_tdb": window.egress_bjd_tdb,
            "coverage_start_bjd_tdb": window.coverage_start_bjd_tdb,
            "coverage_end_bjd_tdb": window.coverage_end_bjd_tdb,
        },
    )
