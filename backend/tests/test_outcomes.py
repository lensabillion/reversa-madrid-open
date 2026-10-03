"""Outcome tracing: text survival by aligned provision, with unknown kept apart from lost."""

import json
from datetime import UTC, date, datetime
from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

from influence.schemas.atlas import (
    Amendment,
    ArticleStage,
    ArticleVersion,
    Ask,
    LinkAssessment,
    Outcome,
    SourceSpan,
    span_matches,
)
from influence.services.outcomes import outcome_result, trace_outcomes

FIXTURES = Path(__file__).parent / "fixtures" / "atlas"


def _rows(name: str) -> list[dict[str, object]]:
    lines = (FIXTURES / name).read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines]


def _fixture_outcomes() -> dict[tuple[str, str], Outcome]:
    amendments = {r["amendment_id"]: Amendment.model_validate(r) for r in _rows("amendments.jsonl")}
    links = {r["ask_id"]: LinkAssessment.model_validate(r) for r in _rows("links.jsonl")}
    versions = [ArticleVersion.model_validate(r) for r in _rows("articles.jsonl")]
    traced: dict[tuple[str, str], Outcome] = {}
    for row in _rows("asks.jsonl"):
        ask = Ask.model_validate(row)
        link = links.get(ask.ask_id)
        amendment = amendments[link.amendment_id] if link else None
        pool = [v for v in versions if v.procedure_id == ask.procedure_id]
        for outcome in trace_outcomes(ask, amendment, link, pool):
            traced[(ask.ask_id, outcome.stage)] = outcome
    return traced


def test_fixture_outcomes_match_the_contract_examples() -> None:
    expected = {
        (str(r["ask_id"]), str(r["stage"])): Outcome.model_validate(r)
        for r in _rows("outcomes.jsonl")
    }
    traced = _fixture_outcomes()
    # Two examples differ on purpose. `a-acme` has no provision that lines up, which is
    # unknown here (failing to find the place is not proof the wording was lost), where the
    # fixture says not_observed. `a-city` keeps the label "wording": its requested word
    # survives verbatim, and only the surrounding scope changed; the fixture says reworded.
    differ = {("ask:a-acme", "final_act"), ("ask:a-city", "final_act")}
    for key, outcome in expected.items():
        got = traced[key]
        if key in differ:
            continue
        assert (got.result, got.kind, got.article_id) == (
            outcome.result,
            outcome.kind,
            outcome.article_id,
        ), key
    assert traced[("ask:a-acme", "final_act")].result == "unknown"
    city = traced[("ask:a-city", "final_act")]
    assert (city.result, city.article_id) == ("partial", "art:32099R0001:article-11-2")


def test_a_contradicted_ask_does_not_inherit_the_amendments_win() -> None:
    traced = _fixture_outcomes()
    watch = traced[("ask:a-watch", "final_act")]
    assert (watch.relation, watch.result) == ("direct_to_final", "not_observed")
    assert ("ask:a-watch", "heard") not in traced


def test_a_direct_ask_gets_only_a_final_act_outcome() -> None:
    traced = _fixture_outcomes()
    stages = {stage for ask, stage in traced if ask == "ask:a-undated"}
    assert stages == {"final_act"}


def _ask(text: str) -> Ask:
    return Ask(
        ask_id="ask:x",
        procedure_id="2099/0001(COD)",
        actor_id="actor:name:hys_feedback.x",
        document_id="doc:hys_feedback:1",
        span=SourceSpan(record_id="doc:hys_feedback:1", start=0, end=len(text), text=text),
        submitted_at=datetime(2099, 2, 1, tzinfo=UTC),
        extraction_method="test",
    )


def _amendment(old: str | None, new: str) -> Amendment:
    return Amendment(
        amendment_id="am:2099-0001-COD:IMCO:1",
        procedure_id="2099/0001(COD)",
        document_id="doc:parltrack:x",
        stage="committee",
        tabled_on=date(2099, 3, 1),
        old_text=old,
        new_text=new,
    )


def _link(amendment: Amendment, status: str = "published") -> LinkAssessment:
    base = {
        "link_id": "link:x",
        "procedure_id": amendment.procedure_id,
        "amendment_id": amendment.amendment_id,
        "ask_id": "ask:x",
        "status": status,
        "support_score": 0.5,
        "time_eligibility": "ask_first",
        "method": "test",
        "method_revision": "t1",
    }
    if status == "published":
        span = {"record_id": "am:x", "field": "new_text", "start": 0, "end": 1, "text": "P"}
        base |= {"tier": "copied", "amendment_spans": [span], "ask_spans": [span]}
    return LinkAssessment.model_validate(base)


