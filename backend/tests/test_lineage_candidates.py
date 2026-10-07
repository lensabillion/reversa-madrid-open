"""The optional Jev shortlist preserves quotes, IDs, bounds and explicit unknowns."""

from collection_fixture import build_fixture

from influence.schemas.atlas import Amendment, Ask, Passage, SourceSpan, id_part
from influence.schemas.scoring import TextChange
from influence.services.lineage_candidates import (
    ASK_METHOD,
    amendment_direction,
    ask_limit_reason,
    asks_from_passages,
    find_candidates,
    requested_direction,
)
from influence.services.scoring import changed_spans

FIXTURE = build_fixture()


def passage(text: str) -> Passage:
    original = FIXTURE.passages[0]
    return Passage.model_validate(
        {
            **original.model_dump(),
            "span": SourceSpan(record_id=original.document_id, start=0, end=len(text), text=text),
        }
    )


def ask(text: str) -> Ask:
    return asks_from_passages((passage(text),))[0]


def amendment(old: str, new: str) -> Amendment:
    return Amendment.model_validate(
        {**FIXTURE.amendments[0].model_dump(), "old_text": old, "new_text": new}
    )


def test_passages_keep_the_exact_quote_identity_date_and_instruction_direction() -> None:
    source = passage("In Article 4, replace 'may' with 'shall'.")
    (request,) = asks_from_passages((source,))
    assert request.ask_id == f"ask:{id_part(source.passage_id)}"
    assert request.span == source.span
    assert request.document_id == source.document_id
    assert request.actor_id == source.actor_id
    assert request.submitted_at == source.submitted_at
    assert (request.direction, request.extraction_method) == ("stricter", ASK_METHOD)
    assert requested_direction("Providers should not be required to keep logs.") == "unknown"
    assert requested_direction("replace 'shall' with 'may'") == "weaker"
    assert requested_direction(f"insert '{'x' * 12001}'") == "unknown"


def test_changed_obligation_cues_are_read_in_both_directions_and_ties_stay_unknown() -> None:
    cases = [
        ("", "shall", "stricter"),
        ("may", "", "stricter"),
        ("must", "", "weaker"),
        ("", "optional", "weaker"),
        ("", "shall may", "unknown"),
        ("same", "same", "unknown"),
    ]
    for old, new, expected in cases:
        assert amendment_direction(changed_spans(TextChange(old=old, new=new))) == expected


def test_asks_are_not_truncated_or_silently_reinterpreted_when_outside_the_bounds() -> None:
    assert "no non-whitespace" in (ask_limit_reason(ask(" \n")) or "")
    assert "input bounds" in (ask_limit_reason(ask("!" * 801)) or "")
    assert "input bounds" in (ask_limit_reason(ask(f"insert '{'x' * 12001}'")) or "")
    assert ask_limit_reason(ask("We request technical logs.")) is None
    assert ask_limit_reason(ask("replace 'may' with 'shall'")) is None


def test_candidates_preserve_bm25_rank_score_and_pair_ids() -> None:
    requests = asks_from_passages(FIXTURE.passages)
    candidates = find_candidates(FIXTURE.amendments, requests)
    assert candidates
    for candidate in candidates:
        assert (
            candidate.candidate_id
            == f"cand:{id_part(candidate.amendment_id)}:{id_part(candidate.ask_id)}"
        )
        assert candidate.lexical_rank is not None
        assert candidate.lexical_rank <= 5
        assert candidate.retrieval_score > 0
        assert candidate.method == "bm25-passages-v1"
    assert find_candidates(FIXTURE.amendments, requests) == candidates


def test_blank_or_oversized_asks_cannot_displace_searchable_candidates() -> None:
    valid = ask("Providers shall retain technical logs.")
    invalid = ask("!" * 801).model_copy(update={"ask_id": "ask:over-limit"})
    item = amendment("", "technical logs")
    diagnostics: dict[str, str] = {}
    baseline = find_candidates((item,), (valid,))
    assert baseline
    assert find_candidates((item,), (invalid, valid), unsearchable_asks=diagnostics) == baseline
    assert "input bounds" in diagnostics[invalid.ask_id]
    assert find_candidates((item,), (invalid, valid)) == baseline


def test_unsearchable_amendments_report_bounds_and_case_only_edits() -> None:
    oversized = amendment("", "token " * 801)
    case_only = amendment("Technical logs", "technical logs")
    requests = (ask("technical logs"),)
    refused: list[str] = []
    assert find_candidates((oversized, case_only), requests, refused) == ()
    assert refused == [oversized.amendment_id, case_only.amendment_id]
    assert find_candidates((oversized, case_only), requests) == ()
