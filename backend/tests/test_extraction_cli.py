"""The extraction command line: exit codes, written files and one-line failures."""

import runpy
import sys
from io import StringIO
from pathlib import Path

import pytest
from extraction_fixtures import FETCHED_AT, RecordingFetcher

from influence.extraction import catalog, cli
from influence.extraction.cache import HttpCache
from influence.extraction.fetching import CachedFetcher, RateLimiter, RawResponse
from influence.extraction.layout import DataLayout

REGISTRY_URL = "https://transparency-register.europa.eu/"
OEIL_URL = "https://oeil.secure.europarl.europa.eu/"


def install_fetcher(
    monkeypatch: pytest.MonkeyPatch, responses: dict[str, RawResponse]
) -> RecordingFetcher:
    """Replace the command line's network seam, so no test reaches the internet."""
    recording = RecordingFetcher(responses, [])

    def build(root: Path) -> CachedFetcher:
        return CachedFetcher(
            cache=HttpCache(DataLayout(root).cache),
            fetcher=recording,
            limiter=RateLimiter(monotonic=lambda: 0.0, sleep=lambda _: None),
            clock=lambda: FETCHED_AT,
        )

    monkeypatch.setattr(cli, "_fetcher", build)
    return recording


def test_the_data_root_comes_from_the_environment_or_the_repository_checkout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("INFLUENCE_DATA_ROOT", str(tmp_path / "elsewhere"))
    assert cli.default_data_root() == tmp_path / "elsewhere"
    monkeypatch.delenv("INFLUENCE_DATA_ROOT")
    assert cli.default_data_root().name == "data"


def test_the_fetcher_caches_under_the_data_root_it_was_given(tmp_path: Path) -> None:
    fetcher = cli._fetcher(tmp_path)  # pyright: ignore[reportPrivateUsage]
    assert fetcher.cache.directory == DataLayout(tmp_path).cache


def test_sources_lists_the_whole_catalog_and_a_single_scope() -> None:
    everything = StringIO()
    assert cli.main(["sources"], everything) == 0
    assert "A registry [global/confirmed] https://" in everything.getvalue()
    assert "H amendments [per_law/unverified] no base URL" in everything.getvalue()
    scoped = StringIO()
    assert cli.main(["sources", "--scope", "global"], scoped) == 0
    assert "E oeil" not in scoped.getvalue()
    assert len(scoped.getvalue().splitlines()) == 4


def answers(scope: catalog.Scope, status: int = 200) -> dict[str, RawResponse]:
    """One scripted response per probeable URL in a scope, taken from the catalog itself."""
    return {
        spec.probe_url: RawResponse(status, "text/html", b"ok")
        for spec in catalog.probeable(catalog.by_scope(scope))
        if spec.probe_url is not None
    }


def test_probe_writes_its_report_and_succeeds_when_every_source_answers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    responses = answers("global")
    recording = install_fetcher(monkeypatch, responses)
    out = StringIO()
    code = cli.main(["--data-root", str(tmp_path), "probe", "--scope", "global", "--refresh"], out)
    report = DataLayout(tmp_path).global_source("probe") / "probe-report.json"
    assert code == 0
    assert sorted(recording.calls) == sorted(responses)
    assert REGISTRY_URL in recording.calls
    assert report.is_file()
    assert "Report written to" in out.getvalue()


def test_probe_exits_non_zero_when_a_source_is_unreachable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    responses = answers("per_law")
    responses[OEIL_URL] = RawResponse(503, None, b"")
    install_fetcher(monkeypatch, responses)
    out = StringIO()
    assert cli.main(["--data-root", str(tmp_path), "probe", "--scope", "per_law"], out) == 1
    assert "unreachable: HTTP 503" in out.getvalue()


def test_fetch_stores_the_bytes_and_reports_where_they_went(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    url = "https://transparency-register.europa.eu/full.xml"
    install_fetcher(monkeypatch, {url: RawResponse(200, "text/xml", b"<register/>")})
    out = StringIO()
    code = cli.main(["--data-root", str(tmp_path), "fetch", "A", url, "--name", "full.xml"], out)
    assert code == 0
    assert (DataLayout(tmp_path).global_source("registry") / "full.xml").read_bytes() == (
        b"<register/>"
    )
    assert "11 bytes to" in out.getvalue()


def test_an_unknown_source_is_one_line_and_exit_code_two(tmp_path: Path) -> None:
    out = StringIO()
    assert (
        cli.main(["--data-root", str(tmp_path), "fetch", "Z", "https://a.eu", "--name", "x"], out)
        == 2
    )
    assert out.getvalue().startswith("error:")
    assert len(out.getvalue().splitlines()) == 1


def test_output_goes_to_standard_output_when_no_stream_is_given(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli.main(["sources", "--scope", "enrichment"]) == 0
    assert "I lobbyfacts" in capsys.readouterr().out


def test_the_module_entry_point_runs_the_command_line(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "argv", ["influence-extract", "sources", "--scope", "global"])
    with pytest.raises(SystemExit) as exit_code:
        runpy.run_module("influence.extraction", run_name="__main__")
    assert exit_code.value.code == 0
    assert "A registry" in capsys.readouterr().out