def _version(stage: ArticleStage, text: str, name: str = "Article 5(1)") -> ArticleVersion:
    return ArticleVersion(
        article_id=f"art:{stage}:{name.replace(' ', '-')}",
        procedure_id="2099/0001(COD)",
        document_id=f"doc:cellar:{stage}",
        stage=stage,
        provision=name,
        kind="paragraph",
        text=text,
    )


OLD = "Providers shall keep logs."
NEW = "Providers shall keep logs for six months."


def test_a_provision_is_found_by_text_even_when_it_is_renumbered() -> None:
    amendment = _amendment(OLD, NEW)
    versions = [
        _version("proposal", OLD, "Article 5(1)"),
        _version("final_act", "Unrelated recital about pizza.", "Article 1"),
        _version("final_act", NEW, "Article 17(4)"),
    ]
    final = trace_outcomes(_ask(NEW), amendment, _link(amendment), versions)[2]
    assert (final.result, final.article_id) == ("full", "art:final_act:Article-17(4)")
    assert all(span_matches(span, NEW) for span in final.spans)


def test_missing_stage_text_is_unknown_with_a_reason_not_a_loss() -> None:
    amendment = _amendment(OLD, NEW)
    outcomes = trace_outcomes(_ask(NEW), amendment, _link(amendment), [])
    assert [o.result for o in outcomes] == ["full", "unknown", "unknown"]
    assert all(o.reason for o in outcomes[1:])


def test_punctuation_only_insert_is_not_a_word_match_in_an_aligned_provision() -> None:
    # Keep this guard deterministic: random word/punctuation examples need not reach it.
    amendment = _amendment("Providers shall keep logs.", "Providers shall keep logs.!")
    final_text = "Providers shall safely keep logs."
    final = trace_outcomes(
        _ask(amendment.new_text),
        amendment,
        _link(amendment),
        [_version("final_act", final_text)],
    )[2]
    assert final.result == "not_observed"
    assert final.spans == ()


def test_no_aligned_provision_is_unknown() -> None:
    amendment = _amendment(OLD, NEW)
    versions = [_version("final_act", "Something entirely about other matters.")]
    final = trace_outcomes(_ask(NEW), amendment, _link(amendment), versions)[2]
    assert final.result == "unknown"
    assert "lines up" in (final.reason or "")


def test_an_unpublished_link_is_not_heard() -> None:
    amendment = _amendment(OLD, NEW)
    heard = trace_outcomes(_ask(NEW), amendment, _link(amendment, "unconfirmed"), [])[0]
    assert (heard.result, heard.link_id, heard.relation) == ("not_observed", None, "via_amendment")


def test_requested_words_with_changed_surroundings_are_partial() -> None:
    amendment = _amendment(OLD, NEW)
    versions = [_version("final_act", "Providers shall keep detailed logs for six months.")]
    final = trace_outcomes(_ask(NEW), amendment, _link(amendment), versions)[2]
    assert final.result == "partial"
    assert final.reason


def test_requested_words_missing_are_not_observed() -> None:
    amendment = _amendment(OLD, NEW)
    versions = [_version("final_act", "Providers shall keep logs.")]
    final = trace_outcomes(_ask(NEW), amendment, _link(amendment), versions)[2]
    assert final.result == "not_observed"


def test_a_deletion_wins_when_the_words_are_gone_and_loses_when_they_remain() -> None:
    amendment = _amendment(
        "Providers shall keep logs and audit reports.", "Providers shall keep logs."
    )
    link = _link(amendment)
    kept = [_version("final_act", "Providers shall keep logs and audit reports.")]
    gone = [_version("final_act", "Providers shall keep logs.")]
    assert trace_outcomes(_ask("x"), amendment, link, kept)[2].result == "not_observed"
    won = trace_outcomes(_ask("x"), amendment, link, gone)[2]
    assert (won.result, won.kind) == ("full", "deletion")
    assert won.spans


def test_a_replacement_with_the_old_words_still_present_is_partial() -> None:
    amendment = _amendment("The authority shall publish it.", "The authority may publish it.")
    versions = [_version("final_act", "The authority may publish it, and shall archive it.")]
    final = trace_outcomes(_ask("x"), amendment, _link(amendment), versions)[2]
    assert final.result == "partial"
    assert "removed" in (final.reason or "")


