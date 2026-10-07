"""Read-only lineage views: the laws `influence lineage` has built, and one law's view.

Both routes are cacheable (`view_cache.py`): the validators come from the files' stats,
taken before any read, so a 304 never reads or parses a view.
"""

import os
from pathlib import Path
from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi import Path as PathParameter

from influence.routers.view_cache import NO_STORE, max_age_from, not_modified, validators
from influence.schemas.atlas_view import SLUG_PATTERN
from influence.schemas.lineage import LineageLawList, LineageView
from influence.services.lineage_views import (
    list_lineage_views,
    read_lineage_view,
    view_stat,
    view_stats,
)
from influence.services.pipeline import PipelineError

router = APIRouter(prefix="/api/v1")
# Read at import, which is app start: an invalid value stops the API before it serves.
VIEW_MAX_AGE = max_age_from(os.environ)
NOT_MODIFIED: dict[int | str, dict[str, object]] = {
    304: {"description": "The cached copy is current: If-None-Match matched the ETag"}
}


def get_data_root(request: Request) -> Path:
    """The law bundles' root, set on the app by `create_app`."""
    return cast("Path", request.app.state.atlas_data_root)


DataRoot = Annotated[Path, Depends(get_data_root)]


def _no_view(slug: str) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail=f"No lineage view for {slug}: run `make lineage LAW=...` for that law first",
        headers=NO_STORE,
    )


# Each route stats before it reads: if a rewrite lands in between, the old tag goes out
# with the new body and the next revalidation corrects it, whereas reading first could pair
# the new tag with the old body and keep that body cached until the next rewrite.


@router.get("/lineage", response_model=LineageLawList, responses=NOT_MODIFIED)
def laws(data_root: DataRoot, request: Request, response: Response) -> LineageLawList | Response:
    headers = validators(view_stats(data_root), VIEW_MAX_AGE)
    if not_modified(request, headers["ETag"]):
        return Response(status_code=304, headers=headers)
    try:
        listing = list_lineage_views(data_root)
    except PipelineError as error:
        raise HTTPException(status_code=500, detail=str(error), headers=NO_STORE) from error
    response.headers.update(headers)
    return listing


@router.get("/lineage/{slug}", response_model=LineageView, responses=NOT_MODIFIED)
def law_view(
    data_root: DataRoot,
    slug: Annotated[str, PathParameter(pattern=SLUG_PATTERN)],
    request: Request,
    response: Response,
) -> LineageView | Response:
    stat = view_stat(data_root, slug)
    if stat is None:
        raise _no_view(slug)
    headers = validators((stat,), VIEW_MAX_AGE)
    if not_modified(request, headers["ETag"]):
        return Response(status_code=304, headers=headers)
    try:
        view = read_lineage_view(data_root, slug)
    except PipelineError as error:
        raise HTTPException(status_code=500, detail=str(error), headers=NO_STORE) from error
    if view is None:  # removed between the stat and the read
        raise _no_view(slug)
    response.headers.update(headers)
    return view
