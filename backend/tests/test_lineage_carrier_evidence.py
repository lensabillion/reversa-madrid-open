"""Carrier-specific occurrence evidence prevents merged phrases transferring provenance."""

from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError
from test_lineage_views import built
from test_origin import document

from influence.schemas.atlas import Amendment, ArticleVersion, SourceSpan
from influence.schemas.lineage import AdoptionEvidence, LineageView, OriginMatch, OriginSupport
from influence.services.lineage import Adoption, Rarity, adopt_records
from influence.services.origin import OriginError, find_origins

WORDS = tuple(f"rare{n}" for n in range(32))
FINAL = " ".join(WORDS[:24])


def article(text: str, stage: str = "final_act", key: str = "final") -> ArticleVersion:
    return ArticleVersion.model_validate(
        {
            "article_id": f"art:{key}:1",
            "procedure_id": "2099/0001(COD)",
            "document_id": f"doc:cellar:{key}",
            "stage": stage,
            "provision": "Article 1",
            "kind": "article",
            "text": text,
        }
    )


def amendment(
    key: int, text: str, *, old: str = "", tabled: date | None = date(2099, 3, 1)
) -> Amendment:
    return Amendment(
        amendment_id=f"am:2099-0001-COD:IMCO:{key}",
        procedure_id="2099/0001(COD)",
        document_id="doc:parltrack:amendments",
        stage="committee",
        old_text=old,
        new_text=text,
        tabled_on=tabled,
        author_ids=(f"actor:mep:{key}",),
    )


def matched(
    amendments: list[Amendment], submission: str, final: str = FINAL
) -> tuple[Adoption, tuple[OriginMatch, ...]]:
    articles = [article("baseline proposal wording", "proposal", "proposal"), article(final)]
    adoption = adopt_records(amendments, articles, [])
    origins = find_origins(
        adoption.phrases,
        adoption.adoptions,
        [document(text=submission)],
        rarity=Rarity.of(a.text for a in articles),
        amendments={a.amendment_id: a for a in amendments},
    )
    return adoption, origins


@pytest.mark.parametrize("unrelated_date", [date(2099, 1, 1), None])
def test_adjacent_carrier_cannot_inherit_the_submission_or_change_its_chronology(
    unrelated_date: date | None,
) -> None:
    left = amendment(1, " ".join(WORDS[:12]))
    right = amendment(2, " ".join(WORDS[12:24]), tabled=unrelated_date)
    adoption, origins = matched([left, right], left.new_text)
    assert len(adoption.phrases) == 1
    assert adoption.linked_units == 24
    (origin,) = origins
    assert origin.amendment_ids == (left.amendment_id,)
    assert origin.earliest_amendment_on == left.tabled_on
    assert origin.precedes is True
    assert len(origin.supports) == 1


def test_partial_overlaps_have_to_qualify_for_each_exact_carrier() -> None:
    left = amendment(1, " ".join(WORDS[:16]))
    right = amendment(2, " ".join(WORDS[12:24]))
    _, short = matched([left, right], left.new_text)
    assert [o.amendment_ids for o in short] == [(left.amendment_id,)]
    _, genuine = matched([left, right], " ".join(WORDS[6:22]))
    assert {o.amendment_ids for o in genuine} == {(left.amendment_id,), (right.amendment_id,)}
    assert {o.span.text for o in genuine} == {" ".join(WORDS[6:16]), " ".join(WORDS[12:22])}


def test_insertion_outside_the_intersection_is_not_adopted_origin_support() -> None:
    item = amendment(1, FINAL, old=" ".join(WORDS[:16]))
    adoption, origins = matched([item], " ".join(WORDS[:16]))
    assert adoption.phrases
    assert origins == ()


def test_the_longest_qualifying_occurrence_wins_after_the_insertion_check() -> None:
    final = " ".join(WORDS)
    item = amendment(1, final, old=" ".join(WORDS[:20]) + " " + " ".join(WORDS[22:]))
    submission = " ".join(WORDS[:18]) + " unrelated " + " ".join(WORDS[18:26])
    _, origins = matched([item], submission, final)
    (origin,) = origins
    assert origin.span.text == " ".join(WORDS[18:26])
    assert origin.words == 8


def test_repeated_wording_uses_the_accepted_amendment_occurrence_with_unicode_offsets() -> None:
    wording = " ".join(WORDS[:12])
    old = f"😀 café {wording} separator"
    item = amendment(1, old + " " + wording, old=old)
    adoption, origins = matched([item], f"Résumé: {wording}", wording)
    (evidence,) = adoption.adoptions[0].evidence
    assert evidence.amendment_span.start == len(old) + 1
    assert evidence.amendment_span.text == wording
    assert item.new_text[evidence.amendment_span.start : evidence.amendment_span.end] == wording
    (support,) = origins[0].supports
    assert support.amendment_span == evidence.amendment_span
    assert support.final_span == evidence.final_span