def test_a_direct_replacement_instruction_is_judged_on_its_new_words() -> None:
    ask = _ask("In Article 9, replace 'shall' with 'may': the authority may publish it.")
    versions = [_version("final_act", "The authority may publish it.", "Article 9")]
    final = trace_outcomes(ask, None, None, versions)[0]
    assert (final.result, final.relation) == ("full", "direct_to_final")


def test_a_direct_deletion_instruction_is_judged_on_what_remains() -> None:
    ask = _ask("Please delete 'and audit reports' from the duty: providers shall keep logs.")
    gone = [_version("final_act", "Providers shall keep logs.")]
    same = [_version("final_act", "Providers shall keep logs and audit reports.")]
    assert trace_outcomes(ask, None, None, same)[0].result == "not_observed"
    assert trace_outcomes(ask, None, None, gone)[0].result == "full"


def test_outcome_result_reads_a_stage_or_none() -> None:
    amendment = _amendment(OLD, NEW)
    outcomes = trace_outcomes(_ask(NEW), amendment, _link(amendment), [])
    assert outcome_result(outcomes, "heard") == "full"
    assert outcome_result(outcomes[:1], "final_act") is None


WORDS = st.sampled_from(["providers", "shall", "may", "keep", "logs", "six", "months", "not", "."])
SENTENCES = st.lists(WORDS, min_size=1, max_size=9).map(" ".join)


@given(old=SENTENCES, new=SENTENCES, final=SENTENCES)
def test_every_observed_outcome_quotes_text_that_is_really_in_the_provision(
    old: str, new: str, final: str
) -> None:
    amendment = _amendment(old, new)
    versions = [_version("final_act", final)]
    for outcome in trace_outcomes(_ask(new), amendment, _link(amendment), versions):
        if outcome.stage == "final_act" and outcome.result in ("full", "partial"):
            assert outcome.spans
            assert all(span_matches(span, final) for span in outcome.spans)
        if outcome.result == "unknown":
            assert outcome.reason


KEEP_TEXT = "Providers shall keep technical logs for the life of the product."


def _keep_ask() -> Ask:
    return _ask(KEEP_TEXT).model_copy(update={"direction": "keep"})


def test_a_keep_ask_wins_when_its_provision_comes_through_word_for_word() -> None:
    versions = [
        _version("proposal", KEEP_TEXT, "Article 5(1)"),
        _version("final_act", KEEP_TEXT.lower(), "Article 9(3)"),
    ]
    (final,) = trace_outcomes(_keep_ask(), None, None, versions)
    assert (final.result, final.kind, final.relation) == ("full", "status_quo", "direct_to_final")
    assert final.article_id == "art:final_act:Article-9(3)"
    assert final.spans
    assert all(span_matches(span, KEEP_TEXT.lower()) for span in final.spans)


def test_a_keep_ask_loses_when_the_provision_was_changed() -> None:
    versions = [
        _version("proposal", KEEP_TEXT),
        _version("final_act", "Providers shall keep technical logs for six months."),
    ]
    (final,) = trace_outcomes(_keep_ask(), None, None, versions)
    assert (final.result, final.kind) == ("not_observed", None)
    assert "changed" in (final.reason or "")


def test_a_keep_ask_is_unknown_when_a_text_is_missing_or_does_not_line_up() -> None:
    no_proposal = [_version("final_act", KEEP_TEXT)]
    assert trace_outcomes(_keep_ask(), None, None, no_proposal)[0].result == "unknown"
    no_final = [_version("proposal", KEEP_TEXT)]
    assert trace_outcomes(_keep_ask(), None, None, no_final)[0].result == "unknown"
    elsewhere = [_version("proposal", KEEP_TEXT), _version("final_act", "Pizza and gardening.")]
    final = trace_outcomes(_keep_ask(), None, None, elsewhere)[0]
    assert (final.result, "wants kept" in (final.reason or "")) == ("unknown", True)
    far_proposal = [_version("proposal", "Pizza and gardening."), _version("final_act", KEEP_TEXT)]
    assert "compare" in (trace_outcomes(_keep_ask(), None, None, far_proposal)[0].reason or "")


def test_a_keep_ask_is_never_traced_through_an_amendment() -> None:
    amendment = _amendment(OLD, NEW)
    outcomes = trace_outcomes(_keep_ask(), amendment, _link(amendment), [])
    assert [(o.stage, o.relation) for o in outcomes] == [("final_act", "direct_to_final")]
