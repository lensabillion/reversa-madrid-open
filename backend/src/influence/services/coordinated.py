"""Part 3, coordinated amendments: near-identical wording tabled by different groups.

Two Members of different political groups who table the same forty new words on one law
probably did not write them separately. The wording points to a draft they both received,
so the cluster is a candidate whose source parts 3 and 4 then look for in the law's
submissions. It needs only the amendments and Members that part 1 read from Parltrack.

Only the wording an amendment inserts is compared. Two amendments to one paragraph share
most of the paragraph whatever they change, so comparing whole texts would cluster every
pair of edits to the same provision.
"""

from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from itertools import combinations
from pathlib import Path

from pydantic import ValidationError

from influence.extraction.files import write_bytes_atomic
from influence.extraction.layout import procedure_slug
from influence.schemas.atlas import Actor, Amendment, LawRecord, SourceSpan
from influence.schemas.coordinated import (
    ClusterMember,
    CoordinatedCluster,
    CoordinatedView,
    CoordinationCounts,
    CoordinationMethod,
)
from influence.schemas.scoring import TextChange
from influence.services.prose_match import words_of
from influence.services.scoring import changed_spans
from influence.services.tabling_groups import group_limitations, known_groups, latest_groups

METHOD: CoordinationMethod = "shingle-jaccard-1"
VIEW_FILE = "coordinated.json"
# Proposed, not calibrated: no labelled set of coordinated amendments exists. The pull
# request that added them reports how the cluster counts move on two real laws.
# Below this many inserted words an identical edit ("shall" to "may", a deleted comma) is
# what any two Members would write on their own.
MIN_INSERTED_WORDS = 12
SHINGLE_WORDS = 5
SIMILARITY_THRESHOLD = 0.8
LIMITATIONS = (
    "Near-identical wording tabled by Members of different groups is consistent with a "
    "shared outside draft. It does not show who wrote the draft, and Members also agree "
    "wording among themselves.",
    f"Only inserted wording of at least {MIN_INSERTED_WORDS} words is compared: identical "
    "deletions and short edits are not clustered.",
    f"Two amendments are joined when their inserted wording shares at least "
    f"{SIMILARITY_THRESHOLD:.0%} of its {SHINGLE_WORDS}-word runs, and a cluster follows "
    "chains of such pairs, so its least similar pair can fall below that share. Both "
    "numbers are proposed, not calibrated.",
)

type Shingle = tuple[str, ...]


class CoordinationError(RuntimeError):
    """A law's `coordinated.json` is on disk and does not fit `CoordinatedView`."""


@dataclass(frozen=True, slots=True)
class _Change:
    amendment: Amendment
    inserted: tuple[SourceSpan, ...]
    words: int
    shingles: frozenset[Shingle]


def _change(amendment: Amendment) -> _Change:
    """The wording the amendment inserts; ValueError when it is over the diff's bounds.

    An unknown original is read as an empty one, as part 4 does: the whole proposed text is
    then the insertion. Words are joined across the diff's runs, so the same scattered
    edits to one paragraph match as one sequence.
    """
    spans = changed_spans(TextChange(old=amendment.old_text or "", new=amendment.new_text))
    inserted = tuple(
        SourceSpan(
            record_id=amendment.amendment_id,
            field="new_text",
            start=span.start,
            end=span.end,
            text=span.text,
        )
        for span in spans
        if span.operation == "insert"
    )
    words = [word.text for span in inserted for word in words_of(span.text)]
    return _Change(
        amendment=amendment,
        inserted=inserted,
        words=len(words),
        shingles=frozenset(
            tuple(words[first : first + SHINGLE_WORDS])
            for first in range(len(words) - SHINGLE_WORDS + 1)
        ),
    )


def _similarity(left: _Change, right: _Change) -> float:
    shared = len(left.shingles & right.shingles)
    return shared / (len(left.shingles) + len(right.shingles) - shared)


