"""User text comparison uses the same service available to batch callers."""

from fastapi import APIRouter

from influence.schemas.comparison import ComparisonRequest, ComparisonResult
from influence.services.comparison import compare_texts

router = APIRouter(prefix="/api/v1", tags=["scoring"])


@router.post("/compare")
def compare(request: ComparisonRequest) -> ComparisonResult:
    return compare_texts(request)
