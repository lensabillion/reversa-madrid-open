"""`influence setup`: collect's global inputs, fetched once, published whole, with provenance.

Every answer comes from one scripted source: the bulk files stream from memory, and the
Have Your Say crawl answers in the API's own shapes (`test_hys`), so no test reaches the
network.
"""

import hashlib
import re
from collections.abc import Collection, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import BinaryIO

import pytest
from test_hys import as_json, crawl_responses, initiative

from influence import cli
from influence.extraction.cache import HttpCache
from influence.extraction.fetching import (
    CachedFetcher,
    FetchError,
    RateLimiter,
    RawResponse,
    ResponseHead,
)
from influence.repositories import hys, parltrack
from influence.schemas.atlas import SourceDocument
from influence.services import setup
from influence.services.collect import CollectInputs
from influence.services.setup import (
    GROUPS,
    SetupError,
    SetupFile,
    SetupGroup,
    setup_data,
    source_record_path,
)

NOW = datetime(2026, 10, 3, 15, 0, tzinfo=UTC)
DUMPS = ("ep_dossiers", "ep_amendments", "ep_plenary_amendments", "ep_meps")
REGISTER = setup.REGISTER_EXPORT_URL


def dump_url(name: str) -> str:
    return f"{parltrack.DUMP_BASE_URL}{name}.json.zst"


def bulk_files(version: str = "v1") -> dict[str, RawResponse]:
    """The four dumps and the export; `version` changes every body, as a new day would."""
    files = {
        dump_url(name): RawResponse(200, "application/zstd", f"{name} {version}".encode())
        for name in DUMPS
    }
    files[REGISTER] = RawResponse(200, "application/xml", f"<register {version}/>".encode())
    return files


def initiatives() -> dict[str, RawResponse]:
    """A crawl that succeeds: `crawl_responses` plus the initiative it leaves unanswered."""
    return {**crawl_responses(), hys.initiative_url(404): as_json(initiative(404, []))}


@dataclass
class ScriptedSource:
    """Both halves of the fetching layer from one script: whole answers and streams.

    `cut` names the URLs whose connection drops after that many bytes: the real streamer
    then raises `FetchError` with part of the body already written.
    """

    responses: dict[str, RawResponse]
    cut: dict[str, int] = field(default_factory=dict[str, int])
    calls: list[str] = field(default_factory=list[str])

    def _answer(self, url: str) -> RawResponse:
        self.calls.append(url)
        if url not in self.responses:
            raise FetchError(url, "No response: unscripted")
        return self.responses[url]

    def __call__(self, url: str, headers: Mapping[str, str] | None = None) -> RawResponse:
        return self._answer(url)

    def stream(self, url: str, sink: BinaryIO) -> ResponseHead:
        answer = self._answer(url)
        if url in self.cut:
            sink.write(answer.body[: self.cut[url]])
            raise FetchError(url, f"Body cut off after {self.cut[url]} bytes")
        sink.write(answer.body)
        return ResponseHead(answer.status, answer.content_type)


def fetcher_for(root: Path, source: ScriptedSource) -> CachedFetcher:
    return CachedFetcher(
        cache=HttpCache(root / "cache"),
        fetcher=source,
        streamer=source.stream,
        limiter=RateLimiter(interval=0.0),
        clock=lambda: NOW,
    )


def run(
    root: Path,
    source: ScriptedSource,
    groups: Collection[SetupGroup] = GROUPS,
    *,
    refresh: bool = False,
) -> list[SetupFile]:
    fetcher = fetcher_for(root, source)
    return list(setup_data(root, groups=groups, fetcher=fetcher, refresh=refresh))


def record(path: Path) -> SourceDocument:
    return SourceDocument.model_validate_json(source_record_path(path).read_bytes())


def names(directory: Path) -> list[str]:
    return sorted(path.name for path in directory.iterdir())


# --- The service ----------------------------------------------------------------------------


