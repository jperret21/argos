from __future__ import annotations

from pathlib import Path

from argos.core.catalog import exoplanets, field_objects


class _CsvResponse:
    def __init__(self, text: str) -> None:
        self.text = text

    def raise_for_status(self) -> None:
        return None


class _JsonResponse:
    def __init__(self, values) -> None:
        self._values = values

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self._values


class _Session:
    def __init__(self, response) -> None:
        self.response = response
        self.calls: list[dict] = []

    def get(self, _url: str, *, params: dict, timeout: float):
        self.calls.append(params)
        return self.response


def test_simbad_field_search_caches_conventional_names(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(field_objects, "_CACHE_DIR", tmp_path / "simbad")
    session = _Session(_CsvResponse("main_id,ra,dec,otype\nV* XX Cyg,300.815175,58.954590,SX*\n"))
    objects = field_objects.simbad_field_objects(300.8, 58.95, 0.2, session=session)
    assert [(item.name, item.object_type) for item in objects] == [("XX Cyg", "SX*")]
    assert "FROM basic" in session.calls[0]["query"]
    # The result is usable during an offline field identification later.
    assert field_objects.simbad_field_objects(300.8, 58.95, 0.2, allow_network=False) == objects


def test_simbad_field_search_preserves_passband_magnitudes(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(field_objects, "_CACHE_DIR", tmp_path / "simbad")
    session = _Session(
        _CsvResponse(
            "main_id,ra,dec,otype,V,G,J,K,g_,r_\n"
            "2MASX J20021735+5909440,300.572,59.162,G,,20.613,14.889,13.639,,\n"
        )
    )
    item = field_objects.simbad_field_objects(300.8, 58.95, 0.6, session=session)[0]
    assert item.object_type == "G"
    assert dict(item.mags) == {"G": 20.613, "J": 14.889, "K": 13.639}
    assert "allfluxes" in session.calls[0]["query"]


def test_point_lookup_can_include_ordinary_simbad_stars(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(field_objects, "_CACHE_DIR", tmp_path / "simbad")
    session = _Session(_CsvResponse("main_id,ra,dec,otype\nGaia DR3 123,300.0,58.0,*\n"))
    objects = field_objects.simbad_field_objects(
        300.0,
        58.0,
        10.0 / 3600.0,
        include_ordinary_stars=True,
        session=session,
    )
    assert objects[0].name == "Gaia DR3 123"
    assert "b.otype <> '*'" not in session.calls[0]["query"]


def test_nasa_field_search_groups_hosts_and_caches(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(exoplanets, "_FIELD_CACHE_DIR", tmp_path / "nasa")
    session = _Session(
        _JsonResponse(
            [
                {
                    "pl_name": "HD 189733 b",
                    "hostname": "HD 189733",
                    "ra": 300.1821,
                    "dec": 22.7099,
                    "sy_vmag": 7.67,
                    "sy_gaiamag": 7.51,
                },
                {"pl_name": "HD 189733 c", "hostname": "HD 189733", "ra": 300.1821, "dec": 22.7099},
            ]
        )
    )
    hosts = exoplanets.exoplanet_hosts_in_cone(300.18, 22.71, 0.2, session=session)
    assert hosts[0].host_name == "HD 189733"
    assert hosts[0].planet_names == ("HD 189733 b", "HD 189733 c")
    assert dict(hosts[0].mags) == {"Gaia G": 7.51, "V": 7.67}
    assert "pscomppars" in session.calls[0]["query"]
    assert exoplanets.exoplanet_hosts_in_cone(300.18, 22.71, 0.2, allow_network=False) == hosts


def test_dense_simbad_limit_is_spatially_distributed() -> None:
    objects = []
    for quadrant, (ra0, dec0) in enumerate(((9.6, 19.6), (10.4, 19.6), (9.6, 20.4), (10.4, 20.4))):
        objects.extend(
            field_objects.NamedFieldObject(f"HD {quadrant}-{index}", ra0, dec0, "*")
            for index in range(20)
        )
    selected = field_objects._spatially_uniform(objects, 8, 10.0, 20.0, 1.0)
    assert len(selected) == 8
    assert {item.name.split("-")[0] for item in selected} == {
        "HD 0",
        "HD 1",
        "HD 2",
        "HD 3",
    }
