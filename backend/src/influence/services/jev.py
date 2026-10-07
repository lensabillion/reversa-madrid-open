"""Bounded TypeSafe transport for optional Jev judgments of reworded origins.

Contract: https://docs.typesafe.ai/api and /models, checked 3 October 2026. The caller
reserves its monetary budget before each call and records returned usage afterwards.
Failures may still be billed: never refund a reservation solely because a call failed.
No credentials are read from the environment and no retries are hidden in this adapter.
"""

import http.client
import json
import math
import ssl
import urllib.error
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Annotated, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, JsonValue, SecretStr, ValidationError

MODEL = "jev-1.13.0"
ENDPOINT = "https://api.typesafe.ai/v1/systemone"
MAX_REQUEST_BYTES = 24_000
MAX_RESPONSE_BYTES = 64_000
# Reserve the documented entire 64k context at the current input-token price, not an
# optimistic characters/4 estimate. The runner owns the price and aggregate dollar cap.
REQUEST_TOKEN_RESERVE = 65_536
type Structured = str | dict[str, JsonValue] | list[JsonValue]
type Probability = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]
type QuestionId = Annotated[str, Field(min_length=1)]


class JevError(RuntimeError):
    """Sanitized failure: never includes a response body, submitted text or credentials."""


class _Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, allow_inf_nan=False)


class NoulQuestion(_Contract):
    type: Literal["noul"] = "noul"
    instructions: Structured
    criteria: dict[Literal["true", "false"], Structured] | None = None


class ChoiceQuestion(_Contract):
    type: Literal["choice"] = "choice"
    instructions: Structured
    criteria: Annotated[dict[QuestionId, Structured | None], Field(min_length=2, max_length=255)]


type Question = Annotated[NoulQuestion | ChoiceQuestion, Field(discriminator="type")]


class JevRequest(_Contract):
    model: Literal["jev-1.13.0"] = MODEL
    state: Structured
    questions: Annotated[dict[QuestionId, Question], Field(min_length=1, max_length=32)]


class NoulAnswer(_Contract):
    type: Literal["noul"]
    noul: Probability


class Usage(_Contract):
    input_tokens: Annotated[int, Field(ge=0, le=REQUEST_TOKEN_RESERVE)]
    output_tokens: Annotated[int, Field(ge=0)]


class ChoiceAnswer(_Contract):
    type: Literal["choice"]
    choice: str
    probabilities: dict[QuestionId, Probability]
    confidence: Probability


type Answer = Annotated[NoulAnswer | ChoiceAnswer, Field(discriminator="type")]


class JevResult(_Contract):
    model: Literal["jev-1.13.0"]
    answers: dict[QuestionId, Answer]
    usage: Usage


class PostTransport(Protocol):
    def __call__(
        self, body: bytes, api_key: SecretStr, timeout: float, context: ssl.SSLContext
    ) -> bytes: ...


class _NoRedirect(urllib.request.HTTPErrorProcessor):
    """Return HTTP statuses directly, preventing urllib from forwarding authorization."""

    def http_response(
        self, request: urllib.request.Request, response: http.client.HTTPResponse
    ) -> http.client.HTTPResponse:
        return response

    https_response = http_response


def urllib_post(body: bytes, api_key: SecretStr, timeout: float, context: ssl.SSLContext) -> bytes:
    """One bounded HTTPS POST. Redirects and non-200 responses are explicit failures."""
    request = urllib.request.Request(
        ENDPOINT,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key.get_secret_value()}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    opener = urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=context), _NoRedirect()
    )
    with opener.open(request, timeout=timeout) as response:
        if response.status != 200:
            raise JevError(f"TypeSafe returned HTTP {response.status}; no retry attempted")
        return response.read(MAX_RESPONSE_BYTES + 1)


@dataclass(frozen=True)
class JevClient:
    api_key: SecretStr = field(repr=False)
    context: ssl.SSLContext = field(repr=False)
    timeout: float = 30.0
    transport: PostTransport = field(default=urllib_post, repr=False)

    def __post_init__(self) -> None:
        if not self.api_key.get_secret_value().strip():
            raise JevError("TypeSafe credential is empty")
        if not math.isfinite(self.timeout) or self.timeout <= 0:
            raise JevError("TypeSafe timeout must be finite and positive")
        if self.context.verify_mode != ssl.CERT_REQUIRED or not self.context.check_hostname:
            raise JevError("TypeSafe requires certificate and hostname verification")

    def evaluate(self, state: Structured, questions: Mapping[str, Question]) -> JevResult:
        """Validate both sides of one call; the caller must separately budget its usage."""
        try:
            request = JevRequest(state=state, questions=dict(questions))
            body = json.dumps(
                request.model_dump(exclude_none=True), ensure_ascii=False, allow_nan=False
            ).encode("utf-8")
        except ValidationError, ValueError, UnicodeError:
            raise JevError("Invalid TypeSafe request") from None
        if len(body) > MAX_REQUEST_BYTES:
            raise JevError("TypeSafe request exceeds the byte limit; input was not truncated")
        try:
            raw = self.transport(body, self.api_key, self.timeout, self.context)
        except urllib.error.URLError, OSError, http.client.HTTPException, ValueError:
            raise JevError("TypeSafe transport failed; no retry attempted") from None
        if len(raw) > MAX_RESPONSE_BYTES:
            raise JevError("TypeSafe response exceeds the byte limit")
        try:
            result = JevResult.model_validate_json(raw)
        except ValidationError:
            raise JevError("Invalid TypeSafe response") from None
        if result.answers.keys() != questions.keys():
            raise JevError("TypeSafe answer IDs do not match the question IDs")
        for identifier, question in questions.items():
            answer = result.answers[identifier]
            if answer.type != question.type:
                raise JevError("TypeSafe answer type does not match the question")
            if isinstance(question, ChoiceQuestion) and isinstance(answer, ChoiceAnswer):
                probabilities = answer.probabilities
                if probabilities.keys() != question.criteria.keys():
                    raise JevError("TypeSafe choice options do not match the question")
                if not math.isclose(sum(probabilities.values()), 1, abs_tol=1e-6):
                    raise JevError("TypeSafe choice probabilities do not sum to one")
                if answer.choice not in probabilities or probabilities[answer.choice] != max(
                    probabilities.values()
                ):
                    raise JevError("TypeSafe choice is not a highest-probability option")
        return result
