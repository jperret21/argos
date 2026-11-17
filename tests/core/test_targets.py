"""Tests for the persistent target set (Qt-free, no hardware)."""

from __future__ import annotations

from dataclasses import replace

from argos.core.catalog.targets import (
    ROLE_CHECK,
    ROLE_COMPARISON,
    ROLE_TARGET,
    TargetSet,
    TargetStar,
    comparison_chart_id,
)


def _star(role=ROLE_TARGET, auid="000-BBB-001", ra=83.6, dec=22.0, name="NU Ori"):
    return TargetStar(role=role, ra_deg=ra, dec_deg=dec, auid=auid, name=name, source="vsx")


def test_set_role_adds_then_updates_by_identity() -> None:
    ts = TargetSet(object_name="M42")
    ts.set_role(_star(role=ROLE_TARGET))
    assert len(ts.stars) == 1
    # Same AUID → update in place (role change), not a duplicate.
    ts.set_role(_star(role=ROLE_COMPARISON))
    assert len(ts.stars) == 1
    assert ts.stars[0].role == ROLE_COMPARISON


def test_key_falls_back_to_position_without_auid() -> None:
    a = TargetStar(role=ROLE_TARGET, ra_deg=10.0, dec_deg=-5.0)
    b = TargetStar(role=ROLE_TARGET, ra_deg=10.0, dec_deg=-5.0)
    assert a.key() == b.key()  # same position → same identity
    assert a.key() != _star().key()


def test_by_role_and_remove() -> None:
    ts = TargetSet()
    ts.set_role(_star(auid="A", role=ROLE_TARGET))
    ts.set_role(_star(auid="B", role=ROLE_COMPARISON, name="comp"))
    assert len(ts.by_role(ROLE_TARGET)) == 1
    assert len(ts.by_role(ROLE_COMPARISON)) == 1
    ts.remove("auid:A")
    assert [s.auid for s in ts.stars] == ["B"]


def test_json_round_trip(tmp_path) -> None:
    ts = TargetSet(object_name="M42")
    ts.set_role(_star(role=ROLE_TARGET))
    ts.set_role(_star(auid="C", role=ROLE_COMPARISON, name="HD 37041"))
    path = tmp_path / "sub" / "targets.json"
    ts.save(path)  # creates parent dirs, atomic write
    back = TargetSet.load(path)
    assert back.object_name == "M42"
    assert {s.auid for s in back.stars} == {"000-BBB-001", "C"}
    assert back.by_role(ROLE_TARGET)[0].name == "NU Ori"


def test_catalogue_enriched_target_replaces_manual_same_position() -> None:
    ts = TargetSet(object_name="XX Cyg")
    ts.set_role(TargetStar(role=ROLE_TARGET, ra_deg=300.815175, dec_deg=58.954590, name="XX Cyg"))
    ts.set_role(
        TargetStar(
            role=ROLE_TARGET,
            ra_deg=300.815170,
            dec_deg=58.954580,
            auid="000-BCK-301",
            name="XX Cyg",
            source="vsx",
        )
    )
    targets = ts.by_role(ROLE_TARGET)
    assert len(targets) == 1
    assert targets[0].auid == "000-BCK-301"


def test_selection_manifest_is_explicit_and_saved(tmp_path) -> None:
    ts = TargetSet(object_name="XX Cyg")
    ts.set_role(
        _star(role=ROLE_TARGET, auid="000-BCK-301", ra=300.81517, dec=58.95458, name="XX Cyg")
    )
    ts.set_role(
        _star(role=ROLE_COMPARISON, auid="000-BJV-170", ra=300.70292, dec=59.00994, name="104")
    )
    ts.set_role(_star(role=ROLE_CHECK, auid="000-BJV-171", ra=300.89913, dec=58.92267, name="106"))
    path = tmp_path / "photometry_selection.json"
    ts.save_selection_manifest(path, generated_by="Argos test")
    saved = __import__("json").loads(path.read_text())
    assert saved["selection_status"] == "provisional_live_preview"
    assert saved["targets"][0]["auid"] == "000-BCK-301"
    assert saved["comparison_stars"][0]["name"] == "104"
    assert saved["check_stars"][0]["ra_deg_j2000"] == 300.89913

    history = tmp_path / "photometry_selection_history.jsonl"
    ts.append_selection_history(history, generated_by="Argos test")
    ts.append_selection_history(history, generated_by="Argos test")
    records = [__import__("json").loads(line) for line in history.read_text().splitlines()]
    assert len(records) == 2
    assert all(record["targets"][0]["name"] == "XX Cyg" for record in records)


