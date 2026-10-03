"""Deterministic English edit signals, not probabilities or legal entailment.

Fit rarity on training documents only. Context checks compare English cue inventories
inside changed clauses sharing a content word; they cannot resolve exceptions,
coreference, cross-sentence scope, multilingual meaning, or numerical equivalence.
Missing modal/quantity cues are not proof of agreement. Publication remains upstream.
"""

import hashlib
import json
from collections import Counter
from collections.abc import Sequence
from math import log

from influence.schemas.scoring import TOKEN_PATTERN, ChangeSpan, Operation, ScoreRequest, TextChange
from influence.services.scoring import score_pair

# Phrases never cross changed runs or operation boundaries.
_PHRASE_WIDTHS = (1, 3, 4, 5)
_SHORT_EDIT_TOKENS = 8
_SENTENCE_ENDS = frozenset({".", ";", "!", "?"})
_NEGATIONS = frozenset({"not", "no", "never", "without", "neither", "nor", "cannot"})
_MODAL_CLASSES = {
    "shall": "obligation",
    "must": "obligation",
    "required": "obligation",
    "may": "permission",
    "can": "permission",
    "permitted": "permission",
    "should": "recommendation",
}
_CONTEXT_WORDS = (
    frozenset(
        {
            "a",
            "an",
            "the",
            "to",
            "of",
            "and",
            "or",
            "in",
            "on",
            "for",
            "by",
            "with",
            "as",
            "at",
            "be",
            "is",
            "are",
            "it",
            "that",
            "this",
            "than",
            "least",
            "most",
            "more",
            "less",
            "only",
            "from",
            "after",
            "before",
        }
    )
    | _NEGATIONS
    | _MODAL_CLASSES.keys()
)
_BOUND_PHRASES = {
    ("at", "least"): "minimum",
    ("not", "less", "than"): "minimum",
    ("at", "most"): "maximum",
    ("no", "more", "than"): "maximum",
    ("more", "than"): "greater",
    ("less", "than"): "less",
}

_NON_NEGATING = (("not", "only"), ("no", "more", "than"), ("not", "less", "than"))
_COORDINATORS = frozenset({"and", "or", "but"})
_MODAL_LOOKAHEAD = 3

type Phrase = tuple[str, ...]
type Feature = tuple[Operation, Phrase]
type Context = tuple[Operation, tuple[str, ...]]


def _tokens(text: str) -> tuple[str, ...]:
    return tuple(token.casefold() for token in TOKEN_PATTERN.findall(text))


def _phrases(tokens: tuple[str, ...]) -> list[Phrase]:
    return [
        tokens[index : index + width]
        for width in _PHRASE_WIDTHS
        for index in range(len(tokens) - width + 1)
    ]


class SignalCorpus:
    """Training-only phrase document frequencies; repeated text counts once per document.

    Construction is O(T) time/memory for T training tokens and fixed phrase widths.
    Queries never update frequencies. Empty training data is an explicit error; an unseen
    phrase receives the maximum smoothed IDF, log((documents + 1) / (df + 1)) + 1.
    """

    def __init__(self, training_texts: Sequence[str]) -> None:
        if not training_texts:
            raise ValueError("SignalCorpus requires training documents")
        self._fingerprint = hashlib.sha256(
            json.dumps(
                (
                    "edit-idf-3to5-short-unigrams-v2",
                    sorted(hashlib.sha256(text.encode()).hexdigest() for text in training_texts),
                )
            ).encode()
        ).hexdigest()
        self._size = len(training_texts)
        self._frequencies: Counter[Phrase] = Counter()
        for text in training_texts:
            self._frequencies.update(set(_phrases(_tokens(text))))

    @property
    def fingerprint(self) -> str:
        """Order-independent training membership digest; duplicate documents are retained."""
        return self._fingerprint

    def idf(self, phrase: Phrase) -> float:
        """Smoothed training-document rarity; callers pass normalized token tuples."""
        return log((self._size + 1) / (self._frequencies[phrase] + 1)) + 1.0


def _features(changes: tuple[ChangeSpan, ...]) -> Counter[Feature]:
    return Counter(
        (span.operation, phrase)
        for span in changes
        for tokens in (_tokens(span.text),)
        for phrase in _phrases(tokens)
        if (len(phrase) == 1) == (len(tokens) < 3)
    )


def _boundary(tokens: tuple[str, ...], index: int) -> bool:
    # A coordinating clause with its own modal has an independent obligation scope.
    return tokens[index] in _SENTENCE_ENDS or (
        tokens[index] in _COORDINATORS
        and any(word in _MODAL_CLASSES for word in tokens[index + 1 : index + 1 + _MODAL_LOOKAHEAD])
    )


def _contexts(change: TextChange, spans: tuple[ChangeSpan, ...]) -> tuple[Context, ...]:
    result: set[Context] = set()
    for span in spans:
        text = change.new if span.operation == "insert" else change.old
        matches = tuple(TOKEN_PATTERN.finditer(text))
        tokens = tuple(token.group().casefold() for token in matches)
        touched = [
            index
            for index, token in enumerate(matches)
            if token.start() < span.end and token.end() > span.start
        ]
        # changed_spans guarantees at least one token at each supplied interval.
        left, right = touched[0], touched[-1] + 1
        while left > 0 and not _boundary(tokens, left - 1):
            left -= 1
        while right < len(matches) and not _boundary(tokens, right):
            right += 1
        result.add(
            (span.operation, tuple(token.group().casefold() for token in matches[left:right]))
        )
    return tuple(sorted(result))


