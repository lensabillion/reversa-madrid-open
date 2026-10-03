"""Part 7, TOWARDS: which way each amendment moves the law, read from the wording it changes.

The rules are transparent cue lists over English legal wording, so a juror can check any
label against the quoted span that decided it. They read the edit, never the actor: an
organisation whose asks echo "weaker" amendments is not thereby shown to want weaker law.

Rules, in precedence order (the first that fires decides):

1. delete: the new wording is empty or Parltrack's "deleted" marker, or the edit inserts
   nothing and removes at least half of the original wording.
2. unknown (`original_unknown`): Parltrack did not give the original wording, so the edit
   cannot be read. An over-long text the diff refuses is unknown too (`over_long`).
3. keep: the two sides hold the same words (case, spacing and punctuation aside).
4. exempt: an exemption phrase occurs more often after the edit than before ("shall not
   apply", "exempt", "exemption", "derogation", "excluding", "with the exception of",
   "except"). Inserting "not" into "shall apply" is therefore exempt, not stricter.
5. delay: a postponement phrase is added ("postpone", "defer", "transitional period",
   "grace period"), or the edit replaces a year or a time period with a later or longer one
   ("2025" to "2027", "six months" to "24 months"). Adding a period where none was replaced
   ("within six months after") is a new deadline, not a delay, and is not counted here.
6. stricter or weaker: obligation cues added minus those removed. Stricter cues are
   "shall", "must", "required", "at least", "minimum", "prohibit", "ban" and "may not";
   weaker cues are "may", "can" and "optional". Removing a weaker cue or an exemption
   counts as stricter, removing a stricter cue as weaker. A tie falls through.
7. add: the edit only inserts wording. 8. other: anything else.

Part 4 keeps its own narrower `assessment.amendment_direction` (shall/must against may) for
its same-direction signal: changing that would change published scores, which needs
practice-loop evidence first. The cue lists here are phrase-aware versions of its sets.
"""

import re
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

from influence.extraction.files import write_bytes_atomic
from influence.extraction.layout import procedure_slug
from influence.schemas.atlas import Actor, Amendment, Direction, LawRecord, LinkId, SourceSpan
from influence.schemas.atlas_view import AtlasView
from influence.schemas.directions import (
    ActorDirections,
    ActorsStatus,
    DirectionCounts,
    DirectionExample,
    DirectionMethod,
    DirectionsView,
    GroupDirections,
    MemberDirections,
    StageDirections,
    UnknownReasons,
)
from influence.schemas.scoring import ChangeSpan, TextChange
from influence.services.pipeline import PipelineError
from influence.services.scoring import changed_spans

METHOD: DirectionMethod = "direction-rules-1"
VIEW_FILE = "directions.json"
TOP_MEMBERS = 20
# The order examples are listed in, which is also the rules' precedence.
PRECEDENCE: tuple[Direction, ...] = (
    "delete",
    "unknown",
    "keep",
    "exempt",
    "delay",
    "stricter",
    "weaker",
    "add",
    "other",
)
DELETION_MARKERS = frozenset({"", "deleted", "(deleted)"})
MOSTLY_DELETED = 0.5
LIMITATIONS = (
    "Directions come from fixed English cue words in the changed wording, not from reading "
    "the provision: an edit with no cue is 'other', and a cue can mislead (a 'shall' added "
    "to grant a right reads as stricter).",
    "Only English wording is read; amendments in another language come back 'other' or "
    "'add' unless they quote English cue words.",
    "A direction describes an amendment, not the stance of whoever tabled or asked for it.",
    "Counts are not causes: an actor's directions are those of the amendments its asks are "
    "published as linked to, one count per published link, and unconfirmed or contradicted "
    "links are never used.",
    "A Member's political group is the one of their latest spell in Parltrack's dump; an "
    "amendment co-signed across groups counts once in each group.",
)

type SideField = Literal["old_text", "new_text"]
type UnknownReason = Literal["over_long", "original_unknown"]
# Which side of the amendment the quote is in, and its code-point offsets there.
type Evidence = tuple[SideField, int, int]


@dataclass(frozen=True, slots=True)
class Reading:
    direction: Direction
    evidence: Evidence | None = None
    unknown_reason: UnknownReason | None = None


