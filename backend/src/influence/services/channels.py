"""Part 7's HOW: by which channels one law was lobbied, counted from part 1's records alone.

The question "how do they win" has a descriptive half that needs no link at all: which
consultation stage organisations wrote to, whether they wrote before or after the
proposal, which Members tabled amendments and with whom, and which coordinated wording
crossed groups. These counts come straight from the collected bundle, so they can be shown
for any law the jury names, before any link is verified. Votes and meetings are reported as
the coverage rows part 1 wrote for them, never as counts nobody collected.

Every function here is linear in the records it reads, except the ranked breakdowns, which
sort their distinct keys (O(k log k), k at most a few thousand Members or categories), and
the coordinated clusters, whose cost `find_coordinated` states.
"""

import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from datetime import date, datetime
from pathlib import Path

from influence.extraction.files import write_bytes_atomic
from influence.extraction.layout import procedure_slug
from influence.repositories.hys import IndexEntry
from influence.schemas.atlas import (
    Actor,
    Amendment,
    LawRecord,
    LayerCoverage,
    Passage,
    SourceDocument,
)
from influence.schemas.channels import (
    ChannelsMethod,
    ChannelsView,
    CoalitionChannel,
    ConsultationChannel,
    DateSplit,
    KeyCount,
    MepChannel,
    PublicationFeedback,
    SubmitterGroup,
    TablingMep,
    TimingChannel,
)
from influence.services.coordinated import find_coordinated

METHOD: ChannelsMethod = "channels-1"
VIEW_FILE = "channels.json"
TOP_MEPS = 20
UNKNOWN = "unknown"
INDEX_GAP = (
    "The Have Your Say index is not built (run `make setup`), so the stage each "
    "publication belongs to is unknown"
)
_PUBLICATION = re.compile(r"[?&]publicationId=(\d+)")
LIMITATIONS = (
    "Every count describes the collected record: a channel is associated with the law, "
    "which does not show that it changed the law.",
    "Feedback is grouped by the Have Your Say publication its URL names; the publication's "
    "type is the source's own code from the Have Your Say index.",
    "All private citizens are one aggregate submitter, so they count once among submitters "
    "however much feedback they sent.",
    "A Member's political group is the one of their latest spell in Parltrack's dump, which "
    "can differ from their group on the day the amendment was tabled.",
    "An amendment co-signed by Members of several groups counts once for each group, so the "
    "group counts can sum to more than the amendments with a known group.",
    "Organisations whose submissions share wording are not counted: comparing every pair of "
    "submissions is not cheap enough for a live run.",
    "Votes and meetings are not collected yet; their coverage rows say so and no count is "
    "shown for them.",
)


def _ranked(counts: Counter[str]) -> tuple[KeyCount, ...]:
    """Most first, then by key, so the order is the same on every run."""
    return tuple(
        KeyCount(key=key, count=count)
        for key, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    )


def split_dates(dates: Iterable[date | None], reference: date | None) -> DateSplit:
    """Place each date before, or on or after, `reference`; unknown dates are counted apart."""
    counts: Counter[str] = Counter()
    for day in dates:
        counts["total"] += 1
        if day is None:
            counts["undated"] += 1
        elif reference is None:
            counts["unplaced"] += 1
        elif day < reference:
            counts["before"] += 1
        else:
            counts["on_or_after"] += 1
    return DateSplit(
        reference_date=reference,
        total=counts["total"],
        before=counts["before"],
        on_or_after=counts["on_or_after"],
        undated=counts["undated"],
        unplaced=counts["unplaced"],
    )


def publication_types(index: Iterable[IndexEntry]) -> dict[int, str]:
    """Each publication's type code from the Have Your Say index, where the index states it."""
    return {
        publication.publication_id: publication.type
        for entry in index
        for publication in entry.publications
        if publication.type is not None
    }


def _publication_of(document: SourceDocument) -> int | None:
    found = _PUBLICATION.search(document.url)
    return None if found is None else int(found.group(1))


