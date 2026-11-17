"""HTTP routes of Review's sessions, curves and frames (rows A67-A75, ``protocol.md``
"Review (wave 7): sessions, curves, frames").

:func:`add_routes` registers them on the token-protected ``/api`` router and gives
the hub its two services (``hub.review``, ``hub.files``) when it has none.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Query, Response
from pydantic import BaseModel, ConfigDict, Field

from argos.server.files import FileService
from argos.server.review import ReviewService

if TYPE_CHECKING:  # pragma: no cover
    from argos.server.hub import Hub

_PATH = Field(min_length=1, max_length=4096)


class _Body(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


class PathBody(_Body):
    path: str = _PATH


class MeasureStarBody(_Body):
    path: str = _PATH
    x: float = Field(allow_inf_nan=False)
    y: float = Field(allow_inf_nan=False)
    radius: int | None = Field(default=None, ge=2, le=50)
    snap: bool = True


def add_routes(api: APIRouter, hub: "Hub") -> None:
    """Register rows A67-A75 on *api* (the ``/api`` router)."""
    if getattr(hub, "review", None) is None:
        hub.review = ReviewService(hub)  # type: ignore[attr-defined]
    if getattr(hub, "files", None) is None:
        hub.files = FileService(hub)  # type: ignore[attr-defined]
    review: ReviewService = hub.review  # type: ignore[attr-defined]
    files: FileService = hub.files  # type: ignore[attr-defined]

    @api.post("/sessions/scan", status_code=202)
    def sessions_scan() -> dict[str, Any]:
        job = review.start_scan()
        return {"job_id": job["id"], "job": job}

    @api.post("/review/session", status_code=202)
    def review_open(body: PathBody) -> dict[str, Any]:
        job = review.start_open(body.path)
        return {"job_id": job["id"], "job": job}

    @api.get("/review/session")
    def review_session(path: str = Query(min_length=1, max_length=4096)) -> dict[str, Any]:
        return review.session_record(path)

    @api.get("/review/session/curves")
    def review_curves(path: str = Query(min_length=1, max_length=4096)) -> dict[str, Any]:
        return review.session_curves(path)

    @api.get("/review/live/curves")
    def review_live_curves() -> dict[str, Any]:
        return review.live_curves()

    @api.post("/review/import-csv")
    def review_import_csv(body: PathBody) -> dict[str, Any]:
        return review.import_csv(body.path)

    @api.get("/files/frame")
    def files_frame(
        path: str = Query(min_length=1, max_length=4096),
        view: str = Query(default="raw", max_length=20),
    ) -> Response:
        return Response(
            content=files.frame_bytes(path, view), media_type="application/octet-stream"
        )

    @api.get("/files/fits-header")
    def files_header(path: str = Query(min_length=1, max_length=4096)) -> dict[str, Any]:
        return files.header(path)

    @api.post("/files/measure-star")
    def files_measure(body: MeasureStarBody) -> dict[str, Any]:
        return files.measure(body.path, body.x, body.y, body.radius, body.snap)

    @api.post("/files/solve", status_code=202)
    def files_solve(body: PathBody) -> dict[str, Any]:
        job = files.start_solve(body.path)
        return {"job_id": job["id"], "job": job}

    @api.get("/files/solution")
    def files_solution(path: str = Query(min_length=1, max_length=4096)) -> dict[str, Any]:
        return files.solution(path)

    @api.post("/files/catalogue", status_code=202)
    def files_catalogue(body: PathBody) -> dict[str, Any]:
        job = files.start_catalogue(body.path)
        return {"job_id": job["id"], "job": job}


__all__ = ["add_routes"]
