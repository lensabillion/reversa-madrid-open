"""The two harness scorers that read a proposal as prose, with the original unknown."""

from practice_fixture import labelled

from influence.practice.prose import prose_coverage_scores, prose_dice_scores
from influence.repositories.lobbyplag import RawText

COPY = "providers shall keep technical logs for at least six months after the system is sold"


def _pair(amendment_new: str, proposal_new: str, key: str = "a") -> object:
    pair = labelled("org", key, key, True, key).pair
    return type(pair)(
        candidate_id=pair.candidate_id,
        amendment_id=pair.amendment_id,
        proposal_id=pair.proposal_id,
        organization_id=pair.organization_id,
        amendment=RawText(old="providers shall keep technical logs", new=amendment_new),
        submission=RawText(old="ignored", new=proposal_new),
    )


def test_a_proposal_that_repeats_the_inserted_phrase_outscores_an_unrelated_one() -> None:
    copy = _pair(
        COPY, "we ask that " + COPY[len("providers shall keep technical logs ") :] + " too"
    )
    other = _pair(COPY, "completely different words about gardening and pizza recipes today", "b")
    for scorer in (prose_dice_scores, prose_coverage_scores):
        copied, unrelated = scorer([], [copy, other])  # type: ignore[list-item]
        assert 0.0 <= unrelated < copied <= 1.0


def test_coverage_reads_only_the_proposals_new_wording() -> None:
    one = _pair(COPY, "x")
    assert prose_coverage_scores([], [one]) == [0.0]  # type: ignore[list-item]


def test_text_the_scorer_cannot_run_scores_zero() -> None:
    too_long = _pair("word " * 900, "some proposal text here")
    empty = _pair(COPY, "")
    assert prose_dice_scores([], [too_long, empty]) == [0.0, 0.0]  # type: ignore[list-item]
    assert prose_coverage_scores([], [too_long]) == [0.0]  # type: ignore[list-item]
