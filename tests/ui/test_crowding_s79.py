"""S79: the Comparison stars tab and the Activity log name a crowded comparison."""

from __future__ import annotations

from types import SimpleNamespace

from argos.core.catalog.targets import TargetSet, TargetStar, crowded_stars


def _set() -> TargetSet:
    ts = TargetSet(object_name="XX Cyg")
    ts.set_role(TargetStar("target", 300.81517, 58.95458, auid="000-BCK-301", source="vsx"))
    ts.set_role(
        TargetStar(
            "comparison",
            300.65291666666667,
            58.89161111111111,
            auid="000-BJV-173",
            source="vsp_auto",
            mags={"V": 11.757},
        )
    )
    ts.set_role(
        TargetStar(
            "check",
            300.6277083333334,
            58.88630555555555,
            auid="000-BJV-169",
            source="vsp_auto",
            mags={"V": 10.283},
        )
    )
    return ts


def test_the_comparison_tab_and_the_log_name_a_crowded_comparison_s79(qapp) -> None:
    """S79: XX Cyg 2026-09-07 040723Z paired 000-BJV-173 with the check star 000-BJV-169,
    1.47 mag brighter, 6.8 green px away, and nothing said so. The Comparison stars tab
    shows it, and the Activity log names it once (not again on the next refresh)."""
    import argos.ui.pages.imaging_page as ip
    from argos.ui.widgets.comparison_table import ComparisonEnsembleTable

    tset = _set()
    radius = 2 * 5.45 * 7.477
    table = ComparisonEnsembleTable()
    logs: list[tuple[str, str]] = []
    page = SimpleNamespace(
        _engine=SimpleNamespace(
            crowding=lambda: (crowded_stars(tset, radius), radius), target_set=lambda: tset
        ),
        _photometry_window=SimpleNamespace(comparisons=table),
        log_message=SimpleNamespace(emit=lambda level, msg: logs.append((level, msg))),
        _crowding_warned=set(),
    )
    ip.ImagingPage._warn_crowding(page)
    ip.ImagingPage._warn_crowding(page)

    assert "000-BJV-173: 000-BJV-169 (1.47 mag brighter in V)" in table.crowding_text
    assert [level for level, _m in logs] == ["WARN"]
    assert "Comparison crowded" in logs[0][1]
