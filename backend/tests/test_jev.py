"""Offline provider contract, input budgets and failure isolation; never call TypeSafe."""

import http.client
import json
import ssl
import urllib.error
import urllib.request
from typing import Any

import pytest
from pydantic import SecretStr

from influence.services import jev

QUESTIONS = {"same_change": jev.NoulQuestion(instructions="Same legal change?")}
SECRET = SecretStr("offline-test-credential")


def response(**changes: object) -> bytes:
    return json.dumps(
        {
            "model": jev.MODEL,
            "answers": {"same_change": {"type": "noul", "noul": 0.75}},
            "usage": {"input_tokens": 120, "output_tokens": 10},
            **changes,
        }
    ).encode()


class FakePost:
    def __init__(self, raw: bytes = response(), error: Exception | None = None) -> None:
        self.raw = raw
        self.error = error
        self.calls: list[bytes] = []

    def __call__(
        self, body: bytes, api_key: SecretStr, timeout: float, context: ssl.SSLContext
    ) -> bytes:
        self.calls.append(body)
        assert api_key == SECRET
        assert timeout == 30
        assert context.check_hostname
        if self.error is not None:
            raise self.error
        return self.raw


def client(transport: jev.PostTransport) -> jev.JevClient:
    return jev.JevClient(SECRET, ssl.create_default_context(), transport=transport)


def test_structured_unicode_request_and_usage_round_trip_without_credentials() -> None:
    post = FakePost()
    adapter = client(post)
    question = jev.NoulQuestion(
        instructions={"question": "Même effet juridique?", "language": "fr"},
        criteria={"true": "Identique", "false": ["Opposé", "Sans rapport"]},
    )
    result = adapter.evaluate(
        {"proposal": "Café — doit conserver", "old": None}, {"same_change": question}
    )
    assert isinstance(result.answers["same_change"], jev.NoulAnswer)
    assert result.answers["same_change"].noul == 0.75
    assert result.usage.input_tokens == 120
    assert result.usage.output_tokens == 10
    assert len(post.calls) == 1
    sent = json.loads(post.calls[0])
    assert sent["model"] == "jev-1.13.0"
    assert sent["state"] == {"proposal": "Café — doit conserver", "old": None}
    assert sent["questions"]["same_change"]["criteria"]["false"] == ["Opposé", "Sans rapport"]
    assert SECRET.get_secret_value() not in repr(adapter) + str(result) + post.calls[0].decode()


@pytest.mark.parametrize("value", [-0.1, 1.1, float("nan"), float("inf"), True, "0.5"])
def test_answer_probability_is_strict_finite_and_bounded(value: object) -> None:
    post = FakePost(response(answers={"same_change": {"type": "noul", "noul": value}}))
    with pytest.raises(jev.JevError, match="Invalid TypeSafe response"):
        client(post).evaluate("text", QUESTIONS)


@pytest.mark.parametrize(
    "changes",
    [
        {"model": "jev-latest"},
        {"usage": {"input_tokens": -1, "output_tokens": 0}},
        {"usage": {"input_tokens": 1.5, "output_tokens": 0}},
        {"usage": {"input_tokens": True, "output_tokens": 0}},
        {"usage": {"input_tokens": 1}},
        {"answers": {"same_change": {"type": "choice", "choice": "yes"}}},
    ],
)
def test_model_answer_type_and_usage_are_validated(changes: dict[str, object]) -> None:
    with pytest.raises(jev.JevError, match="Invalid TypeSafe response"):
        client(FakePost(response(**changes))).evaluate("text", QUESTIONS)


@pytest.mark.parametrize("answers", [{}, {"wrong": {"type": "noul", "noul": 0.9}}])
def test_ids_must_match_exactly(answers: dict[str, object]) -> None:
    with pytest.raises(jev.JevError, match="IDs do not match"):
        client(FakePost(response(answers=answers))).evaluate("text", QUESTIONS)


@pytest.mark.parametrize("raw", [b"not-json private data", b"\xff", b"{}"])
def test_malformed_response_does_not_echo_content(raw: bytes) -> None:
    with pytest.raises(jev.JevError, match=r"^Invalid TypeSafe response$"):
        client(FakePost(raw)).evaluate("text", QUESTIONS)


@pytest.mark.parametrize(
    "error",
    [
        urllib.error.URLError("secret"),
        TimeoutError("secret"),
        http.client.HTTPException("secret"),
        ValueError("Invalid header value: secret"),
    ],
)
def test_transport_failure_is_sanitized_and_never_retried(error: Exception) -> None:
    post = FakePost(error=error)
    with pytest.raises(jev.JevError, match=r"^TypeSafe transport failed; no retry attempted$"):
        client(post).evaluate("text", QUESTIONS)
    assert len(post.calls) == 1


