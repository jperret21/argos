"""Build Argos's compact offline Messier/NGC/IC catalogue from CDS NGC 2000.0.

The generated gzip JSON is committed under ``argos/resources/catalogues`` and
is therefore available in a frozen application without any network access.
It deliberately contains only stable identifiers, B2000/J2000 positions,
object types, magnitudes and aliases.  It is *not* a substitute for a modern
astrometric star catalogue.

Usage:
    python scripts/build_embedded_catalog.py /path/to/ngc2000.dat /path/to/names.dat

Source: CDS/VizieR VII/118, NGC 2000.0 (Sinnott 1988), downloaded from
https://cdsarc.cds.unistra.fr/ftp/VII/118/.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path
import sys

OUT = Path(__file__).parents[1] / "argos" / "resources" / "catalogues" / "essential-v1.json.gz"

# Entries without an NGC/IC counterpart in VII/118/names.dat.  Coordinates are
# J2000, retained only so the canonical Messier designation resolves offline.
_MESSIER_EXTRAS = {
    "M 24": (274.2250, -18.4833, "Star cloud"),
    "M 40": (185.5500, 58.0833, "Double star"),
    "M 45": (56.8500, 24.1167, "Open cluster"),
}


def _canonical(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("I"):
        return f"IC {int(raw[1:])}"
    return f"NGC {int(raw)}"


def _key(value: str) -> str:
    return "".join(char for char in value.casefold() if char.isalnum())


def _parse_ngc(path: Path) -> dict[str, dict]:
    records: dict[str, dict] = {}
    for line in path.read_text(encoding="latin-1").splitlines():
        try:
            raw = line[0:5].strip()
            name = _canonical(raw)
            ra_deg = (int(line[10:12]) + float(line[13:17]) / 60.0) * 15.0
            dec = int(line[20:22]) + int(line[23:25]) / 60.0
            dec_deg = -dec if line[19] == "-" else dec
        except (IndexError, ValueError):
            continue
        try:
            magnitude = float(line[40:44])
        except ValueError:
            magnitude = None
        records[raw] = {
            "name": name,
            "aliases": [name],
            "ra_degrees": round(ra_deg, 7),
            "dec_degrees": round(dec_deg, 7),
            "object_type": line[6:9].strip(),
            "magnitude": magnitude,
        }
    return records


def _add_aliases(records: dict[str, dict], names_path: Path) -> None:
    # A Messier number occasionally points at two components (M 51/M 76).  The
    # first catalogue record is its primary autocomplete/resolve target; both
    # NGC records remain individually searchable.
    used_messier: set[str] = set()
    for line in names_path.read_text(encoding="latin-1").splitlines():
        alias, raw = line[0:35].strip(), line[36:41].strip()
        if not alias or not raw or raw not in records:
            continue
        normal = _key(alias)
        if normal.startswith("m") and normal[1:].isdigit():
            alias = f"M {int(normal[1:])}"
            if alias in used_messier:
                continue
            used_messier.add(alias)
        if alias not in records[raw]["aliases"]:
            records[raw]["aliases"].append(alias)

    # M 102 conventionally designates NGC 5866.  It is absent from the legacy
    # names table but should remain reachable in an observer-facing catalogue.
    for raw, record in records.items():
        if record["name"] == "NGC 5866" and "M 102" not in record["aliases"]:
            record["aliases"].append("M 102")


def build(ngc_path: Path, names_path: Path) -> dict:
    records = _parse_ngc(ngc_path)
    _add_aliases(records, names_path)
    objects = list(records.values())
    for name, (ra_deg, dec_deg, kind) in _MESSIER_EXTRAS.items():
        objects.append(
            {
                "name": name,
                "aliases": [name],
                "ra_degrees": ra_deg,
                "dec_degrees": dec_deg,
                "object_type": kind,
                "magnitude": None,
            }
        )
    objects.sort(key=lambda row: (_key(row["name"]), row["name"]))
    return {
        "schema_version": 1,
        "catalogue": "Argos Essential Catalogue",
        "version": "1.0",
        "source": "CDS/VizieR VII/118 — NGC 2000.0 (Sinnott 1988)",
        "source_url": "https://cdsarc.cds.unistra.fr/ftp/VII/118/",
        "coordinate_system": "J2000 equatorial coordinates as supplied by NGC 2000.0",
        "objects": objects,
    }


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("Usage: build_embedded_catalog.py ngc2000.dat names.dat")
    payload = build(Path(sys.argv[1]), Path(sys.argv[2]))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(OUT, "wt", encoding="utf-8", compresslevel=9) as stream:
        json.dump(payload, stream, ensure_ascii=False, separators=(",", ":"))
    print(f"Wrote {OUT} ({len(payload['objects'])} objects)")


if __name__ == "__main__":
    main()