def test_vsp_chart_id_is_saved_and_handed_off(tmp_path) -> None:
    ts = TargetSet(object_name="XX Cyg")
    comp = replace(_star(role=ROLE_COMPARISON, auid="000-BJV-170"), chart_id="X42585ESI")
    ts.set_role(comp)
    ts.save(tmp_path / "targets.json")
    assert TargetSet.load(tmp_path / "targets.json").stars[0].chart_id == "X42585ESI"
    manifest = ts.selection_manifest()
    assert manifest["comparison_stars"][0]["catalogue_chart_id"] == "X42585ESI"


def test_comparison_chart_id_needs_one_chart_for_every_comparison() -> None:
    c1 = replace(_star(role=ROLE_COMPARISON, auid="C1"), chart_id="X1")
    c2 = replace(_star(role=ROLE_COMPARISON, auid="C2"), chart_id="X1")
    target = _star(role=ROLE_TARGET, auid="T")  # no chart: targets do not count
    assert comparison_chart_id([target, c1, c2]) == "X1"
    assert comparison_chart_id([c1, replace(c2, chart_id="X2")]) is None  # two charts
    assert comparison_chart_id([c1, replace(c2, chart_id=None)]) is None  # manual comp
    assert comparison_chart_id([target]) is None


def test_load_missing_returns_empty(tmp_path) -> None:
    assert TargetSet.load(tmp_path / "nope.json").stars == []


def test_from_dict_ignores_unknown_keys() -> None:
    ts = TargetSet.from_dict(
        {"object": "X", "stars": [{"role": "target", "ra_deg": 1.0, "dec_deg": 2.0, "future": 9}]}
    )
    assert ts.stars[0].ra_deg == 1.0  # unknown 'future' key dropped, no crash


def test_display_name_prefers_name_then_auid() -> None:
    assert _star(name="NU Ori").display_name == "NU Ori"
    assert TargetStar(role="check", ra_deg=1, dec_deg=2, auid="Z").display_name == "Z"
    assert (
        TargetStar(
            role=ROLE_COMPARISON,
            ra_deg=1,
            dec_deg=2,
            auid="000-ABC-123",
            name="114",  # VSP chart magnitude code, not an object name
            source="vsp_auto",
        ).display_name
        == "000-ABC-123"
    )


def test_summary_counts_roles_and_readiness() -> None:
    empty = TargetSet(object_name="M42").summary()
    assert empty["target"] is None and empty["complete"] is False

    ts = TargetSet(object_name="M42")
    ts.set_role(_star(auid="A", role=ROLE_TARGET, name="NU Ori"))
    # Target alone is not yet enough for differential photometry.
    assert ts.summary()["complete"] is False
    ts.set_role(_star(auid="B", role=ROLE_COMPARISON, name="comp1"))
    ts.set_role(_star(auid="C", role=ROLE_COMPARISON, name="comp2"))
    ts.set_role(_star(auid="K", role=ROLE_CHECK, name="check1"))

    s = ts.summary()
    assert s["object"] == "M42"
    assert s["target"] == "NU Ori"
    assert s["n_comparison"] == 2
    assert s["n_check"] == 1
    assert s["complete"] is True


def test_comparisons_saved_without_a_chart_get_the_vsp_answer_s_s68() -> None:
    """S68: a set picked before Argos kept VSP's chart (0.4.1) kept CHART at na forever."""
    from argos.core.catalog.aavso import Band, ComparisonStar

    ts = TargetSet(object_name="XX Cyg")
    ts.set_role(_star(role=ROLE_TARGET, auid="T"))
    for auid, mag in (("C1", 11.4), ("C2", 12.1), ("C3", 12.5)):
        ts.set_role(
            replace(_star(role=ROLE_COMPARISON, auid=auid), source="vsp_auto", mags={"V": mag})
        )
    ts.set_role(replace(_star(role=ROLE_COMPARISON, auid="M"), source="manual", mags={"V": 13.0}))
    answer = [
        ComparisonStar("C1", 0, 0, "114", (Band("V", 11.4), Band("B", 12.0)), chart_id="X9"),
        ComparisonStar("C2", 0, 0, "121", (Band("V", 12.1),), chart_id="X9"),
        ComparisonStar("C3", 0, 0, "126", (Band("V", 12.6),), chart_id="X9"),  # revised
        ComparisonStar("M", 0, 0, "130", (Band("V", 13.0),), chart_id="X9"),
    ]

    assert ts.backfill_chart_ids(answer) == 2

    charts = {s.auid: s.chart_id for s in ts.by_role(ROLE_COMPARISON)}
    assert charts == {"C1": "X9", "C2": "X9", "C3": None, "M": None}
    assert ts.backfill_chart_ids(answer) == 0  # a chart already named is kept


# ── S77: proper motion ───────────────────────────────────────────────────────