def test_request_bytes_bound_unicode_before_transport_and_response_bound() -> None:
    post = FakePost()
    with pytest.raises(jev.JevError, match="request exceeds"):
        client(post).evaluate("界" * (jev.MAX_REQUEST_BYTES // 2), QUESTIONS)
    assert post.calls == []
    with pytest.raises(jev.JevError, match="response exceeds"):
        client(FakePost(b" " * (jev.MAX_RESPONSE_BYTES + 1))).evaluate("text", QUESTIONS)


@pytest.mark.parametrize("state", [{"value": float("nan")}, "\ud800"])
def test_invalid_json_state_fails_before_transport(state: jev.Structured) -> None:
    post = FakePost()
    with pytest.raises(jev.JevError, match="Invalid TypeSafe request"):
        client(post).evaluate(state, QUESTIONS)
    assert post.calls == []


@pytest.mark.parametrize("questions", [{}, {"": QUESTIONS["same_change"]}])
def test_invalid_question_map_fails_before_transport(
    questions: dict[str, jev.NoulQuestion],
) -> None:
    post = FakePost()
    with pytest.raises(jev.JevError, match="Invalid TypeSafe request"):
        client(post).evaluate([], questions)
    assert post.calls == []


@pytest.mark.parametrize("timeout", [0, -1, float("inf"), float("nan")])
def test_invalid_client_timeout(timeout: float) -> None:
    with pytest.raises(jev.JevError, match="timeout"):
        jev.JevClient(SECRET, ssl.create_default_context(), timeout=timeout)


def test_empty_key_or_unverified_tls_rejected() -> None:
    context = ssl.create_default_context()
    with pytest.raises(jev.JevError, match="credential"):
        jev.JevClient(SecretStr("  "), context)
    context.check_hostname = False
    with pytest.raises(jev.JevError, match="verification"):
        jev.JevClient(SECRET, context)
    context.verify_mode = ssl.CERT_NONE
    with pytest.raises(jev.JevError, match="verification"):
        jev.JevClient(SECRET, context)


@pytest.mark.parametrize("status", [200, 302, 401, 429, 529])
def test_real_transport_fixed_endpoint_timeout_headers_read_bound_and_no_redirect(
    monkeypatch: pytest.MonkeyPatch, status: int
) -> None:
    calls: list[tuple[urllib.request.Request, float]] = []

    class Reply:
        status: int = 0

        def __enter__(self) -> Any:
            return self

        def __exit__(self, *args: object) -> None:
            pass

        def read(self, size: int) -> bytes:
            assert size == jev.MAX_RESPONSE_BYTES + 1
            return response()

    reply = Reply()
    reply.status = status

    class Opener:
        def open(self, request: urllib.request.Request, *, timeout: float) -> Reply:
            calls.append((request, timeout))
            return reply

    def build_opener(*handlers: Any) -> Opener:
        assert handlers[1].https_response(None, reply) is reply
        return Opener()

    monkeypatch.setattr(urllib.request, "build_opener", build_opener)
    if status == 200:
        assert client(jev.urllib_post).evaluate("text", QUESTIONS).usage.input_tokens == 120
    else:
        with pytest.raises(jev.JevError, match=f"HTTP {status}; no retry attempted"):
            client(jev.urllib_post).evaluate("text", QUESTIONS)
    assert len(calls) == 1
    request, timeout = calls[0]
    assert request.full_url == jev.ENDPOINT
    assert request.method == "POST"
    assert request.get_header("Authorization") == f"Bearer {SECRET.get_secret_value()}"
    assert request.get_header("Content-type") == "application/json"
    assert timeout == 30


CHOICE = jev.ChoiceQuestion(
    instructions="Does the premise entail or contradict the hypothesis?",
    criteria={"entailment": "Follows", "contradiction": "Opposed", "neutral": None},
)


def choice_response(**changes: object) -> bytes:
    return response(
        answers={
            "same_change": {
                "type": "choice",
                "choice": "entailment",
                "confidence": 0.8,
                "probabilities": {"entailment": 0.8, "contradiction": 0.1, "neutral": 0.1},
                **changes,
            }
        }
    )


def test_choice_answer_and_tied_highest_probability_are_supported() -> None:
    post = FakePost(choice_response())
    result = client(post).evaluate(
        {"premise": "must", "hypothesis": "may"}, {"same_change": CHOICE}
    )
    answer = result.answers["same_change"]
    assert isinstance(answer, jev.ChoiceAnswer)
    assert answer.choice == "entailment"
    assert answer.probabilities == {"entailment": 0.8, "contradiction": 0.1, "neutral": 0.1}
    assert json.loads(post.calls[0])["questions"]["same_change"]["criteria"]["neutral"] is None
    tied = choice_response(probabilities={"entailment": 0.5, "contradiction": 0.5, "neutral": 0})
    assert client(FakePost(tied)).evaluate("text", {"same_change": CHOICE}).answers


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"probabilities": {"entailment": 1}}, "options do not match"),
        (
            {"probabilities": {"entailment": 0.9, "contradiction": 0.1, "neutral": 0.1}},
            "do not sum",
        ),
        ({"choice": "missing"}, "highest-probability"),
        ({"choice": "neutral"}, "highest-probability"),
        ({"confidence": float("nan")}, "Invalid TypeSafe response"),
    ],
)
def test_invalid_choice_semantics(changes: dict[str, object], message: str) -> None:
    with pytest.raises(jev.JevError, match=message):
        client(FakePost(choice_response(**changes))).evaluate("text", {"same_change": CHOICE})


@pytest.mark.parametrize(
    ("raw", "questions"),
    [
        (choice_response(), QUESTIONS),
        (response(), {"same_change": CHOICE}),
    ],
)
def test_response_type_must_match_each_question(
    raw: bytes, questions: dict[str, jev.Question]
) -> None:
    with pytest.raises(jev.JevError, match="type does not match"):
        client(FakePost(raw)).evaluate("text", questions)


def test_usage_above_reserved_context_is_rejected() -> None:
    raw = response(usage={"input_tokens": jev.REQUEST_TOKEN_RESERVE + 1, "output_tokens": 0})
    with pytest.raises(jev.JevError, match="Invalid TypeSafe response"):
        client(FakePost(raw)).evaluate("text", QUESTIONS)
