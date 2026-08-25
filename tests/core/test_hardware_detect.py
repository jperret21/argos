"""Tests for profile/driver cross-checking (Qt-free, no hardware).

The failure this guards against is silent: with the wrong profile selected,
frames keep arriving and solves keep succeeding while every magnitude is
computed against the wrong plate scale. These tests pin both halves of the
contract — that a real disagreement is reported, and that weak evidence
produces no answer at all rather than a confident wrong one.
"""

from __future__ import annotations

from argos.core.hardware import catalog, detect

# --------------------------------------------------------------------------- #
# mismatches                                                                   #
# --------------------------------------------------------------------------- #


def test_matching_camera_reports_nothing():
    assert (
        detect.mismatches(
            catalog.S30_PRO, camera_name="ZWO Seestar S30 Pro", width=3840, height=2160
        )
        == ()
    )


def test_wrong_resolution_is_reported():
    found = detect.mismatches(catalog.S30_PRO, width=1920, height=1080)
    assert len(found) == 1
    assert "1920×1080" in found[0]
    assert "3840×2160" in found[0]


def test_a_different_known_sensor_in_the_name_is_reported():
    found = detect.mismatches(catalog.S30_PRO, camera_name="Seestar IMX462 camera")
    assert any("IMX462" in f for f in found)


def test_a_loose_driver_name_is_not_a_contradiction():
    """Only a positive contradiction counts — drivers name cameras loosely."""
    assert (
        detect.mismatches(catalog.S30_PRO, camera_name="Seestar camera", width=3840, height=2160)
        == ()
    )


def test_unknown_values_are_not_treated_as_conflicts():
    """A driver that reports nothing is not evidence of a wrong profile."""
    assert detect.mismatches(catalog.S30_PRO, camera_name="", width=None, height=None) == ()


# --------------------------------------------------------------------------- #
# suggest                                                                      #
# --------------------------------------------------------------------------- #


def test_sensor_name_identifies_the_profile():
    assert detect.suggest(camera_name="ZWO Seestar (IMX585)").key == "s30pro"


def test_unique_resolution_identifies_the_profile():
    assert detect.suggest(width=3840, height=2160).key == "s30pro"


def test_ambiguous_resolution_suggests_nothing():
    """The S30 and S50 share 1920×1080 — a coin flip here would be trusted."""
    assert detect.suggest(width=1920, height=1080) is None


def test_unknown_camera_suggests_nothing():
    assert detect.suggest(camera_name="Some other telescope", width=640, height=480) is None