#: RR Lyr (000-BCG-719): its VSX position (J2000.0) and Gaia DR3 2125982599343482624
#: (ESA Gaia archive, gaiadr3.gaia_source: ra, dec at 2016.0, pmra, pmdec in mas/yr).
_RR_VSX = (291.36629, 42.78436)
_RR_GAIA = dict(
    source_id="2125982599343482624",
    ra_deg=291.36564029422567,
    dec_deg=42.783488792618705,
    g_mag=7.6188045,
    pmra_mas_yr=-109.59872730873641,
    pmdec_mas_yr=-195.85073064533083,
)
#: JD of RR Lyr 2026-09-25 200453Z's first sub (2026-09-25T20:05 UTC).
_JD_2026_09_25 = 2461309.337


def _gaia(**kw):
    from argos.core.catalog.gaia import GaiaStar

    return GaiaStar(**kw)


def test_a_vsx_target_takes_its_gaia_proper_motion_and_moves_to_the_frame_date_s77() -> None:
    """S77: target sets held J2000.0 positions only: RR Lyr's aperture sat 1.0 green px
    (6") from the star in 2026. Its Gaia DR3 source (3.6" from the VSX position in
    2016.0, 0.05" once moved back to 2000.0) gives the motion; the set measured on a
    frame of 2026-09-25 places it 26.73 years of -109.6/-195.9 mas/yr from J2000.0."""
    import math

    ts = TargetSet(object_name="RR Lyr")
    ts.set_role(TargetStar("target", *_RR_VSX, auid="000-BCG-719", name="RR Lyr", source="vsx"))
    faint = _gaia(
        source_id="1",
        ra_deg=291.35837,
        dec_deg=42.78593,
        g_mag=16.1,
        pmra_mas_yr=-1.5,
        pmdec_mas_yr=-2.7,
    )
    assert ts.backfill_proper_motions([faint, _gaia(**_RR_GAIA)]) == 1
    star = ts.stars[0]
    assert star.pm_source == "Gaia DR3 2125982599343482624"
    assert (star.ra_deg, star.dec_deg) == _RR_VSX  # the catalogue position is kept
    moved = ts.at_jd(_JD_2026_09_25).stars[0]
    years = 2000.0 + (_JD_2026_09_25 - 2451545.0) / 365.25 - 2016.0
    expect_dec = _RR_GAIA["dec_deg"] + _RR_GAIA["pmdec_mas_yr"] * years / 3.6e6
    expect_ra = _RR_GAIA["ra_deg"] + _RR_GAIA["pmra_mas_yr"] * years / 3.6e6 / math.cos(
        math.radians(_RR_GAIA["dec_deg"])
    )
    assert abs(moved.dec_deg - expect_dec) * 3600 < 0.001
    assert abs(moved.ra_deg - expect_ra) * 3600 < 0.001
    shift = math.hypot(
        (moved.ra_deg - _RR_VSX[0]) * math.cos(math.radians(_RR_VSX[1])), moved.dec_deg - _RR_VSX[1]
    )
    assert 5.8 < shift * 3600 < 6.2  # 6.0" in 26.7 years: 0.8 green px
    assert moved.key() == star.key()  # the same star


def test_a_comparison_matches_its_gaia_source_by_brightness_when_vsp_is_off_s77() -> None:
    """S77: VSP's position of RR Lyr's comparison 000-BJW-666 (174 mas/yr) is 3.2" from
    its Gaia DR3 2016.0 one and 5.2" from its J2000.0 one: the only source within 6"
    whose G (7.70) is within 1 mag of its V (7.90) is it. A faint variable never takes
    a brighter neighbour's motion and position."""
    vsp = (291.98771, 42.77725)
    g666 = _gaia(
        source_id="666",
        ra_deg=vsp[0] + 0.0008,
        dec_deg=vsp[1] - 0.0006,
        g_mag=7.70,
        pmra_mas_yr=68.1,
        pmdec_mas_yr=160.5,
    )
    ts = TargetSet(object_name="RR Lyr")
    ts.set_role(
        TargetStar("comparison", *vsp, auid="000-BJW-666", source="vsp_auto", mags={"V": 7.902})
    )
    assert ts.backfill_proper_motions([g666]) == 1
    faint = TargetSet(object_name="V")
    faint.set_role(TargetStar("target", *vsp, auid="000-ZZZ-001", source="vsx", mags={"V": 14.5}))
    assert faint.backfill_proper_motions([g666]) == 0  # 6.7 mag brighter: not it
    manual = TargetSet(object_name="M")
    manual.set_role(TargetStar("comparison", *vsp, auid="000-BJW-666", source="manual"))
    assert manual.backfill_proper_motions([g666]) == 0  # a position taken on a frame


