"""Select an honest lexical comparison when original wording is unavailable."""

from influence.schemas.comparison import ComparisonRequest, ComparisonResult
from influence.schemas.scoring import ScoreRequest, TextChange
from influence.services.scoring import score_pair


def compare_texts(request: ComparisonRequest) -> ComparisonResult:
    """Use both redlines only when both originals are known; otherwise compare passages.

    The passage branch applies the same unigram/bigram matcher to whole texts, without
    claiming those texts were inserted. Evidence offsets refer to `new` in that mode.
    Worst-case O(n*m) diff work remains bounded by the scorer's input validation.
    """
    edits = request.amendment.old is not None and request.submission.old is not None
    result = score_pair(
        ScoreRequest(
            amendment=TextChange(
                old=(request.amendment.old or "") if edits else "", new=request.amendment.new
            ),
            submission=TextChange(
                old=(request.submission.old or "") if edits else "", new=request.submission.new
            ),
        )
    )
    return ComparisonResult(
        mode="edits" if edits else "passages",
        method="lexical-delta-v1" if edits else "lexical-passage-v1",
        score=result.score,
        evidence=result.evidence,
        negation_conflict=result.negation_conflict,
        limitations=(
            "Lexical similarity is not a probability or proof of influence.",
            "English lexical matching can miss paraphrases and cannot establish legal meaning.",
            "Both originals are known; shared deletions may reflect common starting law."
            if edits
            else "An original is unavailable. Full passages are compared, so unchanged legal "
            "wording can inflate similarity; any one-sided original is not used.",
        ),
    )
