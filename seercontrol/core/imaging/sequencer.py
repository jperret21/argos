"""Acquisition sequence model and expansion — pure logic, no Qt, no I/O.

Defines the multi-step sequence plan used by the advanced sequencer and the
``expand_plan`` flattener that turns a plan into the ordered list of frames to
shoot. Kept free of PyQt and hardware so it stays unit-testable in isolation
(this is where the business logic of sequencing lives, per CLAUDE.md).
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterator

from seercontrol.core.imaging.fits_writer import IMAGE_TYPE_MAP

logger = logging.getLogger(__name__)

#: Frame types accepted in a step (UI-facing short names).
FRAME_TYPES: tuple[str, ...] = ("Light", "Dark", "Flat", "Bias")


@dataclass
class SequenceStep:
    """One block of identical frames in a sequence plan.

    Attributes:
        enabled:      Whether this step is included when the plan runs.
        frame_type:   One of ``FRAME_TYPES`` (maps to a FITS ``IMAGETYP``).
        filter_name:  Filter to use (ignored for Dark/Bias frames).
        exposure_s:   Exposure time in seconds.
        gain:         Camera gain value.
        count:        Number of frames to shoot for this step.
        interval_s:   Idle delay inserted after each frame of this step.
        dither_every: Dither cadence (frames). 0 = off. Dithering is not
                      supported on the Seestar (no guiding) — kept for forward
                      compatibility only.
    """

    enabled: bool = True
    frame_type: str = "Light"
    filter_name: str = "LRGB"
    exposure_s: float = 10.0
    gain: int = 80
    count: int = 10
    interval_s: float = 0.0
    dither_every: int = 0


@dataclass
class SequencePlan:
    """An ordered list of steps plus sequence-level options.

    Attributes:
        steps:                      Ordered acquisition steps.
        object_name:                Target name written to FITS headers/filenames.
        repeat:                     Number of times the whole step list is replayed.
        autofocus_every_n:          Trigger autofocus every N frames (0 = off).
        autofocus_on_filter_change: Trigger autofocus whenever the filter changes.
        base_dir:                   Output root (defaults to ``Config.sessions_path``
                                    when ``None``).
    """

    steps: list[SequenceStep] = field(default_factory=list)
    object_name: str = ""
    repeat: int = 1
    autofocus_every_n: int = 0
    autofocus_on_filter_change: bool = False
    base_dir: Path | None = None


@dataclass
class FrameSpec:
    """A single frame to shoot, produced by :func:`expand_plan`."""

    frame_type: str  # "Light" | "Dark" | "Flat" | "Bias"
    image_type: str  # FITS IMAGETYP, e.g. "Light Frame"
    filter_name: str
    exposure_s: float
    gain: int
    interval_s: float
    dither_every: int
    frame_index: int  # 1-based counter within its (image_type, filter) bucket
    step_index: int  # index of the SequenceStep that produced it (0-based)
    is_light: bool

    @property
    def needs_filter(self) -> bool:
        """True for frame types that require a filter selection."""
        return self.frame_type in ("Light", "Flat")


def _image_type_for(frame_type: str) -> str:
    """Map a short frame type ("Light") to a FITS IMAGETYP ("Light Frame")."""
    return IMAGE_TYPE_MAP.get(frame_type.lower(), frame_type)


def expand_plan(plan: SequencePlan) -> Iterator[FrameSpec]:
    """Flatten a plan into the ordered sequence of frames to shoot.

    Honors ``enabled``, ``count`` and ``repeat``. The frame index restarts per
    ``(image_type, filter_name)`` bucket and increases monotonically across
    repeats, matching the Siril folder layout (one numbered series per
    type/filter sub-folder).

    Args:
        plan: The sequence plan to expand.

    Yields:
        One :class:`FrameSpec` per frame, in shooting order.
    """
    counters: dict[tuple[str, str], int] = {}
    for _pass in range(max(1, plan.repeat)):
        for step_index, step in enumerate(plan.steps):
            if not step.enabled or step.count <= 0:
                continue
            image_type = _image_type_for(step.frame_type)
            is_light = step.frame_type == "Light"
            for _ in range(step.count):
                key = (image_type, step.filter_name)
                counters[key] = counters.get(key, 0) + 1
                yield FrameSpec(
                    frame_type=step.frame_type,
                    image_type=image_type,
                    filter_name=step.filter_name,
                    exposure_s=step.exposure_s,
                    gain=step.gain,
                    interval_s=step.interval_s,
                    dither_every=step.dither_every,
                    frame_index=counters[key],
                    step_index=step_index,
                    is_light=is_light,
                )


def total_frames(plan: SequencePlan) -> int:
    """Return the total number of frames the plan will shoot."""
    per_pass = sum(s.count for s in plan.steps if s.enabled and s.count > 0)
    return per_pass * max(1, plan.repeat)


def plan_to_dict(plan: SequencePlan) -> dict:
    """Serialize a plan to a JSON-safe dict (for preset save)."""
    return {
        "object_name": plan.object_name,
        "repeat": plan.repeat,
        "autofocus_every_n": plan.autofocus_every_n,
        "autofocus_on_filter_change": plan.autofocus_on_filter_change,
        "base_dir": str(plan.base_dir) if plan.base_dir is not None else None,
        "steps": [asdict(s) for s in plan.steps],
    }


def plan_from_dict(data: dict) -> SequencePlan:
    """Rebuild a plan from a dict produced by :func:`plan_to_dict`."""
    steps = [SequenceStep(**s) for s in data.get("steps", [])]
    base = data.get("base_dir")
    return SequencePlan(
        steps=steps,
        object_name=data.get("object_name", ""),
        repeat=data.get("repeat", 1),
        autofocus_every_n=data.get("autofocus_every_n", 0),
        autofocus_on_filter_change=data.get("autofocus_on_filter_change", False),
        base_dir=Path(base) if base else None,
    )
