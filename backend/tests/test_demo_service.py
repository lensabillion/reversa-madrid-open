"""Dataset integrity and evidence semantics must hold independently of the HTTP layer."""

from pathlib import Path
from types import MappingProxyType

import pytest
from demo_fixture import write_dataset
from pydantic import ValidationError

from influence.repositories.lobbyplag import (
    DatasetInvalidError,
    DatasetUnavailableError,
    DemoRepository,
    EntityNotFoundError,
    RawDocument,
)
from influence.services.demo import SOURCE_LIMIT, DemoService


@pytest.fixture
def service(tmp_path: Path) -> DemoService:
    write_dataset(tmp_path)
    return DemoService(DemoRepository.load(tmp_path))


def test_overview_and_immutable_contract(service: DemoService) -> None:
    overview = service.overview()
    assert (overview.amendments, overview.proposals, overview.documents) == (2, 2, 3)
    assert (overview.organizations, overview.candidate_links, overview.verified_links) == (3, 2, 1)
    assert overview.source_url == "https://github.com/lobbyplag/lobbyplag-data"
    assert "incomplete" in overview.coverage_note
    with pytest.raises(ValidationError, match="frozen"):
        overview.amendments = 4
    with pytest.raises(ValidationError, match="Extra inputs"):
        type(overview).model_validate({**overview.model_dump(), "adoption": 1})
    with pytest.raises(ValidationError, match="frozen"):
        service.repository.amendments["a1"].committee = "new"


@pytest.mark.parametrize(
    ("query", "verified_only", "ids"),
    [
        ("", False, ["a1", "a2"]),
        ("ITRE 616", False, ["a1"]),
        ("ada EXAMPLE", False, ["a1"]),
        ("42", False, ["a2"]),
        ("", True, ["a1"]),
        ("not present", False, []),
    ],
)
def test_browse_search(
    service: DemoService, query: str, verified_only: bool, ids: list[str]
) -> None:
    page = service.list_amendments(query, 0, 100, verified_only)
    assert [item.id for item in page.items] == ids
    assert page.total == len(ids)


def test_browse_pagination(service: DemoService) -> None:
    page = service.list_amendments("", 1, 1, False)
    assert (page.total, page.offset, page.limit) == (2, 1, 1)
    assert [item.id for item in page.items] == ["a2"]
    assert service.list_amendments("", 10, 1, False).items == ()


@pytest.mark.parametrize(("offset", "limit"), [(-1, 20), (0, 0), (0, 101)])
def test_browse_rejects_invalid_bounds(service: DemoService, offset: int, limit: int) -> None:
    with pytest.raises(ValueError, match="offset"):
        service.list_amendments("", offset, limit, False)


def test_detail_preserves_provenance_and_unknown_verification(service: DemoService) -> None:
    detail = service.amendment("a1")
    assert detail.text.language == "en"
    assert detail.text.old == "The controller shall report."
    assert detail.text.new == "The controller may report."
    assert detail.total_sources == 2
    first, second = detail.sources
    assert (first.proposal_id, first.organization_id, first.document_id) == ("p1", "o1", "d1")
    assert (first.organization, first.document, first.page) == (
        "Example association",
        "public-paper.pdf",
        "17",
    )
    assert first.historically_verified is True
    assert second.historically_verified is False
    assert second.page == "2-3"
    assert first.score != second.score
    assert detail.amendment.verified_links == 1
    assert "not rejected" in detail.coverage_note
    other = service.amendment("a2")
    assert other.text.language == "es"
    assert other.sources == ()
    assert other.total_sources == 0


def test_graph_only_shows_verified_organizations_and_deduplicates_authors(
    service: DemoService,
) -> None:
    graph = service.graph("a1")
    assert {(node.id, node.kind) for node in graph.nodes} == {
        ("amendment:a1", "amendment"),
        ("organization:o1", "organization"),
        ("author:Ada Example", "author"),
    }
    assert {(edge.source, edge.target, edge.kind) for edge in graph.edges} == {
        ("organization:o1", "amendment:a1", "historically_verified"),
        ("author:Ada Example", "amendment:a1", "authored"),
    }
    empty_graph = service.graph("a2")
    assert len(empty_graph.nodes) == 1
    assert empty_graph.edges == ()


def test_organizations_report_counts_without_win_rates(service: DemoService) -> None:
    result = service.organizations()
    assert [
        (item.id, item.proposals, item.verified_links, item.amendments_echoing)
        for item in result.items
    ] == [("o1", 1, 1, 1), ("o3", 0, 0, 0), ("o2", 1, 0, 0)]
    assert "win rates" in result.coverage_note


