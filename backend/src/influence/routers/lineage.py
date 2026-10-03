"""Read-only lineage views: the laws `influence lineage` has built, and one law's view."""

from typing import Annotated

from fastapi import APIRouter, HTTPException
from fastapi import Path as PathParameter

from influence.routers.atlas import DataRoot
from influence.schemas.atlas_view import SLUG_PATTERN
from influence.schemas.lineage import LineageLawList, LineageView
from influence.services.lineage_views import list_lineage_views, read_lineage_view
from influence.services.pipeline import PipelineError

router = APIRouter(prefix="/api/v1")


@router.get("/lineage")
def laws(data_root: DataRoot) -> LineageLawList:
    try:
        return list_lineage_views(data_root)
    except PipelineError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@router.get("/lineage/{slug}")
def law_view(
    data_root: DataRoot, slug: Annotated[str, PathParameter(pattern=SLUG_PATTERN)]
) -> LineageView:
    try:
        view = read_lineage_view(data_root, slug)
    except PipelineError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error
    if view is None:
        raise HTTPException(
            status_code=404,
            detail=f"No lineage view for {slug}: run `make lineage LAW=...` for that law first",
        )
    return view
