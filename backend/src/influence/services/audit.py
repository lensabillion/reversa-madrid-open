"""Blind audit of published links: a seeded sample, two readers, a Wilson interval.

The audit measures how often the links we publish are right, so labels live apart from the
pipeline's output and nothing here changes a link, a score or a threshold. The sample is
spread over (procedure, tier) in proportion to how many links each holds, so a large law or
tier cannot hide a weak one, and it is a pure function of the links and the seed, so a
reader can redraw it. `summarise` counts a link only when both readers agree; a link they
split on is reported as unresolved, never decided for them. Linear in the number of links.
"""

import random
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from math import sqrt
from typing import Literal

from influence.schemas.atlas import LinkAssessment

type Verdict = Literal["correct", "incorrect"]
Z_95 = 1.959963984540054


class AuditError(Exception):
    """The labels do not describe the sample they claim to audit."""


@dataclass(frozen=True, slots=True)
class AuditReport:
    """Precision of the published links, with the uncertainty a small sample leaves."""

    sampled: int
    resolved: int
    correct: int
    unresolved: int
    unlabelled: int
    precision: float | None
    low: float
    high: float
    by_tier: Mapping[str, tuple[int, int]]


def wilson_interval(correct: int, total: int, z: float = Z_95) -> tuple[float, float]:
    """Wilson score interval for a proportion. With no trials nothing is known: (0, 1).

    Unlike the plain normal interval it stays inside [0, 1] and is honest at small n and at
    proportions near 0 or 1: 30 of 30 correct bounds precision at about 0.886 from below.
    """
    if total <= 0:
        return 0.0, 1.0
    p = correct / total
    scale = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / scale
    half = z * sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / scale
    # The formula is exact at the endpoints but floating point leaves a speck; pin them so the
    # interval always holds the estimate.
    low = 0.0 if correct == 0 else max(0.0, centre - half)
    high = 1.0 if correct == total else min(1.0, centre + half)
    return low, high


def draw_sample(
    links: Sequence[LinkAssessment], size: int, seed: int
) -> tuple[LinkAssessment, ...]:
    """Draw `size` published links, spread over (procedure, tier) in proportion to its size.

    Seats go by largest remainder, so the sample has exactly `size` links unless fewer are
    published, in which case every published link is returned. Never samples a link that is
    not published. O(n log n) in the number of published links.
    """
    published = sorted(
        (link for link in links if link.status == "published"), key=lambda link: link.link_id
    )
    if size >= len(published):
        return tuple(published)
    strata: dict[tuple[str, str], list[LinkAssessment]] = defaultdict(list)
    for link in published:
        strata[(link.procedure_id, link.tier or "")].append(link)
    exact = {key: size * len(members) / len(published) for key, members in strata.items()}
    seats = {key: int(value) for key, value in exact.items()}
    spare = size - sum(seats.values())
    for key in sorted(exact, key=lambda item: (exact[item] - seats[item], item), reverse=True)[
        :spare
    ]:
        seats[key] += 1
    # Deliberate: a seeded, reproducible draw is the requirement; nothing here is secret.
    rng = random.Random(seed)  # noqa: S311
    chosen = [link for key in sorted(strata) for link in rng.sample(strata[key], seats[key])]
    return tuple(sorted(chosen, key=lambda link: link.link_id))


def summarise(
    sample: Sequence[LinkAssessment],
    labels: Mapping[str, Mapping[str, Verdict]],
) -> AuditReport:
    """Precision among links both readers agree on, with its Wilson interval.

    `labels` maps a link ID to each reader's verdict. A link outside the sample is an error
    (it would let a label audit something we did not draw); a sampled link with fewer than
    two readers is unlabelled, and one the readers split on is unresolved. Neither counts
    toward precision, and both are reported so a thin audit cannot look complete.
    """
    in_sample = {link.link_id: link for link in sample}
    stray = sorted(set(labels) - set(in_sample))
    if stray:
        raise AuditError(f"Labels for links outside the sample: {stray}")
    correct = resolved = unresolved = unlabelled = 0
    tiers: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for link_id, link in in_sample.items():
        verdicts = set(labels.get(link_id, {}).values())
        if len(labels.get(link_id, {})) < 2:
            unlabelled += 1
        elif len(verdicts) > 1:
            unresolved += 1
        else:
            resolved += 1
            right = verdicts == {"correct"}
            correct += right
            tier = tiers[link.tier or ""]
            tier[0] += right
            tier[1] += 1
    low, high = wilson_interval(correct, resolved)
    return AuditReport(
        sampled=len(in_sample),
        resolved=resolved,
        correct=correct,
        unresolved=unresolved,
        unlabelled=unlabelled,
        precision=correct / resolved if resolved else None,
        low=low,
        high=high,
        by_tier={tier: (counts[0], counts[1]) for tier, counts in sorted(tiers.items())},
    )