@pytest.mark.parametrize("method", ["amendment", "graph"])
def test_missing_entity(service: DemoService, method: str) -> None:
    operation = service.amendment if method == "amendment" else service.graph
    with pytest.raises(EntityNotFoundError, match="Unknown amendment missing"):
        operation("missing")


def test_empty_snapshot(tmp_path: Path) -> None:
    write_dataset(
        tmp_path,
        {name: [] for name in ("amendments", "proposals", "plags", "documents", "lobbyists")},
    )
    service = DemoService(DemoRepository.load(tmp_path))
    assert service.overview().amendments == 0
    assert service.overview().verified_links == 0
    assert service.list_amendments("", 0, 20, True).total == 0
    assert service.organizations().items == ()


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


def test_manually_constructed_repository_cannot_invent_attribution(service: DemoService) -> None:
    repository = service.repository
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


def test_source_details_are_bounded_but_counts_and_graph_are_complete(tmp_path: Path) -> None:
    records = write_dataset(tmp_path)
    for index in range(SOURCE_LIMIT + 2):
        records["proposals"].append({**records["proposals"][0], "uid": f"extra-{index}"})
        records["plags"].append(
            {
                "uid": f"extra-{index}",
                "proposal": f"extra-{index}",
                "amendment": "a1",
                "verified": True,
            }
        )
    write_dataset(tmp_path, records)
    service = DemoService(DemoRepository.load(tmp_path))
    detail = service.amendment("a1")
    assert len(detail.sources) == SOURCE_LIMIT
    assert detail.total_sources == SOURCE_LIMIT + 4
    assert all(source.historically_verified for source in detail.sources)
    graph = service.graph("a1")
    assert sum(edge.kind == "historically_verified" for edge in graph.edges) == 1
    organization = service.organizations().items[0]
    assert organization.verified_links == SOURCE_LIMIT + 3
    assert organization.amendments_echoing == 1


@pytest.mark.parametrize(
    "case", ["amendment-language", "submission-language", "empty", "oversized"]
)
def test_unscorable_text_preserves_historical_evidence(tmp_path: Path, case: str) -> None:
    records = write_dataset(tmp_path)
    if case == "amendment-language":
        records["amendments"][0]["text"] = [{"lang": "es", "old": "Texto", "new": "Otro texto"}]
    elif case == "submission-language":
        records["documents"][0]["lang"] = "es"
    elif case == "empty":
        records["proposals"][0]["text"] = {"old": "", "new": ""}
    else:
        records["proposals"][0]["text"] = {"old": "", "new": "word " * 801}
    write_dataset(tmp_path, records)
    detail = DemoService(DemoRepository.load(tmp_path)).amendment("a1")
    source = detail.sources[0]
    assert source.historically_verified is True
    assert source.score is None
    assert source.score_unavailable_reason is not None
    if "language" in case:
        assert "English" in source.score_unavailable_reason
    else:
        assert "input limits" in source.score_unavailable_reason
    if case == "oversized":
        assert source.text.new == "word " * 801


def test_equivalent_candidate_rows_coalesce_with_explicit_count(tmp_path: Path) -> None:
    records = write_dataset(tmp_path)
    records["plags"].append({**records["plags"][0], "relations": ["different-location"]})
    write_dataset(tmp_path, records)
    service = DemoService(DemoRepository.load(tmp_path))
    assert service.overview().duplicate_candidate_rows == 1
    assert service.overview().candidate_links == 2
    assert service.overview().verified_links == 1
    assert len(service.amendment("a1").sources) == 2


def test_conflicting_candidate_identity_is_rejected(tmp_path: Path) -> None:
    records = write_dataset(tmp_path)
    records["plags"].append({**records["plags"][0], "verified": False})
    write_dataset(tmp_path, records)
    with pytest.raises(DatasetInvalidError, match="Conflicting duplicate candidate"):
        DemoRepository.load(tmp_path)


@pytest.mark.parametrize("value", ["true", 1])
def test_verification_requires_a_json_boolean(tmp_path: Path, value: object) -> None:
    records = write_dataset(tmp_path)
    records["plags"][0]["verified"] = value
    write_dataset(tmp_path, records)
    with pytest.raises(DatasetInvalidError, match="Invalid plags"):
        DemoRepository.load(tmp_path)
