"""The passage reader: quoted instructions become changes, everything else stays unclassified."""

import json
from itertools import pairwise
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from influence.schemas.scoring import ScoreRequest, TextChange
from influence.services.passage_change import opposed_sentence, read_changes
from influence.services.scoring import score_pair

FIXTURES = Path(__file__).parent / "fixtures" / "atlas"
CITY = "City Network.\n\nIn Article 9(2), replace 'shall' with 'may': the authority may publish."


def _row(name: str, key: str, value: str) -> dict[str, str]:
    lines = (FIXTURES / name).read_text(encoding="utf-8").splitlines()
    return next(row for row in map(json.loads, lines) if row[key] == value)


def test_replace_instruction_gives_old_and_new_with_exact_offsets() -> None:
    (change,) = read_changes(CITY)
    assert (change.kind, change.old, change.new) == ("replace", "shall", "may")
    assert change.text == "replace 'shall' with 'may'"
    assert CITY[change.start : change.end] == change.text


@pytest.mark.parametrize("verb", ["Replace", "CHANGE", "substitute"])
@pytest.mark.parametrize("link", ["with", "by", "to"])
def test_replace_verbs_and_links_are_case_insensitive(verb: str, link: str) -> None:
    (change,) = read_changes(f"{verb} “six months” {link} “twelve months”.")
    assert (change.old, change.new) == ("six months", "twelve months")


def test_delete_has_empty_new_and_insert_has_empty_old_not_unknown() -> None:
    deleted, inserted = read_changes("Please delete 'and the public' and also add \"in writing\".")
    assert (deleted.kind, deleted.old, deleted.new) == ("delete", "and the public", "")
    assert (inserted.kind, inserted.old, inserted.new) == ("insert", "", "in writing")


def test_several_instructions_come_back_in_order_without_overlap() -> None:
    text = "Replace 'a' with 'b'. Remove 'c'. Insert 'd'."
    changes = read_changes(text)
    assert [change.kind for change in changes] == ["replace", "delete", "insert"]
    assert all(left.end <= right.start for left, right in pairwise(changes))


def test_plain_prose_is_one_statement_with_unknown_original() -> None:
    text = "  Providers should not be required to keep logs.\n"
    (change,) = read_changes(text)
    assert (change.kind, change.old) == ("statement", None)
    assert change.new == "Providers should not be required to keep logs."
    assert text[change.start : change.end] == change.text == change.new


@pytest.mark.parametrize("blank", ["", "  \n\t "])
def test_blank_passage_has_no_change(blank: str) -> None:
    assert read_changes(blank) == ()


@pytest.mark.parametrize(
    "text",
    [
        "Replace 'it's' with 'its'.",  # an apostrophe ends the fragment early
        "Replace '' with 'x'.",  # an empty fragment is not an instruction
        "Replace ' ' with 'x'.",  # neither is a blank one
        "We would replace shall with may.",  # unquoted: not spelled as an instruction
    ],
)
def test_malformed_or_unquoted_instructions_stay_statements(text: str) -> None:
    assert [change.kind for change in read_changes(text)] == ["statement"]


def test_offsets_are_code_points_not_bytes() -> None:
    text = (
        "Résumé: \N{LEFT SINGLE QUOTATION MARK}Ä\N{RIGHT SINGLE QUOTATION MARK} "
        "replace 'naïve' with 'näive'."
    )
    (change,) = read_changes(text)
    assert text[change.start : change.end] == change.text
    assert change.old == "naïve"


@given(st.text(max_size=400))
def test_changes_are_exact_ordered_and_never_overlap(text: str) -> None:
    previous_end = 0
    for change in read_changes(text):
        assert change.text == text[change.start : change.end]
        assert change.start >= previous_end
        previous_end = change.end


def test_bridge_lets_the_scorer_see_the_shall_may_change() -> None:
    """Before: the whole City Network paragraph as one insertion scored 0.03.

    That 0.03 is the pre-bridge baseline measured in the Atlas fixture on 3 October. The
    fixture is invented, so this shows the failure mode is fixed, not real-world accuracy.
    """
    amendment = _row("amendments.jsonl", "amendment_id", "am:2099-0001-COD:IMCO:102")
    passage = _row("document_texts.jsonl", "document_id", "doc:hys_attachment:fixture0003")
    request = TextChange(old=amendment["old_text"], new=amendment["new_text"])
    before = score_pair(
        ScoreRequest(amendment=request, submission=TextChange(old="", new=passage["text"]))
    )
    (change,) = read_changes(passage["text"])
    assert change.old is not None
    after = score_pair(
        ScoreRequest(amendment=request, submission=TextChange(old=change.old, new=change.new))
    )
    assert round(before.score, 2) == 0.03
    assert after.score == 1.0


@pytest.mark.parametrize(
    "passage",
    [
        "Insert 'the provider's obligation to keep logs for ten years' in Article 12.",
        "Delete \N{LEFT SINGLE QUOTATION MARK}the deployer\N{RIGHT SINGLE QUOTATION MARK}s right "
        "to object\N{RIGHT SINGLE QUOTATION MARK} please",
    ],
)
def test_an_apostrophe_is_not_read_as_the_closing_quote(passage: str) -> None:
    """Review round 2 (r2.py): "the provider's" was read as the instruction 'the provider'."""
    (change,) = read_changes(passage)
    assert change.kind == "statement"
    assert change.new == passage


@pytest.mark.parametrize("after", [".", ",", " ", ")", "2", ""])
def test_a_closing_quote_before_punctuation_or_a_digit_still_closes(after: str) -> None:
    (change,) = read_changes(f"insert 'keep logs'{after}")
    assert (change.kind, change.new) == ("insert", "keep logs")


@pytest.mark.parametrize(
    ("passage", "sentence"),
    [
        (
            "Intro. We strongly oppose any proposal to insert 'keep logs'. Thanks.",
            "We strongly oppose any proposal to insert 'keep logs'.",
        ),
        ("Please do not delete 'keep logs'", "Please do not delete 'keep logs'"),
        ("We don't want to delete 'keep logs'; fine.", "We don't want to delete 'keep logs';"),
        (
            "Members shouldn\N{RIGHT SINGLE QUOTATION MARK}t remove 'keep logs'.",
            "Members shouldn\N{RIGHT SINGLE QUOTATION MARK}t remove 'keep logs'.",
        ),
        ("Ok.\n  We reject the move to add 'keep logs'", "We reject the move to add 'keep logs'"),
        (
            "We object to the plan to change 'a' to 'b' here.",
            "We object to the plan to change 'a' to 'b' here.",
        ),
    ],
)
def test_an_opposition_cue_before_the_instruction_gives_the_whole_sentence(
    passage: str, sentence: str
) -> None:
    (change,) = read_changes(passage)
    bounds = opposed_sentence(passage, change)
    assert bounds is not None
    assert passage[bounds[0] : bounds[1]] == sentence


@pytest.mark.parametrize(
    "passage",
    [
        "Insert 'keep logs'.",
        "We oppose the ban. Insert 'keep logs'.",
        "Insert 'keep logs', not the ban.",
        "We oppose the ban; insert 'keep logs'.",
        "Note the annotation. Insert 'keep logs'.",
    ],
)
def test_no_opposition_cue_before_the_instruction_in_its_sentence(passage: str) -> None:
    (change,) = read_changes(passage)
    assert change.kind == "insert"
    assert opposed_sentence(passage, change) is None


def test_a_statement_has_no_opposed_instruction() -> None:
    (change,) = read_changes("We do not support logging.")
    assert opposed_sentence("We do not support logging.", change) is None
