"""Signal contracts use adversarial edits; none establishes real link accuracy."""

from math import isfinite

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from influence.schemas.scoring import TextChange
from influence.services.signals import SignalCorpus, pair_signals


def test_same_edits_keep_short_modal_change_and_detect_opposite_direction() -> None:
    corpus = SignalCorpus(("Operators shall retain logs.", "Operators may retain logs."))
    change = TextChange(old="Operators shall retain logs.", new="Operators may retain logs.")
    same = pair_signals(change, change, corpus)
    assert same["lexical_overlap"] == 1
    assert same["rarity_overlap"] == 1
    assert same["alignment"] == 1
    assert same["short_edit"] == 1
    reverse = pair_signals(change, TextChange(old=change.new, new=change.old), corpus)
    assert reverse["lexical_overlap"] == 0
    assert reverse["modal_conflict"] == 1


@pytest.mark.parametrize(
    ("left", "right", "key", "expected"),
    [
        (
            ("Providers shall retain logs.", "Providers shall retain encrypted logs."),
            ("Providers shall not retain logs.", "Providers shall not retain encrypted logs."),
            "negation_conflict",
            1,
        ),
        (
            (
                "No sale is permitted. Providers shall retain logs.",
                "No sale is permitted. Providers shall retain encrypted logs.",
            ),
            (
                "Sale is permitted. Providers shall retain logs.",
                "Sale is permitted. Providers shall retain encrypted logs.",
            ),
            "negation_conflict",
            0,
        ),
        (
            ("Providers shall retain logs.", "Providers shall retain encrypted logs."),
            ("Providers may retain logs.", "Providers may retain encrypted logs."),
            "modal_conflict",
            1,
        ),
        (
            ("Providers shall retain logs.", "Providers shall retain encrypted logs."),
            ("Providers must retain logs.", "Providers must retain encrypted logs."),
            "modal_conflict",
            0,
        ),
        (
            ("Providers retain logs for 60 days.", "Providers retain logs for 30 days."),
            ("Providers retain logs for 60 days.", "Providers retain logs for 90 days."),
            "quantity_conflict",
            1,
        ),
        (
            ("Providers retain logs for 60 days.", "Providers retain logs for 30 days."),
            ("Providers retain logs for 60 months.", "Providers retain logs for 30 months."),
            "quantity_conflict",
            1,
        ),
        (
            (
                "Providers retain logs for at most 60 days.",
                "Providers retain logs for at most 30 days.",
            ),
            (
                "Providers retain logs for at least 60 days.",
                "Providers retain logs for at least 30 days.",
            ),
            "quantity_conflict",
            1,
        ),
        (
            (
                "Providers retain logs for at most 60 days.",
                "Providers retain logs for at most 30 days.",
            ),
            (
                "Providers retain logs for no more than 60 days.",
                "Providers retain logs for no more than 30 days.",
            ),
            "quantity_conflict",
            0,
        ),
        (
            (
                "Providers retain logs for at least 60 days.",
                "Providers retain logs for at least 30 days.",
            ),
            (
                "Providers retain logs for not less than 60 days.",
                "Providers retain logs for not less than 30 days.",
            ),
            "quantity_conflict",
            0,
        ),
        (
            (
                "Providers retain logs for more than 60 days.",
                "Providers retain logs for more than 30 days.",
            ),
            (
                "Providers retain logs for less than 60 days.",
                "Providers retain logs for less than 30 days.",
            ),
            "quantity_conflict",
            1,
        ),
        (
            ("Providers shall retain logs.", "Providers shall retain encrypted logs."),
            ("Doctors should not diagnose diseases.", "Doctors should not diagnose rare diseases."),
            "context_comparable",
            0,
        ),
        (
            ("Logs retained.", "Encrypted logs retained."),
            ("Logs retained for 30.", "Encrypted logs retained for 30."),
            "quantity_conflict",
            0,
        ),
        (
            ("Providers retain logs.", "Providers retain encrypted logs."),
            ("Providers not only retain logs.", "Providers not only retain encrypted logs."),
            "negation_conflict",
            0,
        ),
    ],
)
def test_changed_sentence_context_flags_lexical_conflicts(
    left: tuple[str, str],
    right: tuple[str, str],
    key: str,
    expected: int,
) -> None:
    a, b = TextChange(old=left[0], new=left[1]), TextChange(old=right[0], new=right[1])
    corpus = SignalCorpus((a.old, a.new, b.old, b.new))
    assert pair_signals(a, b, corpus)[key] == expected


