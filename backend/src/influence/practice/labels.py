"""Turn LobbyPlag's historical records into labelled practice pairs, with provenance.

Labels come only from LobbyPlag's public records; nobody labels a pair by hand (explainer
§11, "No hand labelling, anywhere"). Each candidate is a pair LobbyPlag's own matcher
proposed, so every label below describes a lookalike that matcher already found:

| `verified` | crowd checks | crowd yes votes | Outcome |
| --- | --- | --- | --- |
| true | any | any | positive: a volunteer verified the copy |
| false | > 0 | 0 | weak negative: crowd-checked, never voted a copy |
| false | 0 | 0 | unlabelled: never checked |
| false | > 0 | > 0 | unlabelled: some crowd support, never verified |

Weak negatives are weaker evidence than the positives: most rest on one crowd check, and
LobbyPlag never marked any of them `checked` (review finding R1). Unlabelled pairs are not
negatives, and no negative is invented, for example from same-article pairs (R2).
The unit is one amendment-proposal pair compared as clean edits: both old and new wording.
"""

from collections import Counter, defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from influence.repositories.lobbyplag import DemoRepository, RawCandidate, RawText

type LabelSource = Literal["volunteer_verified", "crowd_rejected"]
type TextKey = tuple[str, str]


class PracticeDataError(Exception):
    """The labelled data cannot support the requested folds or simulated tests."""


@dataclass(frozen=True, slots=True)
class PracticePair:
    """What a scorer may read: identities and texts, never a label or LobbyPlag's own score."""

    candidate_id: str
    amendment_id: str
    proposal_id: str
    organization_id: str
    amendment: RawText
    submission: RawText


@dataclass(frozen=True, slots=True)
class LabelledPair:
    pair: PracticePair
    source: LabelSource
    crowd_checks: int
    crowd_yes_votes: int
    # LobbyPlag's document metadata; some documents marked "de" hold English proposals.
    document_language: str

    @property
    def influenced(self) -> bool:
        return self.source == "volunteer_verified"


@dataclass(frozen=True, slots=True)
class IdenticalInputs:
    """Groups of two or more labelled pairs whose texts a scorer cannot tell apart."""

    groups: int
    pairs: int
    conflicting_groups: int


@dataclass(frozen=True, slots=True)
class PracticeSet:
    pairs: tuple[LabelledPair, ...]
    outcomes: Mapping[str, int]
    excluded: Mapping[str, int]
    identical_inputs: IdenticalInputs


def label_source(candidate: RawCandidate) -> LabelSource | None:
    if candidate.verified:
        return "volunteer_verified"
    if candidate.processing.checked > 0 and candidate.processing.verified == 0:
        return "crowd_rejected"
    return None


def text_key(text: RawText) -> TextKey:
    """Case and spacing differences are the same evidence, so they never separate duplicates."""
    return " ".join(text.old.casefold().split()), " ".join(text.new.casefold().split())


def input_key(pair: PracticePair) -> tuple[TextKey, TextKey]:
    return text_key(pair.amendment), text_key(pair.submission)


def build_practice_set(repository: DemoRepository) -> PracticeSet:
    """Label every candidate, ordered by identifier so runs are reproducible.

    Identical inputs with opposite labels are excluded from the metrics: no scorer can rank
    one above the other, and at least one label must be wrong for that input. Identical
    inputs with the same label stay, as separate historical pairs; the folds keep them
    together. O(C log C) for C candidates (1,957 in the public snapshot).
    """
    outcomes: Counter[str] = Counter()
    labelled: list[LabelledPair] = []
    no_english = 0
    for candidate in sorted(repository.candidates.values(), key=lambda row: row.uid):
        source = label_source(candidate)
        if source is None:
            never_checked = candidate.processing.checked == 0
            outcomes[
                "unlabelled_never_checked" if never_checked else "unlabelled_crowd_support"
            ] += 1
            continue
        outcomes[source] += 1
        amendment = repository.amendments[candidate.amendment].text_in("en")
        if amendment is None:
            no_english += 1
            continue
        proposal = repository.proposals[candidate.proposal]
        labelled.append(
            LabelledPair(
                pair=PracticePair(
                    candidate_id=candidate.uid,
                    amendment_id=candidate.amendment,
                    proposal_id=candidate.proposal,
                    organization_id=repository.organization_for(proposal).id,
                    amendment=amendment,
                    submission=proposal.text,
                ),
                source=source,
                crowd_checks=candidate.processing.checked,
                crowd_yes_votes=candidate.processing.verified,
                document_language=repository.documents[proposal.doc_uid].lang,
            )
        )
    groups: defaultdict[tuple[TextKey, TextKey], list[LabelledPair]] = defaultdict(list)
    for item in labelled:
        groups[input_key(item.pair)].append(item)
    repeated = [members for members in groups.values() if len(members) > 1]
    conflicting = [members for members in repeated if len({m.influenced for m in members}) > 1]
    excluded = {member.pair.candidate_id for members in conflicting for member in members}
    return PracticeSet(
        pairs=tuple(item for item in labelled if item.pair.candidate_id not in excluded),
        outcomes={
            name: outcomes[name]
            for name in (
                "volunteer_verified",
                "crowd_rejected",
                "unlabelled_never_checked",
                "unlabelled_crowd_support",
            )
        },
        excluded={
            "no_english_amendment_text": no_english,
            "conflicting_identical_input": len(excluded),
        },
        identical_inputs=IdenticalInputs(
            groups=len(repeated),
            pairs=sum(map(len, repeated)),
            conflicting_groups=len(conflicting),
        ),
    )