def _submitters(
    documents: Iterable[SourceDocument], passages: Iterable[Passage], actors: Iterable[Actor]
) -> dict[str, str]:
    """Document ID to the actor who submitted it: from passages, else from actor aliases.

    A feedback with no text has no passage, but the actor resolver still recorded which
    document it named the actor in.
    """
    wanted = {document.document_id for document in documents}
    found = {
        alias.document_id: actor.actor_id
        for actor in actors
        for alias in actor.aliases
        if alias.document_id in wanted
    }
    found.update(
        (passage.document_id, passage.actor_id)
        for passage in passages
        if passage.document_id in wanted
    )
    return found


def _groups(feedback: Mapping[str, str], key: Mapping[str, str]) -> tuple[SubmitterGroup, ...]:
    """Feedback and distinct submitters per key; `feedback` maps document to actor ID."""
    items: Counter[str] = Counter()
    submitters: defaultdict[str, set[str]] = defaultdict(set)
    for actor_id in feedback.values():
        items[key[actor_id]] += 1
        submitters[key[actor_id]].add(actor_id)
    return tuple(
        SubmitterGroup(key=name, feedback=count, submitters=len(submitters[name]))
        for name, count in sorted(items.items(), key=lambda item: (-item[1], item[0]))
    )


def _publication_type_gap(
    publications: Iterable[int | None], types: Mapping[int, str] | None
) -> str | None:
    known = sorted(publication for publication in publications if publication is not None)
    if not known:
        return None
    if types is None:
        return INDEX_GAP
    unlisted = [str(publication) for publication in known if publication not in types]
    if not unlisted:
        return None
    return f"The Have Your Say index states no type for publication {', '.join(unlisted)}"


def consultation_channel(
    documents: Iterable[SourceDocument],
    passages: Iterable[Passage],
    actors: Iterable[Actor],
    types: Mapping[int, str] | None,
) -> ConsultationChannel:
    """Feedback by consultation stage and by who sent it; `types` None: no index is built."""
    documents = tuple(documents)
    actors = tuple(actors)
    feedback = sorted(
        (document for document in documents if document.source_kind == "hys_feedback"),
        key=lambda document: document.document_id,
    )
    by_publication: defaultdict[int | None, list[date | None]] = defaultdict(list)
    for document in feedback:
        published = document.published_at
        by_publication[_publication_of(document)].append(
            None if published is None else published.date()
        )
    publications = tuple(
        PublicationFeedback(
            publication_id=publication,
            publication_type=None
            if types is None or publication is None
            else types.get(publication),
            feedback=len(dates),
            earliest=min((day for day in dates if day is not None), default=None),
            latest=max((day for day in dates if day is not None), default=None),
        )
        for publication, dates in sorted(
            by_publication.items(), key=lambda item: (item[0] is None, item[0] or 0)
        )
    )
    submitted = _submitters(feedback, passages, actors)
    by_id = {actor.actor_id: actor for actor in actors}
    kind = {
        actor_id: by_id[actor_id].kind if actor_id in by_id else UNKNOWN
        for actor_id in submitted.values()
    }
    category = {
        actor_id: (by_id[actor_id].category if actor_id in by_id else None) or UNKNOWN
        for actor_id in submitted.values()
    }
    organisations = [
        by_id[actor_id]
        for actor_id in set(submitted.values())
        if actor_id in by_id and by_id[actor_id].kind == "organisation"
    ]
    return ConsultationChannel(
        feedback=len(feedback),
        attachments=sum(document.source_kind == "hys_attachment" for document in documents),
        by_publication=publications,
        publication_type_gap=_publication_type_gap(by_publication, types),
        feedback_without_submitter=len(feedback) - len(submitted),
        submitters=len(set(submitted.values())),
        by_actor_kind=_groups(submitted, kind),
        by_register_category=_groups(submitted, category),
        organisations=len(organisations),
        organisations_with_register_id=sum(
            actor.register_id is not None for actor in organisations
        ),
    )


def _author_groups(amendment: Amendment, groups: Mapping[str, str]) -> set[str]:
    return {groups[author] for author in amendment.author_ids if author in groups}


def _political_groups(actors: Iterable[Actor]) -> dict[str, str]:
    return {
        actor.actor_id: actor.political_group
        for actor in actors
        if actor.political_group is not None
    }