def test_rarity_uses_training_document_frequency_and_never_learns_queries() -> None:
    corpus = SignalCorpus(("the the the", "the zirconium", "the"))
    assert corpus.idf(("zirconium",)) > corpus.idf(("the",))
    assert corpus.idf(("the",)) == 1
    before = corpus.idf(("unseen",))
    full = TextChange(old="", new="the zirconium")
    rare = pair_signals(full, TextChange(old="", new="zirconium"), corpus)
    common = pair_signals(full, TextChange(old="", new="the"), corpus)
    assert rare["rarity_overlap"] > common["rarity_overlap"]
    pair_signals(TextChange(old="", new="unseen"), TextChange(old="", new="unseen"), corpus)
    assert corpus.idf(("unseen",)) == before
    with pytest.raises(ValueError, match="training documents"):
        SignalCorpus(())


def test_no_changes_opposite_operations_and_uninterrupted_phrase_boundaries() -> None:
    corpus = SignalCorpus(("start end rare phrase",))
    unchanged = TextChange(old="unchanged text", new="unchanged text")
    assert set(pair_signals(unchanged, unchanged, corpus).values()) == {0.0}
    insertion = TextChange(old="", new="rare phrase")
    deletion = TextChange(old="rare phrase", new="")
    opposite = pair_signals(insertion, deletion, corpus)
    assert opposite["lexical_overlap"] == opposite["rarity_overlap"] == opposite["alignment"] == 0
    assert opposite["operation_agreement"] == opposite["context_comparable"] == 0
    separated = TextChange(old="start keep end", new="rare keep phrase")
    # Four separate changed unigrams versus two short-run unigrams; no cross-run phrase.
    assert pair_signals(separated, insertion, corpus)["rarity_overlap"] == pytest.approx(2 / 3)


@settings(max_examples=35, derandomize=True, deadline=None)
@given(
    st.lists(
        st.sampled_from(("shall", "may", "not", "logs", "30", "60", ".", "😀")),
        min_size=1,
        max_size=12,
    ),
    st.lists(
        st.sampled_from(("shall", "may", "not", "logs", "30", "60", ".", "😀")),
        min_size=1,
        max_size=12,
    ),
)
def test_signals_remain_finite_bounded_and_training_stable(
    left: list[str], right: list[str]
) -> None:
    corpus = SignalCorpus(("shall may logs 30 60",))
    a, b = TextChange(old="", new=" ".join(left)), TextChange(old="", new=" ".join(right))
    forward, reverse = pair_signals(a, b, corpus), pair_signals(b, a, corpus)
    assert all(isfinite(value) and 0 <= value <= 1 for value in forward.values())
    for key in forward.keys() - {"alignment"}:
        assert forward[key] == pytest.approx(reverse[key]), key


@pytest.mark.parametrize(
    ("left", "right"),
    [
        (
            (
                "Providers retain logs for at most 60 days.",
                "Providers retain logs for at most 30 days.",
            ),
            (
                "Providers retain logs for no more than 60 days.",
                "Providers retain logs for no more than 30 days.",
            ),
        ),
        (
            (
                "Providers retain logs for at least 60 days.",
                "Providers retain logs for at least 30 days.",
            ),
            (
                "Providers retain logs for not less than 60 days.",
                "Providers retain logs for not less than 30 days.",
            ),
        ),
        (
            (
                "Providers shall not sell logs and shall archive records.",
                "Providers shall not sell logs and shall archive encrypted records.",
            ),
            (
                "Providers shall sell logs and shall archive records.",
                "Providers shall sell logs and shall archive encrypted records.",
            ),
        ),
    ],
)
def test_bound_phrases_and_separate_modal_clauses_are_not_negation_conflicts(
    left: tuple[str, str],
    right: tuple[str, str],
) -> None:
    a, b = TextChange(old=left[0], new=left[1]), TextChange(old=right[0], new=right[1])
    assert pair_signals(a, b, SignalCorpus((a.old, b.old)))["negation_conflict"] == 0


def test_corpus_fingerprint_tracks_training_membership_not_document_order() -> None:
    first = SignalCorpus(("a", "b"))
    assert first.fingerprint == SignalCorpus(("b", "a")).fingerprint
    assert first.fingerprint != SignalCorpus(("a", "b", "b")).fingerprint
    assert first.fingerprint != SignalCorpus(("a", "c")).fingerprint


def test_local_alignment_rewards_contiguous_same_operation_runs() -> None:
    corpus = SignalCorpus(("alpha beta gamma delta epsilon",))
    a = TextChange(old="", new="alpha beta gamma delta")
    b = TextChange(old="", new="alpha beta gamma epsilon")
    assert pair_signals(a, b, corpus)["alignment"] == 0.75
    assert (
        pair_signals(a, TextChange(old="alpha beta gamma delta", new=""), corpus)["alignment"] == 0
    )
    assert pair_signals(a, TextChange(old="same", new="same"), corpus)["alignment"] == 0
    assert corpus.idf(("alpha", "beta", "gamma")) == 1
    assert corpus.idf(("alpha", "beta", "gamma", "delta")) == 1
    assert corpus.idf(("alpha", "beta", "gamma", "delta", "epsilon")) == 1
