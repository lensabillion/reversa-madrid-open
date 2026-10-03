"""Invented LobbyPlag-shaped records and labelled pairs for the practice-harness tests."""

from collections.abc import Sequence

from influence.practice.labels import LabelledPair, PracticePair
from influence.repositories.lobbyplag import RawText

type Records = dict[str, list[dict[str, object]]]


def practice_records(organizations: int = 6, per_organization: int = 12) -> Records:
    """Each organization has one document and `per_organization` labelled candidates.

    Even-numbered candidates are verified copies whose proposal repeats the amendment's edit;
    odd-numbered ones are crowd-rejected and propose a different edit. Every text is unique,
    so each organization is its own connected component. Two unlabelled candidates follow.
    """
    records: Records = {
        "amendments": [],
        "proposals": [],
        "plags": [],
        "documents": [],
        "lobbyists": [],
    }
    for org in range(organizations):
        records["lobbyists"].append({"id": f"org{org}", "title": f"Organization {org}"})
        records["documents"].append(
            {
                "uid": f"doc{org}",
                "filename": f"paper{org}.pdf",
                "lobbyist": f"org{org}",
                "lang": "en",
            }
        )
        for item in range(per_organization):
            key = f"{org}-{item}"
            old = f"Article {key} requires consent."
            new = f"Article {key} requires explicit consent within {item} days."
            copy = item % 2 == 0
            records["amendments"].append(
                {
                    "uid": f"a{key}",
                    "committee": "libe",
                    "number": org * 100 + item,
                    "authors": [],
                    "relations": [],
                    "text": [{"lang": "en", "old": old, "new": new}],
                }
            )
            records["proposals"].append(
                {
                    "uid": f"p{key}",
                    "doc_uid": f"doc{org}",
                    "page": "1",
                    "text": {"old": old, "new": new if copy else f"Article {key} is deleted."},
                }
            )
            records["plags"].append(
                {
                    "uid": f"c{key}",
                    "amendment": f"a{key}",
                    "proposal": f"p{key}",
                    "verified": copy,
                    "match": 0.9 if copy else 0.6,
                    "processing": {"checked": 0 if copy else 1, "verified": 0},
                }
            )
    for suffix, tallies in (("never", (0, 0)), ("support", (1, 1))):
        records["plags"].append(
            {
                "uid": f"u-{suffix}",
                "amendment": "a0-0",
                "proposal": f"p0-{1 if suffix == 'never' else 3}",
                "verified": False,
                "match": 0.5,
                "processing": {"checked": tallies[0], "verified": tallies[1]},
            }
        )
    return records


def labelled(
    organization: str, amendment: str, submission: str, influenced: bool, candidate: str
) -> LabelledPair:
    """A labelled pair whose texts are named by the given keys, for fold tests."""
    return LabelledPair(
        pair=PracticePair(
            candidate_id=candidate,
            amendment_id=f"amendment {amendment}",
            proposal_id=f"proposal {candidate}",
            organization_id=organization,
            amendment=RawText(old=f"law {amendment}", new=f"law {amendment} changed"),
            submission=RawText(old=f"law {submission}", new=f"law {submission} asked"),
        ),
        source="volunteer_verified" if influenced else "crowd_rejected",
        crowd_checks=0 if influenced else 1,
        crowd_yes_votes=0,
        document_language="en",
    )


def links_of(pairs: Sequence[LabelledPair], indices: Sequence[int]) -> set[tuple[str, str]]:
    """Organization, amendment and submission identities of the given pairs."""
    found: set[tuple[str, str]] = set()
    for index in indices:
        pair = pairs[index].pair
        found |= {
            ("organization", pair.organization_id),
            ("amendment", pair.amendment.new),
            ("submission", pair.submission.new),
        }
    return found
