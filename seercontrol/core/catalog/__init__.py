"""Star catalog access for photometry (variable + comparison stars).

Qt-free clients for the two AAVSO services this app cares about:

* **VSX** (Variable Star indeX) — *where the variable stars are* in a field.
* **VSP** (Variable Star Plotter) — *which comparison stars* are available,
  with calibrated magnitudes, for photometry of a target.

The UI solves a frame (:mod:`seercontrol.core.imaging.platesolve`), gets a
:class:`~seercontrol.core.imaging.platesolve.FrameWCS`, then queries these by the
field centre + radius and projects the results back onto the image.
"""

from __future__ import annotations

from .aavso import (
    Band,
    CatalogError,
    ComparisonStar,
    VariableStar,
    vsp_chart,
    vsx_cone_search,
)
from .photometry import (
    ScoredComparison,
    comparisons_for_variable,
    rank_comparisons,
    separation_arcmin,
)

__all__ = [
    "Band",
    "CatalogError",
    "ComparisonStar",
    "ScoredComparison",
    "VariableStar",
    "comparisons_for_variable",
    "rank_comparisons",
    "separation_arcmin",
    "vsp_chart",
    "vsx_cone_search",
]
