"""Tests for the launcher guards in ``main.py`` (Qt-free, no hardware).

The macOS quarantine sweep is what made Argos take ~10 s to start: it walks
~2600 files in the PyQt6 tree on every launch and, on a healthy venv, clears
exactly zero flags. It is now stamped so it runs once per install — these
tests pin the stamp logic, whose failure modes are both silent:

- stamping a sweep that failed would disable it forever;
- not invalidating the stamp on reinstall would leave a fresh venv quarantined
  and Qt unable to load its cocoa plugin.
"""

from __future__ import annotations

import os
import time

import main


def test_missing_stamp_requires_a_sweep(tmp_path):
    qt6 = tmp_path / "PyQt6"
    qt6.mkdir()
    assert main._needs_quarantine_sweep(qt6, tmp_path / ".stamp") is True


def test_stamp_newer_than_the_tree_skips_the_sweep(tmp_path):
    qt6 = tmp_path / "PyQt6"
    qt6.mkdir()
    stamp = tmp_path / ".stamp"
    stamp.touch()
    # Stamp written after the tree was last touched — nothing to do.
    os.utime(stamp, (time.time() + 10, time.time() + 10))
    assert main._needs_quarantine_sweep(qt6, stamp) is False


def test_reinstalled_tree_invalidates_the_stamp(tmp_path):
    """A uv sync rewrites PyQt6 and bumps its mtime — the sweep must run again."""
    qt6 = tmp_path / "PyQt6"
    qt6.mkdir()
    stamp = tmp_path / ".stamp"
    stamp.touch()
    later = time.time() + 60
    os.utime(qt6, (later, later))
    assert main._needs_quarantine_sweep(qt6, stamp) is True


def test_unreadable_tree_falls_back_to_sweeping(tmp_path):
    """A missing/unstatable tree must not skip the sweep on a bad stamp read."""
    stamp = tmp_path / ".stamp"
    stamp.touch()
    assert main._needs_quarantine_sweep(tmp_path / "does-not-exist", stamp) is True