def test_every_file_lands_where_collect_reads_it_with_its_source_record(tmp_path: Path) -> None:
    source = ScriptedSource({**bulk_files(), **initiatives()})

    files = run(tmp_path, source)

    inputs = CollectInputs.under(tmp_path)
    assert inputs.missing() == ()
    assert [item.path for item in files] == [
        inputs.dossiers,
        inputs.committee_amendments,
        inputs.plenary_amendments,
        inputs.meps,
        inputs.register,
        inputs.hys_index,
    ]
    assert [item.action for item in files] == [*["fetched"] * 5, "built"]
    for item in files:
        body = item.path.read_bytes()
        assert (item.byte_count, item.sha256) == (len(body), hashlib.sha256(body).hexdigest())
    assert inputs.meps.read_bytes() == b"ep_meps v1"
    assert inputs.register.read_bytes() == b"<register v1/>"
    assert [entry.initiative_id for entry in hys.read_index(inputs.hys_index)] == [
        12527,
        404,
        12417,
    ]
    # A dump's record is the one collect writes for it, retrieved when the request left.
    assert record(inputs.meps) == parltrack.dump_source_document(inputs.meps, NOW)
    export = record(inputs.register)
    assert (export.url, export.retrieved_at, export.media_type) == (
        REGISTER,
        NOW,
        "application/xml",
    )
    assert export.sha256 == hashlib.sha256(b"<register v1/>").hexdigest()
    assert names(inputs.register.parent) == ["register.xml", "register.xml.source.json"]
    # One request per bulk file: nothing is fetched twice and nothing else is asked.
    assert [call for call in source.calls if "better-regulation" not in call] == [
        *map(dump_url, DUMPS),
        REGISTER,
    ]


def test_a_second_run_keeps_every_present_file_and_sends_no_request(tmp_path: Path) -> None:
    run(tmp_path, ScriptedSource({**bulk_files(), **initiatives()}))
    again = ScriptedSource({**bulk_files("v2"), **initiatives()})

    files = run(tmp_path, again)

    assert [item.action for item in files] == ["kept"] * 6
    assert again.calls == []
    assert CollectInputs.under(tmp_path).register.read_bytes() == b"<register v1/>"
    assert files[4].sha256 == hashlib.sha256(b"<register v1/>").hexdigest()


def test_refresh_fetches_every_chosen_file_again_and_replaces_it(tmp_path: Path) -> None:
    run(tmp_path, ScriptedSource({**bulk_files(), **initiatives()}))
    fresh = initiatives()
    fresh[hys.initiative_url(404)] = as_json(initiative(404, [{"id": 7, "reference": "x"}]))
    again = ScriptedSource({**bulk_files("v2"), **fresh})

    files = run(tmp_path, again, refresh=True)

    inputs = CollectInputs.under(tmp_path)
    assert [item.action for item in files] == [*["fetched"] * 5, "built"]
    assert inputs.register.read_bytes() == b"<register v2/>"
    assert record(inputs.register).sha256 == hashlib.sha256(b"<register v2/>").hexdigest()
    # The crawl asked every page again instead of replaying the cache.
    assert again.calls.count(hys.initiative_url(12527)) == 1
    (rejected,) = (e for e in hys.read_index(inputs.hys_index) if e.initiative_id == 404)
    assert [p.publication_id for p in rejected.publications] == [7]


def test_only_the_chosen_groups_are_fetched_in_run_order(tmp_path: Path) -> None:
    source = ScriptedSource({**bulk_files(), **initiatives()})

    files = run(tmp_path, source, {"hys", "register"})

    inputs = CollectInputs.under(tmp_path)
    assert [item.path for item in files] == [inputs.register, inputs.hys_index]
    assert inputs.missing() == (
        inputs.dossiers,
        inputs.committee_amendments,
        inputs.plenary_amendments,
        inputs.meps,
    )


def test_a_cut_off_download_stops_the_run_and_keeps_the_previous_file(tmp_path: Path) -> None:
    run(tmp_path, ScriptedSource(bulk_files()), {"parltrack", "register"})
    inputs = CollectInputs.under(tmp_path)
    previous = source_record_path(inputs.register).read_bytes()
    source = ScriptedSource({**bulk_files("v2"), **initiatives()}, cut={REGISTER: 3})
    files = setup_data(tmp_path, groups=GROUPS, fetcher=fetcher_for(tmp_path, source), refresh=True)

    finished = [next(files) for _ in DUMPS]
    with pytest.raises(SetupError, match=r"register\.xml was not .* unchanged: .*after 3 bytes"):
        next(files)

    assert [item.action for item in finished] == ["fetched"] * 4
    assert inputs.meps.read_bytes() == b"ep_meps v2"
    assert inputs.register.read_bytes() == b"<register v1/>"
    assert source_record_path(inputs.register).read_bytes() == previous
    assert names(inputs.register.parent) == ["register.xml", "register.xml.source.json"]
    # The run stopped there: the index crawl never started.
    assert not inputs.hys_index.exists()
    assert source.calls[-1] == REGISTER