def test_genuine_carriers_preserve_exact_groups_and_union_coverage() -> None:
    text = " ".join(WORDS[:12])
    first, second = amendment(1, text), amendment(2, text)
    adoption, origins = matched([first, second], text, text)
    assert adoption.linked_units == adoption.changed_units == 12
    (origin,) = origins
    assert origin.amendment_ids == (first.amendment_id, second.amendment_id)
    assert len(origin.supports) == 2
    reversed_adoption, reversed_origins = matched([second, first], text, text)
    assert reversed_adoption == adoption
    assert reversed_origins == origins


def test_invalid_carrier_records_fail_before_a_view_can_publish(tmp_path: Path) -> None:
    view = built(tmp_path)
    evidence = view.adoptions[0].evidence[0]
    support = view.origins[0].supports[0]
    for update, reason in [
        (
            {"amendment_span": evidence.amendment_span.model_copy(update={"field": "text"})},
            "quotes amendment",
        ),
        (
            {"final_span": evidence.final_span.model_copy(update={"field": "new_text"})},
            "quotes amendment",
        ),
        (
            {"final_span": evidence.final_span.model_copy(update={"text": "different", "end": 9})},
            "eight consecutive",
        ),
        (
            {
                "amendment_span": evidence.amendment_span.model_copy(
                    update={"text": "too short", "end": 9}
                ),
                "final_span": evidence.final_span.model_copy(
                    update={"text": "too short", "end": 9}
                ),
            },
            "eight consecutive",
        ),
        ({"inserted_word_offsets": ()}, "Inserted word"),
        ({"inserted_word_offsets": (1, 1)}, "Inserted word"),
        ({"inserted_word_offsets": (2, 1)}, "Inserted word"),
        ({"inserted_word_offsets": (-1,)}, "Inserted word"),
        ({"inserted_word_offsets": (18,)}, "Inserted word"),
    ]:
        with pytest.raises(ValidationError, match=reason):
            AdoptionEvidence.model_validate(evidence.model_copy(update=update).model_dump())
    for field in ("submission_span", "amendment_span", "final_span"):
        span = getattr(support, field)
        assert isinstance(span, SourceSpan)
        for update, reason in [
            ({"field": "old_text"}, "Origin support quotes"),
            ({"text": "different", "end": span.start + 9}, "eight consecutive"),
        ]:
            with pytest.raises(ValidationError, match=reason):
                OriginSupport.model_validate(
                    support.model_copy(update={field: span.model_copy(update=update)}).model_dump()
                )


