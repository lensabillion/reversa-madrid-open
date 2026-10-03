"""Law-local background and reciprocal ranks, independent of labels or publication.

These helpers operate on the complete candidate pool supplied for one law. Computing
backgrounds only from shortlisted winners would exaggerate distinctiveness; callers
must record pool coverage with the resulting signals.
"""

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class RankedPair:
    candidate_id: str
    amendment_id: str
    ask_id: str
    score: float


def background_signals(pairs: Sequence[RankedPair]) -> dict[str, dict[str, float]]:
    """O(N log N) sorting plus O(N) grouping for N pairs from one law.

    Ranks are competition ranks (ties receive equal rank), independently forward per
    amendment and reverse per ask. A constant-score pool has zero standardized distance.
    """
    if len({pair.candidate_id for pair in pairs}) != len(pairs):
        raise ValueError("Candidate IDs must be unique")
    if any(not math.isfinite(pair.score) for pair in pairs):
        raise ValueError("Background scores must be finite")
    if not pairs:
        return {}
    mean = math.fsum(pair.score for pair in pairs) / len(pairs)
    variance = math.fsum((pair.score - mean) ** 2 for pair in pairs) / len(pairs)
    deviation = math.sqrt(variance)
    forward: dict[str, list[RankedPair]] = {}
    reverse: dict[str, list[RankedPair]] = {}
    for pair in pairs:
        forward.setdefault(pair.amendment_id, []).append(pair)
        reverse.setdefault(pair.ask_id, []).append(pair)
    ranks: list[dict[str, int]] = []
    for groups in (forward, reverse):
        ranked: dict[str, int] = {}
        for group in groups.values():
            previous: float | None = None
            rank = 0
            for position, pair in enumerate(sorted(group, key=lambda row: -row.score), 1):
                if previous is None or pair.score != previous:
                    rank = position
                ranked[pair.candidate_id] = rank
                previous = pair.score
        ranks.append(ranked)
    return {
        pair.candidate_id: {
            "background_z": (pair.score - mean) / deviation if deviation else 0.0,
            "forward_reciprocal_rank": 1 / ranks[0][pair.candidate_id],
            "reverse_reciprocal_rank": 1 / ranks[1][pair.candidate_id],
            "mutual_reciprocal_rank": 2
            / (ranks[0][pair.candidate_id] + ranks[1][pair.candidate_id]),
        }
        for pair in pairs
    }


def reciprocal_rank_fusion(
    rankings: Sequence[Sequence[str]], *, limit: int, offset: int = 60
) -> tuple[tuple[str, float], ...]:
    """Fuse lexical/dense ranked IDs without letting repeated IDs add credit.

    O(N + U log U), N input ranking entries and U distinct candidates. This is the
    plan's sum(1/(60+rank)); ties resolve by stable candidate identifier.
    """
    if limit < 1 or offset < 0:
        raise ValueError("Need a positive limit and nonnegative rank offset")
    scores: dict[str, float] = {}
    for ranking in rankings:
        seen: set[str] = set()
        for identifier in ranking:
            if identifier in seen:
                continue
            seen.add(identifier)
            scores[identifier] = scores.get(identifier, 0.0) + 1 / (offset + len(seen))
    return tuple(sorted(scores.items(), key=lambda item: (-item[1], item[0]))[:limit])


def cosine(left: Sequence[float], right: Sequence[float]) -> float:
    """Finite cosine for recorded dense embeddings; zero vectors are missing evidence."""
    if not left or len(left) != len(right):
        raise ValueError("Embeddings need equal nonzero dimensions")
    if any(not math.isfinite(value) for value in (*left, *right)):
        raise ValueError("Embeddings must be finite")
    left_scale, right_scale = max(map(abs, left)), max(map(abs, right))
    if not left_scale or not right_scale:
        raise ValueError("A zero embedding cannot provide semantic evidence")
    # Scale before squaring to avoid overflow/underflow for finite input coordinates.
    unit_left = tuple(value / left_scale for value in left)
    unit_right = tuple(value / right_scale for value in right)
    denominator = math.hypot(*unit_left) * math.hypot(*unit_right)
    numerator = math.fsum(a * b for a, b in zip(unit_left, unit_right, strict=True))
    return max(-1.0, min(1.0, numerator / denominator))


def feature_vector(signals: Mapping[str, float], names: Sequence[str]) -> tuple[float, ...]:
    """Missing required signals are errors, never unreported zero-valued fallbacks."""
    if not names or len(set(names)) != len(names):
        raise ValueError("Feature names must be nonempty and unique")
    values = tuple(signals[name] for name in names)
    if any(not math.isfinite(value) for value in values):
        raise ValueError("Signals must be finite")
    return values