def test_an_answer_that_is_not_2xx_is_an_error_and_writes_no_file(tmp_path: Path) -> None:
    source = ScriptedSource({REGISTER: RawResponse(404, "text/html", b"<h1>gone</h1>")})

    with pytest.raises(SetupError, match="HTTP 404"):
        run(tmp_path, source, {"register"})

    assert names(tmp_path / "raw" / "registry") == []


def test_a_failed_initiative_writes_no_index_and_a_rerun_asks_only_for_the_rest(
    tmp_path: Path,
) -> None:
    broken = ScriptedSource(crawl_responses())
    with pytest.raises(SetupError, match=r"hys-index\.jsonl was not built .*404.*is cached"):
        run(tmp_path, broken, {"hys"})
    assert not CollectInputs.under(tmp_path).hys_index.exists()

    repaired = ScriptedSource(initiatives())
    files = run(tmp_path, repaired, {"hys"})

    assert [item.action for item in files] == ["built"]
    # The first list page and initiative 12527 come from the cache; the crawl stopped
    # at 404, so the second page and 12417 were never asked before.
    assert repaired.calls == [
        hys.initiative_url(404),
        hys.search_url(page=1),
        hys.initiative_url(12417),
    ]


# --- The command ----------------------------------------------------------------------------


def scripted_cli(monkeypatch: pytest.MonkeyPatch, source: ScriptedSource) -> None:
    """The real command over the script, with a limiter that never sleeps and a fixed clock."""
    monkeypatch.setattr(cli, "UrllibFetcher", lambda: source)
    fetcher = partial(CachedFetcher, limiter=RateLimiter(interval=0.0), clock=lambda: NOW)
    monkeypatch.setattr(cli, "CachedFetcher", fetcher)


def row(output: str, name: str) -> str:
    (found,) = (line for line in output.splitlines() if line.startswith(f"  {name} "))
    return found


def test_the_command_prints_each_file_with_its_size_hash_and_action(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    export = b"<register>" + b"x" * 1990 + b"</register>"
    scripted_cli(
        monkeypatch, ScriptedSource({**bulk_files(), REGISTER: RawResponse(200, None, export)})
    )
    arguments = ["setup", "--data-root", str(tmp_path), "--only", "register, parltrack"]

    status = cli.main(arguments)

    captured = capsys.readouterr()
    assert (status, captured.err) == (0, "")
    assert captured.out.startswith(f"Set up {tmp_path} in ")
    sha = hashlib.sha256(export).hexdigest()[:12]
    assert re.fullmatch(
        rf"  raw/registry/register\.xml +2,011  {sha} +fetched",
        row(captured.out, "raw/registry/register.xml"),
    )
    assert row(captured.out, "raw/parltrack/ep_plenary_amendments.json.zst").endswith("fetched")
    assert "catalog/hys-index.jsonl" not in captured.out

    assert cli.main(arguments) == 0
    assert row(capsys.readouterr().out, "raw/registry/register.xml").endswith("kept")


def test_the_command_lists_what_finished_then_names_the_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    files = bulk_files()
    del files[REGISTER]
    scripted_cli(monkeypatch, ScriptedSource(files))

    status = cli.main(["setup", "--data-root", str(tmp_path)])

    captured = capsys.readouterr()
    assert status == 1
    assert captured.out.startswith("Stopped after ")
    assert row(captured.out, "raw/parltrack/ep_meps.json.zst").endswith("fetched")
    assert "register.xml" not in captured.out
    assert captured.err.startswith(
        f"error: register.xml was not downloaded and is unchanged: {REGISTER}: No response"
    )
    assert names(tmp_path / "raw" / "registry") == []


def test_the_command_builds_the_index_under_the_default_root_and_shows_progress(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    scripted_cli(monkeypatch, ScriptedSource(initiatives()))
    monkeypatch.setenv("INFLUENCE_DATA_ROOT", str(tmp_path))

    status = cli.main(["setup", "--only", "hys"])

    captured = capsys.readouterr()
    assert status == 0
    assert row(captured.out, "catalog/hys-index.jsonl").endswith("built")
    # Three initiatives: only the last is reported, as every 250th would be.
    assert captured.err == "  Have Your Say index: 3 of 3 initiatives\n"


def test_the_command_refuses_an_unknown_group(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as stopped:
        cli.main(["setup", "--only", "parltrack,votes"])
    assert stopped.value.code == 2
    assert "unknown 'votes'; choose from parltrack,register,hys" in capsys.readouterr().err