def _cues(*phrases: str) -> re.Pattern[str]:
    """Whole-word alternatives; a space in a phrase matches any run of whitespace."""
    joined = "|".join(phrase.replace(" ", r"\s+") for phrase in phrases)
    return re.compile(rf"\b(?:{joined})\b", re.IGNORECASE)


_EXEMPT = _cues(
    "(?:shall|does|do|will) not apply",
    r"exempt\w*",
    r"derogat\w*",
    "excluding",
    "with the exception of",
    "except",
)
_DELAY = _cues(r"postpon\w*", r"defer\w*", "transitional period", "grace period")
# "shall not apply" is an exemption and "may not" a prohibition, so neither counts as the
# bare "shall" or "may".
_STRICTER = _cues(
    r"shall(?! not apply\b)",
    "must",
    "required",
    "at least",
    "minimum",
    r"prohibit\w*",
    "ban(?:s|ned)?",
    "may not",
)
_WEAKER = _cues(r"may(?! not\b)", "can", "optional")
_YEAR = re.compile(r"\b(?:19|20)\d{2}\b")
_NUMBERS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "twelve": 12,
    "eighteen": 18,
    "twenty-four": 24,
    "thirty": 30,
    "thirty-six": 36,
}
_UNIT_DAYS = {"day": 1, "week": 7, "month": 30, "year": 365}
_PERIOD = re.compile(rf"\b(\d+|{'|'.join(_NUMBERS)})[\s-]+(day|week|month|year)s?\b", re.IGNORECASE)


def _year(match: re.Match[str]) -> int:
    return int(match.group())


def _days(match: re.Match[str]) -> int:
    number = match.group(1).casefold()
    count = _NUMBERS[number] if number in _NUMBERS else int(number)
    return count * _UNIT_DAYS[match.group(2).casefold()]


def _whole(field: SideField, text: str) -> Evidence | None:
    stripped = text.strip()
    if not stripped:
        return None
    start = len(text) - len(text.lstrip())
    return field, start, start + len(stripped)


def _longest(field: SideField, spans: Sequence[ChangeSpan]) -> Evidence:
    span = max(spans, key=lambda span: span.end - span.start)
    return field, span.start, span.end


def _gain(
    pattern: re.Pattern[str],
    before: str,
    after: str,
    changed: Sequence[ChangeSpan],
    field: SideField,
) -> tuple[int, Evidence | None]:
    """How many more times `pattern` occurs in `after` than in `before`, and one to quote.

    Counting whole texts rather than changed spans sees a cue the edit completes: inserting
    "not" into "shall apply" adds a "shall not apply" no changed span holds whole. The quote
    is an occurrence the edit touches when there is one.
    """
    found = list(pattern.finditer(after))
    gain = len(found) - len(pattern.findall(before))
    if gain <= 0:
        return 0, None
    touched = [
        match
        for match in found
        if any(match.start() < span.end and span.start < match.end() for span in changed)
    ]
    quote = (touched or found)[0]
    return gain, (field, quote.start(), quote.end())


def _later(
    pattern: re.Pattern[str], value: Callable[[re.Match[str]], int], old: str, new: str
) -> Evidence | None:
    """The latest value the edit adds, when it is later than the latest one it removes."""
    before = Counter(value(match) for match in pattern.finditer(old))
    matches = list(pattern.finditer(new))
    after = Counter(value(match) for match in matches)
    added, removed = after - before, before - after
    if not added or not removed or max(added) <= max(removed):
        return None
    quote = next(match for match in matches if value(match) == max(added))
    return "new_text", quote.start(), quote.end()


