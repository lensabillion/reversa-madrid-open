"""The label rule, its provenance counts, and the exclusions it reports."""

from pathlib import Path

import pytest
from demo_fixture import write_dataset
from practice_fixture import practice_records

from influence.practice.labels import build_practice_set, label_source
from influence.repositories.lobbyplag import (
    DatasetInvalidError,
    DemoRepository,
    RawCandidate,
    RawProcessing,
)


@pytest.mark.parametrize(
    ("verified", "checked", "yes_votes", "expected"),
    [
        (True, 0, 0, "volunteer_verified"),
        (True, 2, 0, "volunteer_verified"),
        (True, 1, 1, "volunteer_verified"),
        (False, 1, 0, "crowd_rejected"),
        (False, 2, 0, "crowd_rejected"),
        (False, 0, 0, None),
        (False, 1, 1, None),
        (False, 2, 1, None),
    ],
)
def test_label_rule_truth_table(
    verified: bool, checked: int, yes_votes: int, expected: str | None
) -> None:
    candidate = RawCandidate(
        uid="c",
        amendment="a",
        proposal="p",
        verified=verified,
        match=0.5,
        processing=RawProcessing(checked=checked, verified=yes_votes),
    )
    assert label_source(candidate) == expected


def test_practice_set_labels_with_provenance(tmp_path: Path) -> None:
    write_dataset(tmp_path, practice_records(organizations=2, per_organization=4))
    practice = build_practice_set(DemoRepository.load(tmp_path))
    assert practice.outcomes == {
        "volunteer_verified": 4,
        "crowd_rejected": 4,
        "unlabelled_never_checked": 1,
        "unlabelled_crowd_support": 1,
    }
    assert [item.pair.candidate_id for item in practice.pairs] == sorted(
        f"c{org}-{item}" for org in range(2) for item in range(4)
    )
    first = practice.pairs[0]
    assert (first.source, first.crowd_checks, first.crowd_yes_votes) == ("volunteer_verified", 0, 0)
    assert first.influenced
    assert (first.pair.organization_id, first.pair.proposal_id) == ("org0", "p0-0")
    assert first.pair.amendment.new == "Article 0-0 requires explicit consent within 0 days."
    assert first.document_language == "en"
    assert not practice.pairs[1].influenced
    assert practice.pairs[1].crowd_checks == 1
    assert practice.excluded == {"no_english_amendment_text": 0, "conflicting_identical_input": 0}


def test_identical_inputs_are_reported_and_conflicts_excluded(tmp_path: Path) -> None:
    records = practice_records(organizations=1, per_organization=6)
    proposals = {row["uid"]: row for row in records["proposals"]}
    amendments = {row["uid"]: row for row in records["amendments"]}
    # Copy a verified pair's texts onto two other candidates: one also verified (agreeing),
    # one crowd-rejected (conflicting). Case and spacing differences do not separate them.
    amendments["a0-2"]["text"] = amendments["a0-0"]["text"]
    proposals["p0-2"]["text"] = proposals["p0-0"]["text"]
    amendments["a0-1"]["text"] = [
        {
            "lang": "en",
            "old": "ARTICLE 0-0 requires  consent.",
            "new": "Article 0-0 requires explicit consent within 0 days.",
        }
    ]
    proposals["p0-1"]["text"] = proposals["p0-0"]["text"]
    amendments["a0-5"]["text"] = [{"lang": "fr", "old": "Texte", "new": "Nouveau texte"}]
    write_dataset(tmp_path, records)
    practice = build_practice_set(DemoRepository.load(tmp_path))
    kept = {item.pair.candidate_id for item in practice.pairs}
    assert kept == {"c0-3", "c0-4"}
    assert practice.excluded == {"no_english_amendment_text": 1, "conflicting_identical_input": 3}
    assert (practice.identical_inputs.groups, practice.identical_inputs.pairs) == (1, 3)
    assert practice.identical_inputs.conflicting_groups == 1


def test_repeated_rows_merge_crowd_tallies_by_maximum(tmp_path: Path) -> None:
    records = write_dataset(tmp_path)
    rejected = records["plags"][1]
    records["plags"] += [
        {**rejected, "relations": ["elsewhere"], "processing": {"checked": 1, "verified": 1}},
        {**rejected, "processing": {"checked": 0, "verified": 0}},
        {**records["plags"][0]},
    ]
    write_dataset(tmp_path, records)
    repository = DemoRepository.load(tmp_path)
    assert repository.candidates["a-unverified"].processing == RawProcessing(checked=2, verified=1)
    assert (repository.duplicate_candidate_rows, repository.merged_crowd_tallies) == (3, 1)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("match", 1.5),
        ("match", "0.5"),
        ("processing", {"checked": -1, "verified": 0}),
        ("processing", {"checked": 1}),
    ],
)
def test_candidate_scores_and_tallies_are_validated(
    tmp_path: Path, field: str, value: object
) -> None:
    records = write_dataset(tmp_path)
    records["plags"][0][field] = value
    write_dataset(tmp_path, records)
    with pytest.raises(DatasetInvalidError, match="Invalid plags"):
        DemoRepository.load(tmp_path)


def test_repeated_rows_with_a_different_match_conflict(tmp_path: Path) -> None:
    records = write_dataset(tmp_path)
    records["plags"].append({**records["plags"][0], "match": 0.7})
    write_dataset(tmp_path, records)
    with pytest.raises(DatasetInvalidError, match="Conflicting duplicate candidate z-verified"):
        DemoRepository.load(tmp_path)
