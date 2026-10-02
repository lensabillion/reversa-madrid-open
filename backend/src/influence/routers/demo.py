"""Read-only endpoints for exploring the public LobbyPlag demo dataset."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from influence.dependencies import get_demo_service
from influence.schemas.demo import (
    AmendmentDetail,
    AmendmentPage,
    DatasetOverview,
    InfluenceGraph,
    OrganizationPage,
)
from influence.services.demo import DemoService

router = APIRouter(prefix="/api/v1")
Service = Annotated[DemoService, Depends(get_demo_service)]


@router.get("/demo")
def overview(service: Service) -> DatasetOverview:
    return service.overview()


@router.get("/amendments")
def amendments(
    service: Service,
    q: Annotated[str, Query(max_length=200)] = "",
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    verified_only: bool = False,
) -> AmendmentPage:
    return service.list_amendments(q, offset, limit, verified_only)


@router.get("/amendments/{amendment_id}")
def amendment(amendment_id: str, service: Service) -> AmendmentDetail:
    return service.amendment(amendment_id)


@router.get("/amendments/{amendment_id}/graph")
def graph(amendment_id: str, service: Service) -> InfluenceGraph:
    return service.graph(amendment_id)


@router.get("/organizations")
def organizations(service: Service) -> OrganizationPage:
    return service.organizations()
