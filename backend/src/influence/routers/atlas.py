"""Read-only Atlas views: the laws `influence atlas` has built, and one law's view."""

from pathlib import Path
from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi import Path as PathParameter

from influence.schemas.atlas_view import SLUG_PATTERN, AtlasLawList, AtlasView
from influence.services.pipeline import PipelineError, list_views, read_view

router = APIRouter(prefix="/api/v1")


def get_atlas_data_root(request: Request) -> Path:
    return cast("Path", request.app.state.atlas_data_root)


DataRoot = Annotated[Path, Depends(get_atlas_data_root)]


@router.get("/atlas")
def laws(data_root: DataRoot) -> AtlasLawList:
    try:
        return list_views(data_root)
    except PipelineError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


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