def read_change(old_text: str | None, new_text: str) -> Reading:
    """The direction of one edit and the wording that decided it; see the module rules.

    Linear in the texts for the cue counts; the diff is O(n*m) in tokens, bounded at 800 a
    side, which is what makes an over-long text unreadable.
    """
    if new_text.strip().casefold() in DELETION_MARKERS:
        return Reading("delete", _whole("old_text", old_text or "") or _whole("new_text", new_text))
    if old_text is None:
        return Reading("unknown", unknown_reason="original_unknown")
    try:
        spans = changed_spans(TextChange(old=old_text, new=new_text))
    except ValueError:
        return Reading("unknown", unknown_reason="over_long")
    if not spans:
        return Reading("keep")
    inserted = [span for span in spans if span.operation == "insert"]
    deleted = [span for span in spans if span.operation == "delete"]
    removed = sum(len(span.text) for span in deleted)
    if not inserted and removed >= MOSTLY_DELETED * len(old_text.strip()):
        return Reading("delete", _longest("old_text", deleted))
    exempt, exempt_quote = _gain(_EXEMPT, old_text, new_text, inserted, "new_text")
    if exempt:
        return Reading("exempt", exempt_quote)
    delayed = (
        _gain(_DELAY, old_text, new_text, inserted, "new_text")[1]
        or _later(_YEAR, _year, old_text, new_text)
        or _later(_PERIOD, _days, old_text, new_text)
    )
    if delayed is not None:
        return Reading("delay", delayed)
    stricter = (
        _gain(_STRICTER, old_text, new_text, inserted, "new_text"),
        _gain(_WEAKER, new_text, old_text, deleted, "old_text"),
        _gain(_EXEMPT, new_text, old_text, deleted, "old_text"),
    )
    weaker = (
        _gain(_WEAKER, old_text, new_text, inserted, "new_text"),
        _gain(_STRICTER, new_text, old_text, deleted, "old_text"),
    )
    tighter = sum(count for count, _ in stricter)
    looser = sum(count for count, _ in weaker)
    if tighter != looser:
        direction, cues = ("stricter", stricter) if tighter > looser else ("weaker", weaker)
        return Reading(direction, next(quote for _, quote in cues if quote is not None))
    if not deleted:
        return Reading("add", _longest("new_text", inserted))
    return Reading(
        "other", _longest("new_text", inserted) if inserted else _longest("old_text", deleted)
    )


def change_direction(old_text: str | None, new_text: str) -> Direction:
    """The direction of the edit from `old_text` (None when unknown) to `new_text`."""
    return read_change(old_text, new_text).direction


def _counts(directions: Iterable[Direction]) -> DirectionCounts:
    return DirectionCounts.model_validate(Counter(directions))


def _example(amendment: Amendment, reading: Reading) -> DirectionExample | None:
    if reading.evidence is None:
        return None
    field, start, end = reading.evidence
    text = amendment.new_text if field == "new_text" else amendment.old_text or ""
    return DirectionExample(
        direction=reading.direction,
        amendment_id=amendment.amendment_id,
        span=SourceSpan(
            record_id=amendment.amendment_id,
            field=field,
            start=start,
            end=end,
            text=text[start:end],
        ),
    )


def _actor_directions(
    atlas: AtlasView | None, run_id: str, current: Mapping[str, Amendment]
) -> tuple[ActorsStatus, str | None, tuple[ActorDirections, ...]]:
    """Directions per asking actor, read only through the view's published links.

    The view must fit the collect run (`run_id`) whose amendments are counted beside it.
    Every command collects again, so a later run of unchanged records is normal; a view of
    another run is used only when every amendment it carries is unchanged in `current`,
    and otherwise its links would be mixed with newer amendments.
    """
    if atlas is None:
        return (
            "no_atlas_view",
            "No atlas view exists for this law; run `influence atlas` first. Actor "
            "directions are read only through published links.",
            (),
        )
    if atlas.run_id != run_id and any(
        current.get(amendment.amendment_id) != amendment for amendment in atlas.bundle.amendments
    ):
        return (
            "stale_atlas_view",
            f"The atlas view was built from collect run {atlas.run_id}, not the current run "
            f"{run_id}, and amendments it carries have changed since; run `influence atlas` "
            "again. Actor directions are read only from a view of the same records.",
            (),
        )
    published = sorted(
        (link for link in atlas.bundle.links if link.status == "published"),
        key=lambda link: link.link_id,
    )
    if not published:
        return (
            "no_published_links",
            f"The atlas view of run {atlas.run_id} publishes none of its "
            f"{len(atlas.bundle.links)} shown links; unconfirmed and contradicted links "
            "are never used.",
            (),
        )
    amendments = {amendment.amendment_id: amendment for amendment in atlas.bundle.amendments}
    asks = {ask.ask_id: ask for ask in atlas.bundle.asks}
    names = {actor.actor_id: actor.name for actor in atlas.bundle.actors}
    per_actor: defaultdict[str, list[tuple[LinkId, Direction]]] = defaultdict(list)
    for link in published:
        try:
            amendment, ask = amendments[link.amendment_id], asks[link.ask_id]
        except KeyError as error:
            raise PipelineError(
                f"The atlas view's link {link.link_id} cites {error} its bundle lacks"
            ) from error
        direction = change_direction(amendment.old_text, amendment.new_text)
        for actor_id in dict.fromkeys((ask.actor_id, *ask.joint_actor_ids)):
            per_actor[actor_id].append((link.link_id, direction))
    rows = (
        ActorDirections(
            actor_id=actor_id,
            name=names.get(actor_id, actor_id),
            published_links=len(links),
            counts=_counts(direction for _, direction in links),
            link_ids=tuple(link_id for link_id, _ in links),
        )
        for actor_id, links in per_actor.items()
    )
    return (
        "from_published_links",
        None,
        tuple(sorted(rows, key=lambda row: (-row.published_links, row.actor_id))),
    )