def _anchors(tokens: tuple[str, ...]) -> set[str]:
    return {token for token in tokens if token.isalpha() and token not in _CONTEXT_WORDS}


def _negations(tokens: tuple[str, ...]) -> int:
    # Additive wording and numeric-bound qualifiers are not obligation negations.
    return sum(
        word in _NEGATIONS
        and not any(tokens[index : index + len(phrase)] == phrase for phrase in _NON_NEGATING)
        for index, word in enumerate(tokens)
    )


def _quantities(tokens: tuple[str, ...]) -> tuple[tuple[str, str, str], ...]:
    quantities: list[tuple[str, str, str]] = []
    for index, token in enumerate(tokens):
        if not token[0].isdigit():
            continue
        bound = "exact"
        for prefix, label in sorted(_BOUND_PHRASES.items(), key=lambda item: -len(item[0])):
            if index >= len(prefix) and tokens[index - len(prefix) : index] == prefix:
                bound = label
                break
        unit = tokens[index + 1] if index + 1 < len(tokens) else ""
        quantities.append((token, unit, bound))
    return tuple(sorted(quantities))


def _context_signals(left: tuple[Context, ...], right: tuple[Context, ...]) -> dict[str, float]:
    comparable = negation = modal = quantity = False
    for left_operation, left_tokens in left:
        for right_operation, right_tokens in right:
            if left_operation != right_operation or not (
                _anchors(left_tokens) & _anchors(right_tokens)
            ):
                continue
            comparable = True
            negation |= _negations(left_tokens) != _negations(right_tokens)
            left_modal = Counter(
                _MODAL_CLASSES[token] for token in left_tokens if token in _MODAL_CLASSES
            )
            right_modal = Counter(
                _MODAL_CLASSES[token] for token in right_tokens if token in _MODAL_CLASSES
            )
            modal |= bool(left_modal and right_modal and left_modal != right_modal)
            left_quantity, right_quantity = _quantities(left_tokens), _quantities(right_tokens)
            quantity |= bool(left_quantity and right_quantity and left_quantity != right_quantity)
    return {
        "context_comparable": float(comparable),
        "negation_conflict": float(negation),
        "modal_conflict": float(modal),
        "quantity_conflict": float(quantity),
    }


def _alignment(
    left: tuple[tuple[Operation, str], ...], right: tuple[tuple[Operation, str], ...]
) -> float:
    """Smith-Waterman: +2 same-operation match, -1 mismatch/gap; longest-side normalization.

    Rolling rows use O(len(right)) memory and O(len(left)*len(right)) time. Each edit
    contains at most 1,600 tokens (800 original plus 800 new). No cross-operation match
    earns positive credit. The maximum local score is normalized by 2*max(lengths).
    """
    if not left or not right:
        return 0.0
    previous = [0] * (len(right) + 1)
    best = 0
    for token in left:
        current = [0]
        for column, other in enumerate(right, 1):
            score = max(
                0,
                previous[column - 1] + (2 if token == other else -1),
                previous[column] - 1,
                current[-1] - 1,
            )
            current.append(score)
            best = max(best, score)
        previous = current
    return best / (2 * max(len(left), len(right)))


def pair_signals(
    amendment: TextChange, submission: TextChange, corpus: SignalCorpus
) -> dict[str, float]:
    """Features of same-operation edits; all are finite in [0, 1], with no fitted weights.

    Uses the existing lexical score and its exact changed spans. Rarity is weighted Dice
    on changed 3-5-grams, with unigram fallback for runs shorter than three tokens.
    Frequencies count training documents, not authors or the complete law corpus.
    Alignment is same-operation word Smith-Waterman (+2 match, -1 mismatch/gap). Short edits
    are retained and flagged, never discarded. Context cues describe possible conflicts,
    not entailment: an unflagged pair is not thereby semantically supported.

    TextChange bounds each side to 800 tokens. Token diff/alignment are O(T²) worst case;
    context comparisons are O(Ca * Cs * T), with Ca/Cs changed-clause counts. Memory O(T).
    """
    result = score_pair(ScoreRequest(amendment=amendment, submission=submission))
    left, right = _features(result.amendment_changes), _features(result.submission_changes)
    total = sum(
        count * corpus.idf(key[1]) for features in (left, right) for key, count in features.items()
    )
    matched = sum(min(count, right[key]) * corpus.idf(key[1]) for key, count in left.items())
    left_tokens: tuple[tuple[Operation, str], ...] = tuple(
        (span.operation, token) for span in result.amendment_changes for token in _tokens(span.text)
    )
    right_tokens: tuple[tuple[Operation, str], ...] = tuple(
        (span.operation, token)
        for span in result.submission_changes
        for token in _tokens(span.text)
    )
    size = len(left_tokens) + len(right_tokens)
    left_operations, right_operations = (
        Counter(op for op, _ in left_tokens),
        Counter(op for op, _ in right_tokens),
    )
    return {
        "lexical_overlap": result.score,
        "rare_phrase_overlap": float(
            any(len(key[1]) >= 3 and right[key] and corpus.idf(key[1]) > 1 for key in left)
        ),
        "rarity_overlap": min(1.0, 2 * matched / total) if total else 0.0,
        "alignment": _alignment(left_tokens, right_tokens),
        "operation_agreement": 2 * sum((left_operations & right_operations).values()) / size
        if size
        else 0.0,
        "short_edit": float(
            any(0 < length < _SHORT_EDIT_TOKENS for length in (len(left_tokens), len(right_tokens)))
        ),
        **_context_signals(
            _contexts(amendment, result.amendment_changes),
            _contexts(submission, result.submission_changes),
        ),
    }
