"""Law queries: identifiers recognised by shape, titles ranked, close races left open."""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from influence.services.law_query import (
    LawQuery,
    com_reference_from_celex,
    parse_query,
    resolve_title,
    title_tokens,
)

PROPERTY = settings(derandomize=True, database=None, deadline=None)

TITLES = (
    ("2021/0106(COD)", "Artificial Intelligence Act"),
    ("2020/0361(COD)", "Digital Services Act"),
    ("2020/0374(COD)", "Digital Markets Act"),
    ("2022/0140(COD)", "European Health Data Space"),
    ("2025/0001(COD)", "Artificial Intelligence Act: amending certain deadlines"),
)
ALIASES = {"ai act": "2021/0106(COD)", "ghost act": "1999/0001(COD)"}


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2021/0106(COD)", LawQuery("procedure", "2021/0106(COD)")),
        (" 2021/106 (cod) ", LawQuery("procedure", "2021/0106(COD)")),
        ("2021 / 0106 COD", LawQuery("procedure", "2021/0106(COD)")),
        ("2016/0062A(NLE)", LawQuery("procedure", "2016/0062A(NLE)")),
        ("32024R1689", LawQuery("celex", "32024R1689")),
        ("celex:52021pc0206", LawQuery("celex", "52021PC0206")),
        ("COM(2021) 206 final", LawQuery("com", "COM(2021)206")),
        ("com/2021/0206", LawQuery("com", "COM(2021)206")),
        ("COM(2021)0206", LawQuery("com", "COM(2021)206")),
        ("  AI   Act ", LawQuery("title", "AI Act")),
        ("2021/0106", LawQuery("title", "2021/0106")),
    ],
)
def test_parse_query(text: str, expected: LawQuery) -> None:
    assert parse_query(text) == expected


def test_empty_query_is_rejected() -> None:
    with pytest.raises(ValueError, match="empty"):
        parse_query("   ")


@PROPERTY
@given(st.text(min_size=1))
def test_parse_query_never_returns_an_empty_value(text: str) -> None:
    try:
        query = parse_query(text)
    except ValueError:
        assert not text.split()
        return
    assert query.value


def test_com_reference_from_celex() -> None:
    assert com_reference_from_celex("52021PC0206") == "COM(2021)206"
    assert com_reference_from_celex("52020PC0825") == "COM(2020)825"
    assert com_reference_from_celex("32024R1689") is None


def test_title_tokens_drop_filler_unless_nothing_else_remains() -> None:
    assert title_tokens("Regulation on the Digital Services Act") == {"digital", "services"}
    assert title_tokens("The Act") == {"the", "act"}


def test_exact_alias_wins_outright() -> None:
    result = resolve_title("  AI  act", TITLES, ALIASES)
    assert result.chosen is not None
    assert result.chosen.procedure_id == "2021/0106(COD)"
    assert result.chosen.alias == "ai act"
    assert not result.ambiguous


def test_alias_to_a_procedure_missing_from_the_catalog_falls_back_to_titles() -> None:
    result = resolve_title("ghost act", TITLES, ALIASES)
    assert result.chosen is None
    assert result.candidates == ()
    assert not result.ambiguous


def test_shorter_title_beats_the_act_amending_it() -> None:
    result = resolve_title("artificial intelligence act", TITLES)
    assert result.chosen is not None
    assert result.chosen.procedure_id == "2021/0106(COD)"
    assert [item.procedure_id for item in result.candidates] == [
        "2021/0106(COD)",
        "2025/0001(COD)",
    ]


def test_close_titles_return_choices_instead_of_a_guess() -> None:
    result = resolve_title("digital act", TITLES)
    assert result.chosen is None
    assert result.ambiguous
    assert {item.procedure_id for item in result.candidates} == {
        "2020/0361(COD)",
        "2020/0374(COD)",
    }


def test_single_match_is_chosen_without_aliases() -> None:
    result = resolve_title("health data space", TITLES)
    assert result.chosen is not None
    assert result.chosen.procedure_id == "2022/0140(COD)"
    assert result.chosen.alias is None


def test_no_match_returns_nothing() -> None:
    result = resolve_title("fisheries quotas", TITLES)
    assert result.chosen is None
    assert result.candidates == ()