def build_directions(
    law: LawRecord,
    run_id: str,
    amendments: Iterable[Amendment],
    actors: Iterable[Actor],
    atlas: AtlasView | None,
    *,
    generated_at: datetime,
) -> DirectionsView:
    """Count one law's amendment directions overall, by stage, group and Member, and actor.

    Linear in the amendments apart from each one's bounded diff; the result does not
    depend on their order.
    """
    known = tuple(actors)
    groups = {actor.actor_id: actor.political_group for actor in known if actor.political_group}
    names = {actor.actor_id: actor.name for actor in known}
    ordered = sorted(amendments, key=lambda amendment: amendment.amendment_id)
    readings = [read_change(amendment.old_text, amendment.new_text) for amendment in ordered]
    by_stage: defaultdict[str, list[Direction]] = defaultdict(list)
    by_group: defaultdict[str, list[Direction]] = defaultdict(list)
    by_member: defaultdict[str, list[Direction]] = defaultdict(list)
    examples: dict[Direction, DirectionExample] = {}
    without_group = 0
    for amendment, reading in zip(ordered, readings, strict=True):
        direction = reading.direction
        by_stage[amendment.stage].append(direction)
        tabling_groups = {groups[a] for a in amendment.author_ids if a in groups}
        without_group += not tabling_groups
        for group in tabling_groups:
            by_group[group].append(direction)
        for author in dict.fromkeys(amendment.author_ids):
            by_member[author].append(direction)
        example = _example(amendment, reading)
        if example is not None and direction not in examples:
            examples[direction] = example
    reasons = Counter(reading.unknown_reason for reading in readings)
    status, reason, actor_rows = _actor_directions(
        atlas, run_id, {amendment.amendment_id: amendment for amendment in ordered}
    )
    members = sorted(by_member.items(), key=lambda item: (-len(item[1]), item[0]))
    return DirectionsView(
        procedure_id=law.procedure_id,
        slug=procedure_slug(law.procedure_id),
        title=law.title,
        run_id=run_id,
        generated_at=generated_at,
        method=METHOD,
        amendments=len(ordered),
        counts=_counts(reading.direction for reading in readings),
        unknown_reasons=UnknownReasons(
            over_long=reasons["over_long"], original_unknown=reasons["original_unknown"]
        ),
        by_stage=tuple(
            StageDirections(stage=stage, amendments=len(by_stage[stage]), counts=_counts(found))
            for stage in ("committee", "plenary")
            if (found := by_stage[stage])
        ),
        by_group=tuple(
            GroupDirections(group=group, amendments=len(found), counts=_counts(found))
            for group, found in sorted(by_group.items(), key=lambda item: (-len(item[1]), item[0]))
        ),
        without_group=without_group,
        top_members=tuple(
            MemberDirections(
                actor_id=author,
                name=names.get(author, author),
                political_group=groups.get(author),
                amendments=len(found),
                counts=_counts(found),
            )
            for author, found in members[:TOP_MEMBERS]
        ),
        actors_status=status,
        actors_reason=reason,
        atlas_run_id=atlas.run_id if atlas is not None else None,
        actors=actor_rows,
        examples=tuple(examples[d] for d in PRECEDENCE if d in examples),
        limitations=LIMITATIONS,
    )


def write_directions(view: DirectionsView, bundle: Path) -> Path:
    path = bundle / VIEW_FILE
    write_bytes_atomic(path, view.model_dump_json().encode("utf-8"))
    return path