def mep_channel(amendments: Iterable[Amendment], actors: Iterable[Actor]) -> MepChannel:
    """Amendments by stage, committee and group, and the Members who tabled the most.

    A Member absent from the MEP dump is named as the amendment names them.
    """
    actors = tuple(actors)
    groups = _political_groups(actors)
    names = {actor.actor_id: actor.name for actor in actors}
    counts: Counter[str] = Counter()
    stages: Counter[str] = Counter()
    committees: Counter[str] = Counter()
    by_group: Counter[str] = Counter()
    tabled: Counter[str] = Counter()
    for amendment in amendments:
        counts["amendments"] += 1
        stages[amendment.stage] += 1
        committees[amendment.committee or UNKNOWN] += 1
        authors = set(amendment.author_ids)
        if len(amendment.author_names) == len(amendment.author_ids):
            for author, name in zip(amendment.author_ids, amendment.author_names, strict=True):
                names.setdefault(author, name or author)
        tabled.update(authors)
        known = _author_groups(amendment, groups)
        by_group.update(known)
        if not authors:
            counts["no_known_author"] += 1
        elif known:
            counts["with_known_group"] += 1
        else:
            counts["group_unknown"] += 1
    top = sorted(tabled.items(), key=lambda item: (-item[1], item[0]))[:TOP_MEPS]
    return MepChannel(
        amendments=counts["amendments"],
        by_stage=_ranked(stages),
        by_committee=_ranked(committees),
        by_political_group=_ranked(by_group),
        with_known_group=counts["with_known_group"],
        group_unknown=counts["group_unknown"],
        no_known_author=counts["no_known_author"],
        tabling_meps=len(tabled),
        top_meps=tuple(
            TablingMep(
                actor_id=actor_id,
                name=names.get(actor_id, actor_id),
                political_group=groups.get(actor_id),
                amendments=count,
            )
            for actor_id, count in top
        ),
    )


def coalition_channel(amendments: Iterable[Amendment], actors: Iterable[Actor]) -> CoalitionChannel:
    """Open co-signing across groups, and part 3's coordinated wording across groups."""
    amendments = tuple(amendments)
    actors = tuple(actors)
    groups = _political_groups(actors)
    clusters, counts = find_coordinated(amendments, actors)
    crossing = [cluster for cluster in clusters if cluster.cross_group]
    return CoalitionChannel(
        amendments=len(amendments),
        cosigned=sum(len(set(amendment.author_ids)) > 1 for amendment in amendments),
        cosigned_across_groups=sum(
            len(_author_groups(amendment, groups)) > 1 for amendment in amendments
        ),
        coordinated=counts,
        coordinated_clusters=len(clusters),
        cross_group_clusters=len(crossing),
        amendments_in_cross_group_clusters=sum(len(cluster.members) for cluster in crossing),
    )


def _coverage(law: LawRecord) -> tuple[LayerCoverage, ...]:
    return tuple(item for item in law.coverage if item.layer in {"votes", "meetings"})


def build_channels(
    law: LawRecord,
    run_id: str,
    *,
    documents: Iterable[SourceDocument],
    passages: Iterable[Passage],
    actors: Iterable[Actor],
    amendments: Iterable[Amendment],
    types: Mapping[int, str] | None,
    generated_at: datetime,
) -> ChannelsView:
    documents = tuple(documents)
    actors = tuple(actors)
    amendments = tuple(amendments)
    feedback_dates = (
        None if document.published_at is None else document.published_at.date()
        for document in documents
        if document.source_kind == "hys_feedback"
    )
    tabled = [amendment.tabled_on for amendment in amendments]
    return ChannelsView(
        procedure_id=law.procedure_id,
        slug=procedure_slug(law.procedure_id),
        title=law.title,
        run_id=run_id,
        generated_at=generated_at,
        method=METHOD,
        consultation=consultation_channel(documents, passages, actors, types),
        timing=TimingChannel(
            feedback_vs_proposal=split_dates(feedback_dates, law.proposed_on),
            amendments_vs_proposal=split_dates(tabled, law.proposed_on),
            amendments_vs_completion=split_dates(tabled, law.completed_on),
        ),
        meps=mep_channel(amendments, actors),
        coalitions=coalition_channel(amendments, actors),
        votes_and_meetings=_coverage(law),
        limitations=LIMITATIONS,
    )


def write_channels(view: ChannelsView, bundle: Path) -> Path:
    path = bundle / VIEW_FILE
    write_bytes_atomic(path, view.model_dump_json().encode("utf-8"))
    return path
