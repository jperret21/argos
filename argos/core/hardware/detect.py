"""Cross-check the active profile against what the driver actually reports.

Picking the wrong telescope profile is a silent failure: the frames keep
coming, the plate solve keeps working, and every magnitude is computed against
the wrong plate scale. The driver knows its own sensor size and name, so there
is no reason to let that go unnoticed.

Deliberately advisory. :func:`mismatches` reports, it does not correct — the
caller warns and the observer decides. Switching profile mid-session would
change the plate scale under a running photometry series, which is worse than
the mismatch it would be fixing.

:func:`suggest` only answers when the evidence is unambiguous. The S30 and S50
share a 1920×1080 sensor, so resolution alone cannot separate them; guessing
between two wrong answers is not better than saying nothing.
"""

from __future__ import annotations

from argos.core.hardware import catalog
from argos.core.hardware.profile import TelescopeProfile


def mismatches(
    profile: TelescopeProfile,
    *,
    camera_name: str = "",
    width: int | None = None,
    height: int | None = None,
) -> tuple[str, ...]:
    """Human-readable disagreements between *profile* and the connected camera.

    Empty when everything the driver reported is consistent with the profile.
    Unknown values (empty name, ``None`` dimensions) are skipped rather than
    treated as conflicts — a driver that does not report a field is not
    evidence of anything.
    """
    found: list[str] = []

    if width and height and (width, height) != (profile.sensor_width_px, profile.sensor_height_px):
        found.append(
            f"driver reports {width}×{height}, profile {profile.key} expects "
            f"{profile.sensor_width_px}×{profile.sensor_height_px}"
        )

    if camera_name and profile.sensor:
        # Drivers name cameras loosely ("ZWO Seestar S30 Pro", "IMX585",
        # "Seestar camera"), so only a positive contradiction counts: some
        # *other* known sensor appears in the name.
        upper = camera_name.upper()
        others = {p.sensor.upper() for p in catalog.PROFILES.values() if p.sensor}
        others.discard(profile.sensor.upper())
        for sensor in sorted(others):
            if sensor in upper:
                found.append(
                    f"driver name {camera_name!r} mentions {sensor}, "
                    f"profile {profile.key} expects {profile.sensor}"
                )
                break

    return tuple(found)


def suggest(
    *, camera_name: str = "", width: int | None = None, height: int | None = None
) -> TelescopeProfile | None:
    """The one registered profile matching this camera, or ``None``.

    Returns ``None`` when nothing matches *and* when several do — an ambiguous
    suggestion would be worse than none, because the observer would trust it.
    """
    if camera_name:
        upper = camera_name.upper()
        by_sensor = [p for p in catalog.PROFILES.values() if p.sensor and p.sensor.upper() in upper]
        if len(by_sensor) == 1:
            return by_sensor[0]

    if width and height:
        by_size = [
            p
            for p in catalog.PROFILES.values()
            if (p.sensor_width_px, p.sensor_height_px) == (width, height)
        ]
        if len(by_size) == 1:
            return by_size[0]

    return None
