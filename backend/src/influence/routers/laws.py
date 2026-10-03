"""Find any law by what was typed, and build its files from the explorer."""

from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi import Path as PathParameter

from influence.schemas.atlas_view import SLUG_PATTERN
from influence.schemas.laws import BuildRequest, BuildState, LawSearch
from influence.services.law_search import (
    BuildBusyError,
    CatalogMissingError,
    LawService,
    UnknownLawError,
)

router = APIRouter(prefix="/api/v1/laws")


def get_law_service(request: Request) -> LawService:
    return cast("LawService", request.app.state.law_service)


Service = Annotated[LawService, Depends(get_law_service)]
Slug = Annotated[str, PathParameter(pattern=SLUG_PATTERN)]


@router.get("/search")
def search(service: Service, q: Annotated[str, Query()]) -> LawSearch:
    if not q.strip():
        raise HTTPException(status_code=422, detail="Type a law: q is empty")
    try:
        return service.search(q)
    except CatalogMissingError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.post("/{slug}/build", status_code=202)
def start_build(service: Service, slug: Slug, request: BuildRequest | None = None) -> BuildState:
    steps = (request or BuildRequest()).steps
    try:
        return service.start_build(slug, steps)
    except CatalogMissingError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except UnknownLawError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except BuildBusyError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.get("/{slug}/build")
def build_state(service: Service, slug: Slug) -> BuildState:
    state = service.build_state(slug)
    if state is None:
        raise HTTPException(status_code=404, detail=f"No build of {slug} was started")
    return state