def test_v2_rejects_broken_carrier_and_origin_references(tmp_path: Path) -> None:
    view = built(tmp_path)
    adoption = view.adoptions[0]
    evidence = adoption.evidence[0]
    origin = view.origins[0]
    support = origin.supports[0]

    def invalid(candidate: LineageView, reason: str) -> None:
        with pytest.raises(ValidationError, match=reason):
            LineageView.model_validate(candidate.model_dump())

    def with_evidence(**updates: object) -> LineageView:
        return view.model_copy(
            update={
                "adoptions": (
                    adoption.model_copy(
                        update={"evidence": (evidence.model_copy(update=updates),)}
                    ),
                )
            }
        )

    def with_support(**updates: object) -> LineageView:
        return view.model_copy(
            update={
                "origins": (
                    origin.model_copy(update={"supports": (support.model_copy(update=updates),)}),
                )
            }
        )

    invalid(
        view.model_copy(update={"adoptions": (adoption.model_copy(update={"evidence": ()}),)}),
        "every phrase",
    )
    invalid(
        view.model_copy(
            update={"adoptions": (adoption.model_copy(update={"evidence": (evidence, evidence)}),)}
        ),
        "Duplicate adoption",
    )
    invalid(
        with_evidence(
            amendment_span=evidence.amendment_span.model_copy(
                update={"record_id": "am:2099-0001-COD:IMCO:999"}
            )
        ),
        "own amendment",
    )
    invalid(
        with_evidence(
            final_span=evidence.final_span.model_copy(update={"record_id": "art:wrong:1"})
        ),
        "no listed final",
    )
    invalid(
        with_evidence(
            final_span=evidence.final_span.model_copy(
                update={"start": evidence.final_span.start + 1, "end": evidence.final_span.end + 1}
            )
        ),
        "no listed final",
    )
    # A same-length/same-folded quote is still invalid if its exact source characters differ.
    invalid(
        with_evidence(
            final_span=evidence.final_span.model_copy(
                update={"text": evidence.final_span.text.swapcase()}
            )
        ),
        "exact parent occurrence",
    )
    invalid(
        view.model_copy(update={"origins": (origin.model_copy(update={"supports": ()}),)}),
        "needs exact carrier",
    )
    invalid(
        view.model_copy(
            update={"origins": (origin.model_copy(update={"kind": "semantic", "similarity": 0.9}),)}
        ),
        "kinds must agree",
    )
    invalid(
        view.model_copy(
            update={"origins": (origin.model_copy(update={"supports": (support, support)}),)}
        ),
        "Duplicate origin",
    )
    invalid(
        view.model_copy(
            update={
                "adopted_phrases": (
                    view.adopted_phrases[0].model_copy(
                        update={"kind": "semantic", "similarity": 0.9}
                    ),
                )
            }
        ),
        "only verbatim adopted phrases",
    )
    invalid(
        view.model_copy(update={"adoptions": (adoption.model_copy(update={"kind": "semantic"}),)}),
        "own amendment and phrase",
    )
    invalid(
        with_evidence(phrase_id="phrase:deadbeefdeadbeef").model_copy(
            update={"schema_version": "lineage-1"}
        ),
        "own amendment and phrase",
    )
    invalid(with_support(adoption_evidence_id="missing"), "missing adoption")
    invalid(with_support(amendment_id="am:2099-0001-COD:IMCO:999"), "exact origin and carrier")
    invalid(
        with_support(
            submission_span=support.submission_span.model_copy(
                update={
                    "start": support.submission_span.start + 1,
                    "end": support.submission_span.end + 1,
                }
            )
        ),
        "exact origin and carrier",
    )
    invalid(
        with_support(
            amendment_span=support.amendment_span.model_copy(
                update={"record_id": "am:2099-0001-COD:IMCO:999"}
            )
        ),
        "exact parent occurrence",
    )
    invalid(
        view.model_copy(
            update={
                "origins": (
                    origin.model_copy(
                        update={"amendment_ids": (origin.amendment_ids[0], origin.amendment_ids[0])}
                    ),
                )
            }
        ),
        "exactly the amendments",
    )
    invalid(
        view.model_copy(
            update={"origins": (origin.model_copy(update={"words": origin.words + 1}),)}
        ),
        "word count",
    )
    invalid(
        view.model_copy(
            update={
                "origins": (
                    origin.model_copy(update={"precedes": False, "eligibility": "amendment_first"}),
                )
            }
        ),
        "chronology",
    )

    # Removing a letter preserves token count/folding across all three projections but
    # violates the exact parent's word boundary.
    projections = {
        name: getattr(support, name).model_copy(
            update={
                "start": getattr(support, name).start + 1,
                "text": getattr(support, name).text[1:],
            }
        )
        for name in ("submission_span", "amendment_span", "final_span")
    }
    short_support = support.model_copy(update=projections)
    invalid(
        view.model_copy(
            update={
                "origins": (
                    origin.model_copy(
                        update={"span": short_support.submission_span, "supports": (short_support,)}
                    ),
                )
            }
        ),
        "word boundaries",
    )

    # Identical words at a different location cannot substitute for the supported final occurrence.
    words = " ".join(f"rare{number}" for number in range(8))
    repeated = f"{words} {words}"
    am_span = evidence.amendment_span.model_copy(
        update={"start": 0, "end": len(repeated), "text": repeated}
    )
    final_span = evidence.final_span.model_copy(
        update={"start": 0, "end": len(repeated), "text": repeated}
    )
    ev = evidence.model_copy(
        update={"amendment_span": am_span, "final_span": final_span, "inserted_word_offsets": (15,)}
    )
    sub = support.submission_span.model_copy(update={"start": 0, "end": len(words), "text": words})
    first_am = am_span.model_copy(update={"end": len(words), "text": words})
    first_final = final_span.model_copy(update={"end": len(words), "text": words})
    second_final = final_span.model_copy(update={"start": len(words) + 1, "text": words})
    projected = support.model_copy(
        update={"submission_span": sub, "amendment_span": first_am, "final_span": second_final}
    )
    repeated_view = view.model_copy(
        update={
            "adopted_phrases": (
                view.adopted_phrases[0].model_copy(
                    update={"text": repeated, "words": 16, "final_spans": (final_span,)}
                ),
            ),
            "adoptions": (adoption.model_copy(update={"evidence": (ev,)}),),
            "origins": (
                origin.model_copy(update={"span": sub, "words": 8, "supports": (projected,)}),
            ),
        }
    )
    invalid(repeated_view, "projections must align")
    aligned = projected.model_copy(update={"final_span": first_final})
    invalid(
        repeated_view.model_copy(
            update={
                "origins": (
                    origin.model_copy(update={"span": sub, "words": 8, "supports": (aligned,)}),
                )
            }
        ),
        "intersect an inserted word",
    )


