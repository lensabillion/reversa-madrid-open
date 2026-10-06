"""The LobbyPlag reader rejects a broken snapshot before the practice loop can label it."""

from pathlib import Path
from types import MappingProxyType

import pytest
from demo_fixture import write_dataset

from influence.repositories.lobbyplag import (
    DatasetInvalidError,
    DatasetUnavailableError,
    DemoRepository,
    RawDocument,
)


@pytest.mark.parametrize("filename", ["amendments", "proposals", "plags", "documents", "lobbyists"])
def test_missing_file(tmp_path: Path, filename: str) -> None:
    write_dataset(tmp_path)
    (tmp_path / f"{filename}.json").unlink()
    with pytest.raises(DatasetUnavailableError, match=filename):
        DemoRepository.load(tmp_path)


@pytest.mark.parametrize("content", ["not JSON", "{}", '[{"uid":"a"}]', "[null]"])
def test_invalid_json_or_shape(tmp_path: Path, content: str) -> None:
    write_dataset(tmp_path)
    (tmp_path / "amendments.json").write_text(content, encoding="utf-8")
    with pytest.raises(DatasetInvalidError, match=r"amendments\.json"):
        DemoRepository.load(tmp_path)


@pytest.mark.parametrize("name", ["amendments", "proposals", "documents", "lobbyists"])
def test_duplicate_identifiers(tmp_path: Path, name: str) -> None:
    records = write_dataset(tmp_path)
    records[name].append(records[name][0])
    write_dataset(tmp_path, records)
    with pytest.raises(DatasetInvalidError, match="Duplicate identifiers"):
        DemoRepository.load(tmp_path)


@pytest.mark.parametrize(
    ("name", "field", "value", "message"),
    [
        ("documents", "lobbyist", "missing", "Unknown organization"),
        ("proposals", "doc_uid", "missing", "Unknown document"),
        ("proposals", "doc_uid", "d3", "Unattributed proposal"),
        ("plags", "amendment", "missing", "Dangling candidate"),
        ("plags", "proposal", "missing", "Dangling candidate"),
        ("amendments", "text", [], "Invalid amendments"),
    ],
)
def test_invalid_relationships(
    tmp_path: Path, name: str, field: str, value: object, message: str
) -> None:
    records = write_dataset(tmp_path)
    records[name][0][field] = value
    write_dataset(tmp_path, records)
    with pytest.raises(DatasetInvalidError, match=message):
        DemoRepository.load(tmp_path)


def test_duplicate_candidate_pair(tmp_path: Path) -> None:
    records = write_dataset(tmp_path)
    records["plags"].append({**records["plags"][0], "uid": "another-id"})
    write_dataset(tmp_path, records)
    with pytest.raises(DatasetInvalidError, match="Duplicate candidate pair"):
        DemoRepository.load(tmp_path)


def test_manually_constructed_repository_cannot_invent_attribution(tmp_path: Path) -> None:
    write_dataset(tmp_path)
    repository = DemoRepository.load(tmp_path)
    invalid = DemoRepository(
        repository.amendments,
        repository.proposals,
        repository.candidates,
        MappingProxyType(
            {"d1": RawDocument(uid="d1", filename="orphan.pdf", lobbyist=None, lang="en")}
        ),
        repository.organizations,
    )
    with pytest.raises(DatasetInvalidError, match="Unattributed proposal"):
        invalid.organization_for(repository.proposals["p1"])