def test_proper_motion_fields_round_trip_and_stay_out_when_unknown_s77(tmp_path) -> None:
    """S77: a set without proper motions keeps its bytes (no new keys); one with them
    keeps them through targets.json, a role change, and the selection manifest."""
    plain = TargetSet(object_name="X")
    plain.set_role(TargetStar("target", 1.0, 2.0, auid="000-AAA-001", source="vsx"))
    assert "pm_ra_mas_yr" not in plain.to_dict()["stars"][0]
    ts = TargetSet(object_name="RR Lyr")
    ts.set_role(TargetStar("comparison", *_RR_VSX, auid="000-BCG-719", source="vsx"))
    ts.backfill_proper_motions([_gaia(**_RR_GAIA)])
    ts.save(tmp_path / "t.json")
    again = TargetSet.load(tmp_path / "t.json")
    assert again.stars[0].pm_dec_mas_yr == round(_RR_GAIA["pmdec_mas_yr"], 4)
    again.set_role(TargetStar("check", *_RR_VSX, auid="000-BCG-719", source="vsx"))
    assert again.stars[0].role == "check" and again.stars[0].has_proper_motion
    record = again.selection_manifest()["check_stars"][0]
    assert record["pm_source"] == "Gaia DR3 2125982599343482624"
    assert TargetSet(object_name="X").at_jd(_JD_2026_09_25).stars == []


# ── S79: a comparison beside a brighter star of the set ─────────────────────


def _xx_cyg_set() -> TargetSet:
    """XX Cyg 2026-09-07 040723Z's set, as far as S79 needs it (VSP positions and V)."""
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


def test_a_comparison_beside_a_brighter_star_of_the_set_is_crowded_s79() -> None:
    """S79: 000-BJV-173 sits 6.8 green px (50.6") from the check star 000-BJV-169, 1.47
    mag brighter, inside 2 aperture radii (5.45 px x 7.48"/px x 2 = 81.5"): 1 % of
    169's light falls in its aperture. Nothing said so. The brighter one is not
    crowded by the fainter (1 % of its light, the -0.011 mag of S69)."""
    from argos.core.catalog.targets import crowded_stars

    crowded = crowded_stars(_xx_cyg_set(), 2 * 5.45 * 7.477)
    assert list(crowded) == ["auid:000-BJV-173"]
    why = crowded["auid:000-BJV-173"]
    assert why.neighbour == "000-BJV-169" and why.band == "V"
    assert abs(why.delta_mag + 1.474) < 1e-6 and 50.0 < why.separation_arcsec < 51.0
    assert "1.47 mag brighter in V" in why.text("000-BJV-173", 81.5)
    assert crowded_stars(_xx_cyg_set(), 40.0) == {}  # beyond 2 radii: nothing


def test_a_comparison_beside_the_variable_is_crowded_s79() -> None:
    """S79: a neighbour of unknown brightness (the variable target) counts too."""
    from argos.core.catalog.targets import crowded_stars

    ts = _xx_cyg_set()
    ts.set_role(
        TargetStar(
            "comparison",
            300.81517 + 0.005,
            58.95458,
            auid="000-ZZZ-001",
            source="vsp_auto",
            mags={"V": 12.0},
        )
    )
    crowded = crowded_stars(ts, 81.5)
    assert crowded["auid:000-ZZZ-001"].neighbour == "000-BCK-301"
    assert crowded["auid:000-ZZZ-001"].delta_mag is None


def test_crowding_and_the_gaia_match_see_across_ra_0h_s77_s79() -> None:
    """S77/S79 amended (technical review): the separation took the raw RA difference, so
    two stars 7" apart across RA 0h were 1.3e6" apart: never crowded, never matched to
    their Gaia source."""
    from argos.core.catalog.gaia import GaiaStar
    from argos.core.catalog.targets import crowded_stars

    ts = TargetSet(object_name="Zero")
    ts.set_role(
        TargetStar("comparison", 359.9995, 10.0, auid="000-AAA-001", source="vsp", mags={"V": 9.0})
    )
    ts.set_role(
        TargetStar("comparison", 0.0015, 10.0, auid="000-AAA-002", source="vsp", mags={"V": 11.0})
    )
    assert list(crowded_stars(ts, 20.0)) == ["auid:000-AAA-002"]  # {} before the fix

    gaia = GaiaStar(
        source_id="1", ra_deg=359.99995, dec_deg=10.0, g_mag=9.0, pmra_mas_yr=50.0, pmdec_mas_yr=0.0
    )
    probe = TargetSet(object_name="Zero", stars=[ts.stars[0]])
    probe.stars[0] = TargetStar(
        "comparison", 0.00005, 10.0, auid="000-AAA-001", source="vsp", mags={"V": 9.0}
    )
    assert probe.backfill_proper_motions([gaia]) == 1  # 0 before: 1.3e6" apart
