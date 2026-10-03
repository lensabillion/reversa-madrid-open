"""Passage splitting: exact offsets on any text, and sentence rules that fit legal prose."""

from datetime import UTC, datetime
from itertools import pairwise

import pytest
from hypothesis import given
from hypothesis import strategies as st

from influence.schemas.atlas import (
    CITIZENS_ACTOR_ID,
    DocumentText,
    SourceDocument,
    register_actor_id,
    span_matches,
)
from influence.services.passages import (
    PassageError,
    document_passages,
    split_passages,
    split_sentences,
)

PROCEDURE = "2021/0106(COD)"
SUBMITTED = datetime(2021, 8, 6, 21, 57, 37, tzinfo=UTC)


def sentences(text: str, *, max_words: int = 120) -> list[str]:
    return [text[start:end] for start, end, _ in split_sentences(text, max_words=max_words)]


def passages(text: str, *, max_sentences: int = 3, overlap: int = 1) -> list[str]:
    return [
        item.text for item in split_passages(text, max_sentences=max_sentences, overlap=overlap)
    ]


# Text built from the pieces that make splitting hard, plus arbitrary Unicode.
_PIECES = st.sampled_from(
    [". ", "! ", "? ", "\u2026 ", '." ', "\n", "\n\n", "\n- ", "\n1. ", " ", "Art. 5 ", "e.g. ",
     "No. 3 ", "2.5 ", "The ", "word ", "Page 3", "12", "\u00e9t\u00e9 ", "\U0001f600", "\t",
     "\u00a0", "\u2028"]
)  # fmt: skip
_TEXT = st.lists(st.one_of(_PIECES, st.text(max_size=8)), max_size=60).map("".join)


@given(
    text=st.one_of(st.text(), _TEXT),
    max_sentences=st.integers(min_value=1, max_value=4),
    overlap=st.integers(min_value=0, max_value=3),
    max_words=st.integers(min_value=1, max_value=12),
)
def test_offsets_always_index_the_unmodified_text(
    text: str, max_sentences: int, overlap: int, max_words: int
) -> None:
    if overlap >= max_sentences:
        with pytest.raises(PassageError):
            split_passages(text, max_sentences=max_sentences, overlap=overlap)
        return
    result = split_passages(text, max_sentences=max_sentences, overlap=overlap, max_words=max_words)
    for item in result:
        assert 0 <= item.start < item.end <= len(text)
        assert text[item.start : item.end] == item.text
        assert item.text == item.text.strip()
    # Passages advance: no passage repeats or sits inside the one before it.
    for before, after in pairwise(result):
        assert before.start < after.start
        assert before.end < after.end
    if overlap == 0:
        for before, after in pairwise(result):
            assert before.end <= after.start


def test_a_window_that_cannot_grow_is_not_repeated_inside_the_one_before() -> None:
    """Found by Hypothesis on a fresh checkout: the second window lay inside the first."""
    text = "A" + chr(10) + "- A" + chr(10) + "- A"
    result = split_passages(text, max_sentences=2, overlap=1, max_words=3)
    assert [(item.start, item.end) for item in result] == [(0, 5), (6, 9)]
    # Nothing is lost: every sentence's text is inside some passage.
    assert all(any(item.start <= at < item.end for item in result) for at in (0, 2, 4, 6, 8))


@given(text=st.one_of(st.text(), _TEXT))
def test_sentences_never_overlap_and_cover_every_letter_once(text: str) -> None:
    found = split_sentences(text, max_words=5)
    position = 0
    for start, end, words in found:
        assert position <= start < end
        assert 1 <= words <= 5
        assert len(text[start:end].split()) == words
        position = end


def test_abbreviations_decimals_and_initials_do_not_end_a_sentence() -> None:
    text = (
        "See Art. 5 of the proposal, e.g. the ban in para. 2. We ask that No. 3 be cut to "
        "2.5 percent! Is that clear? J. Smith of the U.S. Chamber agrees (cf. Annex III). Yes."
    )
    assert sentences(text) == [
        "See Art. 5 of the proposal, e.g. the ban in para. 2.",
        "We ask that No. 3 be cut to 2.5 percent!",
        "Is that clear?",
        "J. Smith of the U.S. Chamber agrees (cf. Annex III).",
        "Yes.",
    ]


def test_a_full_stop_followed_by_lower_case_continues_the_sentence() -> None:
    assert sentences("It costs approx. five euros etc. and more. Then it ends.") == [
        "It costs approx. five euros etc. and more.",
        "Then it ends.",
    ]
    assert sentences("Wait... what is this? Wait... What now.") == [
        "Wait... what is this?",
        "Wait...",
        "What now.",
    ]
    assert sentences("First\u2026 then more. End\u2026 Next one.") == [
        "First\u2026 then more.",
        "End\u2026",
        "Next one.",
    ]
    assert sentences('He said "delete it." Then he left.') == [
        'He said "delete it."',
        "Then he left.",
    ]


def test_pdf_line_wraps_join_and_blank_lines_and_bullets_split() -> None:
    text = (
        "We support the proposal\nbut the definition is too broad\n\n"
        "Our asks\n- delete Article 5\n\u2022 narrow Annex III\n"
        "1. The provider shall report\n(a) within a year\n  2. Review in 2025. Done"
    )
    assert sentences(text) == [
        "We support the proposal\nbut the definition is too broad",
        "Our asks",
        "- delete Article 5",
        "\u2022 narrow Annex III",
        "1. The provider shall report",
        "(a) within a year",
        "2. Review in 2025.",
        "Done",
    ]
    # A year that ends a sentence mid-line still ends it.
    assert sentences("Adopted in 2021. Applied later.") == ["Adopted in 2021.", "Applied later."]


