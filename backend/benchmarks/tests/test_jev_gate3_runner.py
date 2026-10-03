"""Offline budget and cache regression checks.

Run with the backend environment: python -m pytest benchmarks/tests/test_jev_gate3_runner.py.

All model responses come from a local function. No environment file or provider is read.
"""

import io
import json
import ssl
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import SecretStr

from benchmarks.jev_gate3 import (
    RESERVE_USD,
    CachedResult,
    PreparedCase,
    PreparedTrial,
    build_request,
    charged,
    load_ledger,
    load_trial,
    main,
    real_case,
    request_bytes,
    run_trial,
    write,
)
from influence.services.jev import MAX_REQUEST_BYTES, JevClient, JevError
from tests.atlas_fixture import build_fixture


class RunnerChecks(unittest.TestCase):
    def setUp(self) -> None:
        self.calls = 0
        self.trial = PreparedTrial(
            source_hashes={},
            cases=[
                PreparedCase(
                    case_id=str(index),
                    family="nli-v1",
                    state={"premise": f"Premise {index}", "hypothesis": "Hypothesis"},
                    metadata={"label_never_sent": "entailment"},
                )
                for index in range(2)
            ],
        )

    def transport(
        self, body: bytes, api_key: SecretStr, timeout: float, context: ssl.SSLContext
    ) -> bytes:
        self.calls += 1
        payload = json.loads(body)
        assert set(payload["state"]) == {"premise", "hypothesis"}
        assert "label_never_sent" not in body.decode()
        return json.dumps(
            {
                "model": "jev-1.13.0",
                "answers": {
                    "relation": {
                        "type": "choice",
                        "choice": "entailment",
                        "probabilities": {"entailment": 1.0, "contradiction": 0.0, "neutral": 0.0},
                        "confidence": 1.0,
                    }
                },
                "usage": {"input_tokens": 200, "output_tokens": 0},
            }
        ).encode()

    def client(self) -> JevClient:
        return JevClient(
            SecretStr("offline-test-value"), ssl.create_default_context(), transport=self.transport
        )

    def test_actual_usage_reconciles_and_completed_requests_are_cached(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            first = run_trial(self.trial, output, self.client(), RESERVE_USD, 32)
            assert first["status"] == "cost_cap"
            assert self.calls == 1
            assert charged(load_ledger(output)) == pytest.approx(200 * 0.042 / 1_000_000)
            second = run_trial(self.trial, output, self.client(), 1, 32)
            assert second["status"] == "complete"
            assert self.calls == 2
            assert run_trial(self.trial, output, self.client(), 1, 32)["status"] == "complete"
            assert self.calls == 2
            for path in (output / "results").glob("*.json"):
                cached = CachedResult.model_validate_json(path.read_bytes())
                assert cached.elapsed_seconds >= 0
            inputs = output / "inputs.json"
            write(inputs, self.trial)
            with (
                patch(
                    "sys.argv",
                    [
                        "runner",
                        "run",
                        "--inputs",
                        str(inputs),
                        "--out",
                        str(output),
                        "--execute",
                        "--env-file",
                        "/missing-env",
                    ],
                ),
                redirect_stdout(io.StringIO()),
            ):
                assert main() == 0
            assert self.calls == 2

    def test_failed_request_keeps_full_reservation_and_is_not_retried(self) -> None:
        def fail(body: bytes, api_key: SecretStr, timeout: float, context: ssl.SSLContext) -> bytes:
            self.calls += 1
            raise JevError("Deliberate offline failure")

        one = self.trial.model_copy(update={"cases": self.trial.cases[:1]})
        client = JevClient(
            SecretStr("offline-test-value"), ssl.create_default_context(), transport=fail
        )
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            assert run_trial(one, output, client, 1, 32)["status"] == "request_failed"
            assert charged(load_ledger(output)) == RESERVE_USD
            assert run_trial(one, output, client, 1, 32)["status"] == "incomplete_previous_failure"
            assert self.calls == 1

    def test_request_cap_and_dry_run_need_no_credential(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            assert run_trial(self.trial, output, self.client(), 1, 1)["status"] == "request_cap"
            assert self.calls == 1
            inputs = output / "inputs.json"
            write(inputs, self.trial)
            base = [
                "runner",
                "run",
                "--inputs",
                str(inputs),
                "--out",
                str(output),
                "--env-file",
                "/missing-env",
            ]
            with patch("sys.argv", base), redirect_stdout(io.StringIO()):
                assert main() == 0
            with (
                patch("sys.argv", [*base, "--execute", "--max-requests", "1"]),
                redirect_stdout(io.StringIO()),
            ):
                assert main() == 2
            assert self.calls == 1

    def test_state_validation_rejects_extra_labels_and_oversized_inputs(self) -> None:
        case = self.trial.cases[0].model_copy(
            update={"state": {"premise": "x", "hypothesis": "y", "label": "entailment"}}
        )
        with pytest.raises(ValueError, match="Extra inputs"):
            build_request(case)
        case = self.trial.cases[0].model_copy(
            update={"state": {"premise": "x" * 25000, "hypothesis": "y"}}
        )
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "inputs.json"
            write(path, self.trial.model_copy(update={"cases": [case]}))
            with pytest.raises(ValueError, match="byte bound"):
                load_trial(path)


if __name__ == "__main__":
    unittest.main()


def test_real_case_keeps_exact_context_and_unknown_original_without_truncation() -> None:
    fixture = build_fixture()
    link = fixture.links[0]
    ask = next(ask for ask in fixture.asks if ask.ask_id == link.ask_id)
    amendment = next(am for am in fixture.amendments if am.amendment_id == link.amendment_id)
    original = next(
        text.text for text in fixture.document_texts if text.document_id == ask.document_id
    )
    unknown = amendment.model_copy(update={"old_text": None})
    case = real_case(link, ask, unknown, original, (), "run:test")
    assert case.state["submission_new"] == original[ask.span.start : ask.span.end]
    assert (
        case.state["preceding_context"] == original[max(0, ask.span.start - 1200) : ask.span.start]
    )
    assert case.state["following_context"] == original[ask.span.end : ask.span.end + 300]
    assert case.state["amendment_old"] is None
    assert case.state["amendment_new"] == amendment.new_text
    assert case.state["proposal_context_status"] == "unavailable_no_exact_provision"
    assert case.metadata["span_start"] == ask.span.start
    assert "support_score" not in build_request(case).model_dump_json()
    with pytest.raises(ValueError, match="offsets"):
        real_case(link, ask, unknown, "corrupted source", (), "run:test")
    article = fixture.articles[0].model_copy(update={"provision": "Article 5", "text": "x" * 30000})
    bounded = real_case(link, ask, unknown, original, (article,), "run:test")
    assert bounded.state["proposal_text"] is None
    assert (
        bounded.state["proposal_context_status"] == "omitted_full_provision_exceeds_request_bound"
    )
    assert bounded.state["submission_new"] == ask.span.text
    assert bounded.state["amendment_new"] == amendment.new_text


@pytest.mark.parametrize(
    ("target", "labels", "expected"),
    [
        (
            "Proposal - Article 1 \u2013 paragraph 2",
            ("Article 1(1)", "Article 1(2)", "Article 10(1)"),
            ("Article 1(1)", "Article 1(2)"),
        ),
        ("Proposal - Recital 47", ("Recital 47", "Recital 470", "Article 47(1)"), ("Recital 47",)),
        (
            "article 9 paragraph 3",
            ("ARTICLE 9(3)", "Article 9(4)", "Article 90"),
            ("ARTICLE 9(3)", "Article 9(4)"),
        ),
        ("Article 1a (new)", ("Article 1(1)", "Article 1a", "Article 10"), ("Article 1a",)),
        ("Annex III", ("Article 3", "Recital 3"), ()),
    ],
)
def test_v2_matches_full_paragraph_group_or_recital_without_prefix_collisions(
    target: str, labels: tuple[str, ...], expected: tuple[str, ...]
) -> None:
    fixture = build_fixture()
    link, ask, amendment = fixture.links[0], fixture.asks[0], fixture.amendments[0]
    text = next(t.text for t in fixture.document_texts if t.document_id == ask.document_id)
    amendment = amendment.model_copy(update={"target_provision": target})
    template = fixture.articles[0]
    articles = tuple(
        template.model_copy(
            update={
                "article_id": f"article:case-{i}",
                "provision": label,
                "text": f"Original text {i}.",
            }
        )
        for i, label in enumerate(labels)
    )
    # Matching labels from a final act or a different procedure must not enter proposal context.
    decoys = (
        articles[0].model_copy(update={"stage": "final_act", "text": "Wrong stage"}),
        articles[0].model_copy(update={"procedure_id": "2022/0140(COD)", "text": "Wrong law"}),
    )
    case = real_case(
        link, ask, amendment, text, (*articles, *decoys), "run:test", context_version="proposal-v2"
    )
    assert case.metadata["proposal_provisions"] == list(expected)
    assert case.state["proposal_text"] == (
        "\n\n".join(f"{a.provision}\n{a.text}" for a in articles if a.provision in expected)
        if expected
        else None
    )
    assert case.state["submission_new"] == ask.span.text
    assert case.metadata["proposal_context_version"] == "proposal-v2"
    assert (
        build_request(case).questions
        == build_request(real_case(link, ask, amendment, text, articles, "run:test")).questions
    )


def test_v2_omits_whole_oversize_group_with_ids_and_does_not_change_v1() -> None:
    fixture = build_fixture()
    link, ask, amendment = fixture.links[0], fixture.asks[0], fixture.amendments[0]
    text = next(t.text for t in fixture.document_texts if t.document_id == ask.document_id)
    amendment = amendment.model_copy(update={"target_provision": "Article 5 paragraph 1"})
    article = fixture.articles[0].model_copy(
        update={"provision": "Article 5(1)", "text": "界" * MAX_REQUEST_BYTES}
    )
    v1 = real_case(link, ask, amendment, text, (article,), "run:test")
    assert v1 == real_case(
        link, ask, amendment, text, (article,), "run:test", context_version="proposal-v1"
    )
    assert v1.state["proposal_context_status"] == "unavailable_no_exact_provision"
    assert "proposal_context_version" not in v1.metadata
    v2 = real_case(
        link, ask, amendment, text, (article,), "run:test", context_version="proposal-v2"
    )
    assert v2.state["proposal_context_status"] == "omitted_full_provision_exceeds_request_bound"
    assert v2.state["proposal_text"] is None
    assert v2.metadata["proposal_article_ids"] == [article.article_id]
    assert v2.state["amendment_old"] == amendment.old_text
    assert v2.state["amendment_new"] == amendment.new_text
    assert v2.state["submission_new"] == ask.span.text
    assert len(request_bytes(build_request(v2))) <= MAX_REQUEST_BYTES


def test_canonical_philips_ask_requires_third_party_attribution_context() -> None:
    fixture = build_fixture()
    link, ask, amendment = fixture.links[0], fixture.asks[0], fixture.amendments[0]
    text = next(t.text for t in fixture.document_texts if t.document_id == ask.document_id)
    ask = ask.model_copy(update={"ask_id": "ask:passage-doc-hys_attachment-090166e5d35cddb0-32"})
    with pytest.raises(ValueError, match="Required Philips third-party attribution context"):
        real_case(link, ask, amendment, text, (), "run:test")
    prefix = "Definition attributed to AI HLEG. "
    shifted = ask.model_copy(
        update={
            "span": ask.span.model_copy(
                update={"start": ask.span.start + len(prefix), "end": ask.span.end + len(prefix)}
            )
        }
    )
    case = real_case(link, shifted, amendment, prefix + text, (), "run:test")
    assert "AI HLEG" in str(case.state["preceding_context"])
