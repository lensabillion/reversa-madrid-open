"""A deterministic English lexical baseline; never a probability of influence."""

from collections import Counter, defaultdict
from difflib import SequenceMatcher
from re import Match

from influence.schemas.scoring import (
    TOKEN_PATTERN,
    ChangeSpan,
    MatchEvidence,
    Operation,
    ScoreRequest,
    ScoreResult,
    TextChange,
    TextSpan,
)

type Feature = tuple[Operation, tuple[str, ...]]

_NEGATIONS = frozenset({"not", "no", "never", "without", "neither", "nor", "cannot"})
_LIMITATIONS = (
    "Lexical similarity is not a calibrated probability or proof of influence.",
    "English baseline: no translation, paraphrase model, rarity weighting, or legal reasoning.",
    "The negation check compares changed English cue counts only; "
    "it cannot infer meaning or scope.",
    "Case and whitespace are ignored; punctuation and numbers are retained. Diff alignment can be "
    "ambiguous with repeated wording. Shared deletions may reflect the same starting law.",
    "Offsets are Unicode code points, not UTF-16 indices. Overlapping unigram/bigram evidence "
    "represents separate scoring units; adjacent matches need not form a longer shared phrase.",
)


def _changes(change: TextChange) -> tuple[ChangeSpan, ...]:
    """Token diff is worst-case O(n*m), bounded to 800 tokens per side at validation."""
    old = tuple(TOKEN_PATTERN.finditer(change.old))
    new = tuple(TOKEN_PATTERN.finditer(change.new))
    matcher = SequenceMatcher(
        None,
        tuple(token.group().casefold() for token in old),
        tuple(token.group().casefold() for token in new),
        autojunk=False,
    )
    spans: list[ChangeSpan] = []
    for tag, old_start, old_end, new_start, new_end in matcher.get_opcodes():
        if tag == "equal":
            continue
        edits: tuple[tuple[Operation, tuple[Match[str], ...], int, int, str], ...] = (
            ("delete", old, old_start, old_end, change.old),
            ("insert", new, new_start, new_end, change.new),
        )
        for operation, tokens, start, end, text in edits:
            if start < end:
                left, right = tokens[start].start(), tokens[end - 1].end()
                spans.append(
                    ChangeSpan(operation=operation, start=left, end=right, text=text[left:right])
                )
    return tuple(spans)


def _features(changes: tuple[ChangeSpan, ...]) -> dict[Feature, list[TextSpan]]:
    features: dict[Feature, list[TextSpan]] = defaultdict(list)
    for change in changes:
        tokens = tuple(TOKEN_PATTERN.finditer(change.text))
        # No feature crosses a diff run: unchanged text cannot fabricate a shared phrase.
        for width in (1, 2):
            for index in range(len(tokens) - width + 1):
                window = tokens[index : index + width]
                left, right = window[0].start(), window[-1].end()
                key = (change.operation, tuple(token.group().casefold() for token in window))
                features[key].append(
                    TextSpan(
                        start=change.start + left,
                        end=change.start + right,
                        text=change.text[left:right],
                    )
                )
    return features


def _negations(features: dict[Feature, list[TextSpan]]) -> Counter[Feature]:
    return Counter(
        {
            key: len(spans)
            for key, spans in features.items()
            if len(key[1]) == 1 and key[1][0] in _NEGATIONS
        }
    )


def score_pair(request: ScoreRequest) -> ScoreResult:
    """Compare same-operation changed unigrams and within-run bigrams by multiset Dice.

    Every unit has equal weight: score = 2 * matched units / total units on both sides.
    No-change pairs score zero. A mismatch in changed English negation cues suppresses
    the score and evidence conservatively; this is a lexical guard, not semantic analysis.
    Symmetric scoring does not imply symmetric old/new diff alignment. Worst-case time
    is O(n*m) for each diff (800 tokens/side); feature matching is O(n+m) expected time.
    """
    amendment_changes = _changes(request.amendment)
    submission_changes = _changes(request.submission)
    amendment = _features(amendment_changes)
    submission = _features(submission_changes)
    negation_conflict = _negations(amendment) != _negations(submission)
    evidence: list[MatchEvidence] = []
    if not negation_conflict:
        for key, spans in amendment.items():
            evidence.extend(
                MatchEvidence(operation=key[0], amendment=left, submission=right)
                for left, right in zip(spans, submission.get(key, []), strict=False)
            )
    total = sum(map(len, amendment.values())) + sum(map(len, submission.values()))
    return ScoreResult(
        score=2 * len(evidence) / total if total else 0.0,
        amendment_changes=amendment_changes,
        submission_changes=submission_changes,
        evidence=tuple(evidence),
        negation_conflict=negation_conflict,
        limitations=_LIMITATIONS,
    )