def test_page_numbers_and_rules_are_not_sentences() -> None:
    text = "Real content here.\n\n3\n\nPage 4 of 12\n\n-----\n\n5 / 12\n\np. 7\n\nMore content."
    assert sentences(text) == ["Real content here.", "More content."]
    assert split_passages(" \n\n 12 \n\n ") == ()
    assert split_passages("") == ()


def test_an_overlong_sentence_is_cut_at_word_boundaries() -> None:
    text = "  " + " ".join(f"w{number}" for number in range(7)) + "  "
    assert sentences(text, max_words=3) == ["w0 w1 w2", "w3 w4 w5", "w6"]


def test_windows_hold_up_to_three_sentences_and_overlap_by_one() -> None:
    text = "A one. B two. C three. D four. E five."
    assert passages(text) == ["A one. B two. C three.", "C three. D four. E five."]
    assert passages(text, max_sentences=2, overlap=0) == [
        "A one. B two.",
        "C three. D four.",
        "E five.",
    ]
    assert passages(text, max_sentences=1, overlap=0) == [
        "A one.",
        "B two.",
        "C three.",
        "D four.",
        "E five.",
    ]
    assert passages("A one. B two. C three. D four.") == [
        "A one. B two. C three.",
        "C three. D four.",
    ]
    assert passages("Only one sentence") == ["Only one sentence"]


def test_a_window_stops_before_it_exceeds_the_word_limit() -> None:
    text = "One two three. Four five six. Seven eight nine. Ten."
    result = split_passages(text, max_words=6)
    assert [item.text for item in result] == [
        "One two three. Four five six.",
        "Four five six. Seven eight nine.",
        "Seven eight nine. Ten.",
    ]
    # A window of one sentence still advances although the overlap equals its size.
    single = split_passages(text, max_words=3)
    assert [item.text for item in single] == [
        "One two three.",
        "Four five six.",
        "Seven eight nine.",
        "Ten.",
    ]


@pytest.mark.parametrize(
    ("max_sentences", "overlap", "max_words"),
    [(0, 0, 120), (3, 3, 120), (3, -1, 120), (3, 1, 0)],
)
def test_impossible_window_settings_are_rejected(
    max_sentences: int, overlap: int, max_words: int
) -> None:
    with pytest.raises(PassageError):
        split_passages("Text.", max_sentences=max_sentences, overlap=overlap, max_words=max_words)


def make_document(document_id: str, language: str | None) -> SourceDocument:
    return SourceDocument(
        document_id=document_id,
        procedure_id=PROCEDURE,
        source_kind="hys_feedback",
        url="https://ec.europa.eu/info/law/better-regulation/api/allFeedback?publicationId=14488",
        published_at=SUBMITTED,
        retrieved_at=SUBMITTED,
        sha256="0" * 64,
        language=language,
        extraction_status="extracted",
    )


def test_document_passages_are_atlas_records_with_spans_into_the_text() -> None:
    body = "Caf\u00e9 \U0001f600 first. Delete Article 5. Keep Article 6. Narrow Annex III."
    document = make_document("doc:hys_feedback:2665651", "fr")
    text = DocumentText(document_id=document.document_id, text=body)
    actor = register_actor_id("718971811339-46")
    result = document_passages(
        document, text, procedure_id=PROCEDURE, actor_id=actor, submitted_at=SUBMITTED
    )
    assert [item.passage_id for item in result] == [
        "passage:doc-hys_feedback-2665651:1",
        "passage:doc-hys_feedback-2665651:2",
    ]
    assert [item.span.text for item in result] == [
        "Caf\u00e9 \U0001f600 first. Delete Article 5. Keep Article 6.",
        "Keep Article 6. Narrow Annex III.",
    ]
    for item in result:
        assert span_matches(item.span, body)
        assert item.span.record_id == document.document_id
        assert item.span.field == "text"
        assert item.span.page is None
        assert item.document_id == document.document_id
        assert item.procedure_id == PROCEDURE
        assert item.actor_id == actor
        assert item.submitted_at == SUBMITTED
        assert item.language == "fr"


def test_attachment_passages_carry_no_language_and_undated_stays_undated() -> None:
    document = make_document("doc:hys_attachment:090166e5e1cd1796", None)
    text = DocumentText(document_id=document.document_id, text="Delete Article 5.")
    (only,) = document_passages(
        document, text, procedure_id=PROCEDURE, actor_id=CITIZENS_ACTOR_ID, submitted_at=None
    )
    assert only.language is None
    assert only.submitted_at is None
    assert only.passage_id == "passage:doc-hys_attachment-090166e5e1cd1796:1"


def test_text_of_another_document_is_refused() -> None:
    document = make_document("doc:hys_feedback:1", "en")
    other = DocumentText(document_id="doc:hys_feedback:2", text="Delete Article 5.")
    with pytest.raises(PassageError, match="does not belong"):
        document_passages(
            document, other, procedure_id=PROCEDURE, actor_id=CITIZENS_ACTOR_ID, submitted_at=None
        )
