"""Local astropy hook — shadows the one from pyinstaller-hooks-contrib.

The contrib hook calls ``collect_submodules("astropy")``, which imports every
astropy subpackage. ``astropy.visualization.wcsaxes`` does
``pytest.importorskip("matplotlib")`` at import time, so on a matplotlib-free
install the collection aborts and the whole build fails.

Argos uses astropy for FITS I/O, coordinates and time. It never plots, so the
visualization subpackage is skipped rather than dragging ~50 MB of matplotlib
into a bundle people download over a field hotspot.
"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, get_module_file_attribute

#: astropy reads its own configuration and data tables at runtime.
datas = collect_data_files("astropy")

hiddenimports = collect_submodules(
    "astropy",
    filter=lambda name: not name.startswith("astropy.visualization"),
)


# astropy's unit and angle parsers are built with ply, which caches its
# generated tables as *_parsetab.py / *_lextab.py. At import time
# astropy.utils.parsing._patch_ply_module reads those files' **source** —
# ``Path(...).read_text()`` — to check the signature matches.
#
# PyInstaller ships modules as compiled bytecode inside the archive, so the
# .py files do not exist on disk and the read raises FileNotFoundError. That
# surfaces as the very confusing "'m / (s)' did not parse as unit" on the
# first astropy.units import, and the app dies before showing a window.
#
# Shipping the sources alongside costs a few kilobytes.
_PLY_TABLE_DIRS = ("units/format", "coordinates/angles")

_astropy_root = Path(get_module_file_attribute("astropy")).parent
for _relative in _PLY_TABLE_DIRS:
    _directory = _astropy_root / _relative
    for _table in sorted(_directory.glob("*tab.py")):
        datas.append((str(_table), f"astropy/{_relative}"))