def test_v2_unknown_supported_dates_remain_unknown(tmp_path: Path) -> None:
    view = built(tmp_path)
    adoption = view.adoptions[0]
    origin = view.origins[0]
    undated_carrier = view.model_copy(
        update={
            "adoptions": (adoption.model_copy(update={"tabled_on": None}),),
            "origins": (
                origin.model_copy(
                    update={
                        "earliest_amendment_on": None,
                        "precedes": None,
                        "eligibility": "unknown_date",
                    }
                ),
            ),
        }
    )
    assert (
        LineageView.model_validate(undated_carrier.model_dump()).origins[0].eligibility
        == "unknown_date"
    )
    undated_source = view.model_copy(
        update={
            "origins": (
                origin.model_copy(
                    update={"published_at": None, "precedes": None, "eligibility": "unknown_date"}
                ),
            )
        }
    )
    assert (
        LineageView.model_validate(undated_source.model_dump()).origins[0].eligibility
        == "unknown_date"
    )


def test_origin_search_refuses_missing_or_corrupted_carrier_source() -> None:
    item = amendment(1, FINAL)
    adopted, _ = matched([item], FINAL)
    carrier = adopted.adoptions[0]
    evidence = carrier.evidence[0]
    docs = [document(text=FINAL)]
    for changed, reason in [
        (carrier.model_copy(update={"evidence": ()}), "lacks exact carrier"),
        (
            carrier.model_copy(
                update={
                    "evidence": (
                        evidence.model_copy(
                            update={
                                "amendment_span": evidence.amendment_span.model_copy(
                                    update={"record_id": "am:2099-0001-COD:IMCO:2"}
                                )
                            }
                        ),
                    )
                }
            ),
            "different amendment",
        ),
    ]:
        with pytest.raises(OriginError, match=reason):
            find_origins(adopted.phrases, [changed], docs, rarity=Rarity(frozenset()))
    with pytest.raises(OriginError, match="exact source"):
        find_origins(
            adopted.phrases,
            [carrier],
            docs,
            rarity=Rarity(frozenset()),
            amendments={item.amendment_id: item.model_copy(update={"new_text": "wrong source"})},
        )


def test_repeated_final_occurrences_and_equal_submission_ties_remain_distinct() -> None:
    wording = " ".join(WORDS[:12])
    final = f"😀 {wording} unrelated {wording}"
    item = amendment(1, wording)
    adopted, origins = matched([item], f"{wording} separated {wording}", final)
    evidence = adopted.adoptions[0].evidence
    assert len(evidence) == len(origins) == 2
    assert len({entry.evidence_id for entry in evidence}) == 2
    assert {entry.final_span.start for entry in evidence} == {2, len(f"😀 {wording} unrelated ")}
    assert (adopted.linked_units, adopted.changed_units) == (24, 25)
    for origin in origins:
        assert origin.span.start == 0
        (support,) = origin.supports
        parent = next(
            entry for entry in evidence if entry.evidence_id == support.adoption_evidence_id
        )
        assert support.final_span == parent.final_span
        assert final[support.final_span.start : support.final_span.end] == wording


def test_article_and_document_order_do_not_change_occurrence_identities() -> None:
    wording = "café straße ρυθμός 東京 alpha beta gamma delta epsilon"
    items = [amendment(2, wording), amendment(1, wording)]
    articles = [
        article("baseline proposal wording", "proposal", "proposal"),
        article(wording, key="z"),
        article(wording, key="a"),
        *(
            article(f"other neutral text {number}", "proposal", f"background-{number}")
            for number in range(40)
        ),
    ]
    documents = [document("2", f"😀 {wording}"), document("1", f"🧪 {wording}")]
    first = adopt_records(items, articles, [])
    second = adopt_records(list(reversed(items)), list(reversed(articles)), [])
    assert first == second
    assert first.linked_units == first.changed_units == 18
    found = find_origins(
        first.phrases, first.adoptions, documents, rarity=Rarity.of(a.text for a in articles)
    )
    reversed_found = find_origins(
        second.phrases,
        second.adoptions,
        list(reversed(documents)),
        rarity=Rarity.of(a.text for a in reversed(articles)),
    )
    assert found == reversed_found
    assert len(found) == 4
    for origin in found:
        assert len(origin.supports) == 2
        source = next(
            text.text for document, text in documents if document.document_id == origin.document_id
        )
        assert source[origin.span.start : origin.span.end] == wording