def _components(changes: Sequence[_Change]) -> list[list[int]]:
    """Indices of `changes` grouped by chains of pairs at or over the threshold.

    Pairs are found through an inverted index, so two amendments with no run in common are
    never compared. The cost is the sum, over distinct runs, of the square of the number
    of amendments holding that run: 48,028 pairs for the AI Act's 5,660 amendments.
    """
    holders: defaultdict[Shingle, list[int]] = defaultdict(list)
    for index, change in enumerate(changes):
        for shingle in change.shingles:
            holders[shingle].append(index)
    shared: Counter[tuple[int, int]] = Counter()
    for indices in holders.values():
        shared.update(combinations(indices, 2))
    parent = list(range(len(changes)))

    def root(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    for (left, right), count in shared.items():
        union = len(changes[left].shingles) + len(changes[right].shingles) - count
        if count / union >= SIMILARITY_THRESHOLD:
            parent[root(left)] = root(right)
    groups: defaultdict[int, list[int]] = defaultdict(list)
    for index in range(len(changes)):
        groups[root(index)].append(index)
    return [group for group in groups.values() if len(group) > 1]


def _spans_groups(members: Sequence[ClusterMember]) -> bool:
    """Two members with no author and no group in common, both with a known group.

    One amendment co-signed across groups is open cooperation, and one Member tabling the
    same text in two committees is one author: neither counts.
    """
    return any(
        left.political_groups
        and right.political_groups
        and set(left.author_ids).isdisjoint(right.author_ids)
        and set(left.political_groups).isdisjoint(right.political_groups)
        for left, right in combinations(members, 2)
    )


def _cluster(changes: Sequence[_Change], latest: dict[str, str]) -> CoordinatedCluster:
    ordered = sorted(
        changes,
        key=lambda change: (change.amendment.tabled_on or date.max, change.amendment.amendment_id),
    )
    members = tuple(
        ClusterMember(
            amendment_id=change.amendment.amendment_id,
            stage=change.amendment.stage,
            committee=change.amendment.committee,
            tabled_on=change.amendment.tabled_on,
            target_provision=change.amendment.target_provision,
            author_ids=change.amendment.author_ids,
            author_names=change.amendment.author_names,
            political_groups=tuple(sorted(known_groups(change.amendment, latest))),
            inserted=change.inserted,
        )
        for change in ordered
    )
    return CoordinatedCluster(
        cluster_id=f"coord:{members[0].amendment_id.removeprefix('am:')}",
        members=members,
        political_groups=tuple(sorted({g for member in members for g in member.political_groups})),
        cross_group=_spans_groups(members),
        inserted_words=min(change.words for change in changes),
        min_similarity=min(_similarity(left, right) for left, right in combinations(changes, 2)),
    )


def find_coordinated(
    amendments: Iterable[Amendment], actors: Iterable[Actor]
) -> tuple[tuple[CoordinatedCluster, ...], CoordinationCounts]:
    """Cluster one law's amendments by near-identical inserted wording.

    The result does not depend on the order of `amendments`. Each diff is O(n*m) in the
    two sides' tokens, bounded at 800 a side; pairing is described in `_components`.
    Measured on the AI Act (5,660 amendments) and the Digital Services Act (6,476): under
    one second each.
    """
    latest = latest_groups(actors)
    compared: list[_Change] = []
    counts: Counter[str] = Counter()
    for amendment in sorted(amendments, key=lambda amendment: amendment.amendment_id):
        counts["amendments"] += 1
        try:
            change = _change(amendment)
        except ValueError:
            counts["not_comparable"] += 1
            continue
        if change.words < MIN_INSERTED_WORDS:
            counts["too_short"] += 1
            continue
        compared.append(change)
    clusters = (
        _cluster([compared[index] for index in component], latest)
        for component in _components(compared)
    )
    return (
        tuple(
            sorted(
                clusters,
                key=lambda cluster: (
                    not cluster.cross_group,
                    -len(cluster.political_groups),
                    -len(cluster.members),
                    cluster.cluster_id,
                ),
            )
        ),
        CoordinationCounts(
            amendments=counts["amendments"],
            compared=len(compared),
            too_short=counts["too_short"],
            not_comparable=counts["not_comparable"],
        ),
    )


def build_coordination(
    law: LawRecord,
    run_id: str,
    amendments: Iterable[Amendment],
    actors: Iterable[Actor],
    *,
    generated_at: datetime,
) -> CoordinatedView:
    amendments = tuple(amendments)
    clusters, counts = find_coordinated(amendments, actors)
    return CoordinatedView(
        procedure_id=law.procedure_id,
        slug=procedure_slug(law.procedure_id),
        title=law.title,
        run_id=run_id,
        generated_at=generated_at,
        method=METHOD,
        min_inserted_words=MIN_INSERTED_WORDS,
        shingle_words=SHINGLE_WORDS,
        similarity_threshold=SIMILARITY_THRESHOLD,
        counts=counts,
        clusters=clusters,
        limitations=(*LIMITATIONS, *group_limitations(amendments)),
    )


def write_coordination(view: CoordinatedView, bundle: Path) -> Path:
    path = bundle / VIEW_FILE
    write_bytes_atomic(path, view.model_dump_json().encode("utf-8"))
    return path


def read_coordination(data_root: Path, slug: str) -> CoordinatedView | None:
    """The law's last written clusters, or None when that law has none.

    A file that does not validate raises: serving it as "no clusters" would hide a broken
    run behind an answer that reads as a finding.
    """
    path = data_root / "laws" / slug / VIEW_FILE
    if not path.is_file():
        return None
    try:
        return CoordinatedView.model_validate_json(path.read_bytes())
    except ValidationError as error:
        raise CoordinationError(f"The clusters at {path} are invalid: {error}") from error


def cross_group_clusters(data_root: Path, slug: str) -> int | None:
    """How many of the law's clusters span political groups; None when none were built.

    None is "not computed", which the law list keeps apart from a computed zero.
    """
    view = read_coordination(data_root, slug)
    return None if view is None else sum(cluster.cross_group for cluster in view.clusters)
