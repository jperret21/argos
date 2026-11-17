"""HTTP routes of Review's exports and re-run (rows A76-A79, ``protocol.md``
"Review (wave 7): exports and re-run").

:func:`add_routes` registers them on the token-protected ``/api`` router and gives
the hub its two services (``hub.exports``, ``hub.rerun``) when it has none.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from argos.server.exports import ExportService
from argos.server.rerun import RerunService

if TYPE_CHECKING:  # pragma: no cover
    from argos.server.hub import Hub

_PATH = Field(default=None, min_length=1, max_length=4096)


class _Body(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


class SourceBody(_Body):
    kind: Literal["session", "import", "live"]
    path: str | None = _PATH


class AavsoBody(_Body):
    source: SourceBody
    filter: str | None = Field(default=None, max_length=40)
    keys: list[str] | None = Field(default=None, max_length=1000)
    check_key: str | None = Field(default=None, max_length=200)
    use_check: bool = True
    obscode: str | None = Field(default=None, max_length=40)
    filt: str | None = Field(default=None, max_length=40)
    chart: str | None = Field(default=None, max_length=40)


class AavsoExportBody(AavsoBody):
    path: str | None = _PATH
    overwrite: bool = False


class CsvExportBody(_Body):
    source: SourceBody
    keys: list[str] | None = Field(default=None, max_length=1000)
    filter: str | None = Field(default=None, max_length=40)
    path: str | None = _PATH
    overwrite: bool = False


class RerunBody(_Body):
    session: str = Field(min_length=1, max_length=4096)
    frames: str | None = _PATH
    targets: Literal["session", "live"] = "session"
    reference: Literal["solve", "live"] = "solve"
    reference_frame: str | None = _PATH
    diagnostics: bool | None = None


def _plain(body: _Body) -> dict[str, Any]:
    data = body.model_dump()
    source = data.get("source")
    if isinstance(source, dict) and source.get("path") is None:
        source.pop("path")
    return data


def add_routes(api: APIRouter, hub: "Hub") -> None:
    """Register rows A76-A79 on *api* (the ``/api`` router)."""
    if getattr(hub, "exports", None) is None:
        hub.exports = ExportService(hub)  # type: ignore[attr-defined]
    if getattr(hub, "rerun", None) is None:
        hub.rerun = RerunService(hub)  # type: ignore[attr-defined]
    exports: ExportService = hub.exports  # type: ignore[attr-defined]
    rerun: RerunService = hub.rerun  # type: ignore[attr-defined]

    @api.post("/export/aavso/preview")
    def export_aavso_preview(body: AavsoBody) -> dict[str, Any]:
        return exports.preview(_plain(body))

    @api.post("/export/aavso", status_code=202)
    def export_aavso(body: AavsoExportBody) -> dict[str, Any]:
        job = exports.export_aavso(_plain(body))
        return {"job_id": job["id"], "job": job}

    @api.post("/export/csv", status_code=202)
    def export_csv(body: CsvExportBody) -> dict[str, Any]:
        job = exports.export_csv(_plain(body))
        return {"job_id": job["id"], "job": job}

    @api.post("/review/rerun/plan")
    def rerun_plan(body: RerunBody) -> dict[str, Any]:
        return rerun.plan(body.model_dump())

    @api.post("/review/rerun", status_code=202)
    def rerun_start(body: RerunBody) -> dict[str, Any]:
        job = rerun.start(body.model_dump())
        return {"job_id": job["id"], "job": job}
