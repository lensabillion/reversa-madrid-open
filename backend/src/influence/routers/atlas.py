"""Read-only Atlas views: the laws `influence atlas` built, one law's view, clusters, findings."""

from pathlib import Path
from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi import Path as PathParameter

from influence.schemas.atlas_view import SLUG_PATTERN, AtlasLawList, AtlasView
from influence.schemas.coordinated import CoordinatedView
from influence.schemas.findings import LawFindings
from influence.services.coordinated import CoordinationError, read_coordination
from influence.services.pipeline import PipelineError, list_views, read_view
from influence.services.report import ReportError, law_findings, load_law

router = APIRouter(prefix="/api/v1")


def get_atlas_data_root(request: Request) -> Path:
    return cast("Path", request.app.state.atlas_data_root)


DataRoot = Annotated[Path, Depends(get_atlas_data_root)]


@router.get("/atlas")
def laws(data_root: DataRoot) -> AtlasLawList:
    """Every readable view; an unreadable one is listed under `invalid`, never a 500."""
    return list_views(data_root)


@router.get("/atlas/{slug}")
def law_view(
    data_root: DataRoot, slug: Annotated[str, PathParameter(pattern=SLUG_PATTERN)]
) -> AtlasView:
    try:
        view = read_view(data_root, slug)
    except PipelineError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error
    if view is None:
        raise HTTPException(
            status_code=404,
            detail=f"No Atlas view for {slug}: run `make atlas LAW=...` for that law first",
        )
    return view


@router.get("/atlas/{slug}/coordinated")
def law_coordinated(
    data_root: DataRoot, slug: Annotated[str, PathParameter(pattern=SLUG_PATTERN)]
) -> CoordinatedView:
    try:
        view = read_coordination(data_root, slug)
    except CoordinationError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error
    if view is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No coordinated amendments for {slug}: run `make atlas LAW=...` for that law first"
            ),
        )
    return view


@router.get("/atlas/{slug}/findings")
def law_findings_view(
    data_root: DataRoot, slug: Annotated[str, PathParameter(pattern=SLUG_PATTERN)]
) -> LawFindings:
    """The report's WHO, WHAT, TOWARDS, HOW and NEXT for one law, from the files on disk.

    A question whose files are not written answers `not_run` with the command that writes
    them; only a law that was never collected is a 404.
    """
    try:
        return law_findings(load_law(data_root, slug))
    except ReportError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
