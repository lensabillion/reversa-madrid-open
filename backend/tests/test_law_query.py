"""Law queries: identifiers recognised by shape, common names looked up, titles ranked,
close races left open."""

import re

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from influence.services.law_query import (
    LAW_ALIASES,
    LawQuery,
    name_key,
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
PROCEDURE_FORMAT = re.compile(r"\d{4}/\d{4}\([A-Z]{3}\)")


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


def test_title_tokens_drop_filler_unless_nothing_else_remains() -> None:
    assert title_tokens("Regulation on the Digital Services Act") == {"digital", "services"}
    assert title_tokens("The Act") == {"the", "act"}


@pytest.mark.parametrize(
    "name",
    [
        "  AI  act",
        "the ai act",
        "AI-Act",
        "  The   A.I. act. ",
        "THE AI\N{EN DASH}ACT",
        "ai_act, the",
        "Reglement sur l\N{RIGHT SINGLE QUOTATION MARK}IA",
        "LEY DE IA",
        "KI Verordnung",
    ],
)
def test_an_alias_wins_whatever_its_case_accents_spacing_punctuation_and_articles(
    name: str,
) -> None:
    result = resolve_title(name, TITLES, LAW_ALIASES)
    assert result.chosen is not None
    assert result.chosen.procedure_id == "2021/0106(COD)"
    assert result.chosen.alias is not None
    assert name_key(result.chosen.alias) == name_key(name)
    assert not result.ambiguous


@pytest.mark.parametrize("name", ["AI", "AI Acts", "Act AI", "AI Act 2", "theAI Act"])
def test_an_alias_is_matched_whole_not_by_its_words(name: str) -> None:
    assert resolve_title(name, TITLES, LAW_ALIASES).chosen is None


def test_an_alias_outranks_a_title_that_only_shares_a_word() -> None:
    """The title search sends "AI Act" to any title holding "AI" (seen on the real catalog)."""
    titles = (*TITLES, ("2022/0303(COD)", "AI Liability Directive"))

    by_title = resolve_title("AI Act", titles)
    by_alias = resolve_title("AI Act", titles, LAW_ALIASES)

    assert by_title.chosen is not None
    assert by_title.chosen.procedure_id == "2022/0303(COD)"
    assert by_alias.chosen is not None
    assert by_alias.chosen.procedure_id == "2021/0106(COD)"


def test_names_that_disagree_return_the_choices_instead_of_a_guess() -> None:
    two_aliases = resolve_title(
        "the ai act", TITLES, {"AI Act": "2021/0106(COD)", "AI-Act": "2022/0047(COD)"}
    )
    alias_and_title = resolve_title(
        "the Digital Markets Act", TITLES, {"digital markets act": "2020/0361(COD)"}
    )

    assert two_aliases.ambiguous
    assert [(c.procedure_id, c.title, c.alias) for c in two_aliases.candidates] == [
        ("2021/0106(COD)", "Artificial Intelligence Act", "AI Act"),
        ("2022/0047(COD)", "2022/0047(COD)", "AI-Act"),
    ]
    assert alias_and_title.ambiguous
    assert [(c.procedure_id, c.alias) for c in alias_and_title.candidates] == [
        ("2020/0361(COD)", "digital markets act"),
        ("2020/0374(COD)", None),
    ]


def test_an_alias_to_a_procedure_missing_from_the_catalog_names_it_instead_of_a_title() -> None:
    result = resolve_title("ghost act", TITLES, ALIASES)
    assert result.missing == "1999/0001(COD)"
    assert result.chosen is None
    assert result.candidates == ()


@PROPERTY
@given(st.text())
def test_name_key_is_stable_and_ignores_surrounding_articles_and_punctuation(text: str) -> None:
    key = name_key(text)
    assert name_key(key) == key
    assert name_key(f"  THE {text} !? ") == key
    assert key == key.strip()
    assert "  " not in key


def test_every_alias_is_a_well_formed_procedure_and_a_name_the_lookup_reaches() -> None:
    """A typo here would never match the catalog; a name shaped like a CELEX never arrives."""
    titles = [(procedure, f"Title of {procedure}") for procedure in set(LAW_ALIASES.values())]
    assert len({name_key(name) for name in LAW_ALIASES}) == len(LAW_ALIASES)
    for name, procedure in LAW_ALIASES.items():
        assert PROCEDURE_FORMAT.fullmatch(procedure), procedure
        assert parse_query(name).kind == "title"
        found = resolve_title(name, titles, LAW_ALIASES)
        assert found.chosen is not None
        assert (found.chosen.procedure_id, found.chosen.alias) == (procedure, name)


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
