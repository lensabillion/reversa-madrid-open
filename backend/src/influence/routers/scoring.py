"""Pair scoring endpoint."""

from fastapi import APIRouter

from influence.schemas.scoring import ScoreRequest, ScoreResult
from influence.services.scoring import score_pair

router = APIRouter(prefix="/api/v1")


@router.post("/score")
def score(request: ScoreRequest) -> ScoreResult:
    return score_pair(request)
