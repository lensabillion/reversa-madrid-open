"""Read Parltrack's bulk dumps into Atlas records for any procedure, with no per-law code.

Parltrack (parltrack.org, ODbL v1.0) republishes the European Parliament's dossiers,
amendments and Members as zstd-compressed files holding one JSON record per line: the
first line opens the array with `[`, every later record starts with `,`, and the last
line is `]`. The amendment dump holds 1.27 million records, so nothing here loads a dump
into memory: every reader is a single streaming pass, linear in the size of the dump.

A record the source left unusable (no wording, no identifier, a reference that is not a
procedure) is skipped and counted in the caller's tally, never guessed at and never a
crash; an unreadable dump is a `ParltrackError`.
"""

import hashlib
import json
import re
from collections import Counter
from collections.abc import Collection, Iterable, Iterator
from compression import zstd
from datetime import date, datetime
from pathlib import Path
from typing import cast

from pydantic import ValidationError

from influence.extraction.files import write_bytes_atomic
from influence.schemas.atlas import (
    PROCEDURE_PATTERN,
    Actor,
    Amendment,
    AmendmentStage,
    LawStatus,
    NonEmpty,
    ProcedureId,
    SourceDocument,
    document_id,
    id_part,
    mep_actor_id,
)
from influence.schemas.scoring import FrozenModel

DUMP_BASE_URL = "https://parltrack.org/dumps/"
DUMP_SUFFIX = ".json.zst"
REUSE_TERMS = "ODbL v1.0 (Parltrack)"

# Skip reasons, the keys of the tally a caller passes in.
SKIP_NO_PROCEDURE = "no_procedure"
SKIP_NOT_A_PROCEDURE = "reference_not_a_procedure"
SKIP_INVALID = "invalid"
SKIP_NO_TEXT = "no_text"
SKIP_NO_ID = "no_id"
SKIP_DUPLICATE_ID = "duplicate_id"
SKIP_NO_NAME = "no_name"

_PROCEDURE = re.compile(PROCEDURE_PATTERN)
_COM_REFERENCE = re.compile(r"COM\((\d{4})\)(\d+)")
_CELEX_IN_URL = re.compile(r"numdoc=(\d[0-9A-Z]+)")
_LEAD_COMMITTEE_TYPES = frozenset({"Responsible Committee", "Joint Responsible Committee"})
_PROPOSAL_EVENTS = frozenset(
    {"Legislative proposal published", "Initial legislative proposal published"}
)
_FINAL_ACT_EVENT = "Final act published in Official Journal"
_END_IN_PARLIAMENT_EVENT = "End of procedure in Parliament"
# Stages that end a procedure without an act. A rejected procedure is grouped with the
# withdrawn ones because the Atlas status has no value of its own for it.
_ENDED_WITHOUT_ACT = frozenset({"procedure lapsed or withdrawn", "procedure rejected"})
_HASH_CHUNK_BYTES = 1 << 20
_SURROGATES = re.compile("[\ud800-\udfff]")
# A tabling date as the amendment dumps write it; the scan for the dump's end date
# reads it from the raw line, without parsing JSON.
_DUMP_DATE = re.compile(rb'"date": ?"(\d{4}-\d{2}-\d{2})')

type Record = dict[str, object]


class ParltrackError(Exception):
    """A Parltrack dump or catalog file could not be read as the format it claims."""


class ProcedureEntry(FrozenModel):
    """One dossier reduced to what resolving a law by name, number or CELEX needs."""

    procedure_id: ProcedureId
    title: NonEmpty
    stage_reached: str | None
    status: LawStatus
    subjects: tuple[str, ...] = ()
    celex_final: str | None = None
    com_references: tuple[str, ...] = ()
    lead_committee: str | None = None
    rapporteurs: tuple[str, ...] = ()
    proposed_on: date | None = None
    completed_on: date | None = None
    last_activity_on: date | None = None


# --- Typed access to untyped JSON ---------------------------------------------------------


def _mapping(value: object) -> Record:
    """The value as a JSON object, or an empty one when the source put something else."""
    return cast("Record", value) if isinstance(value, dict) else {}


def _items(value: object) -> list[object]:
    return cast("list[object]", value) if isinstance(value, list) else []


def _clean(text: str) -> str:
    """Replace lone surrogates, which JSON escapes can carry and UTF-8 cannot encode.

    Without this one bad `\\ud83d` in an amendment crashes writing the whole stage.
    """
    return _SURROGATES.sub("\ufffd", text)


def _strings(value: object) -> list[str]:
    """A field Parltrack writes as one string or a list of them, always as a list."""
    if isinstance(value, str):
        return [_clean(value)]
    return [_clean(item) for item in _items(value) if isinstance(item, str)]


def _text(value: object) -> str | None:
    """A non-blank string with outer whitespace removed; anything else is unknown."""
    if not isinstance(value, str):
        return None
    return _clean(value).strip() or None


def _day(value: object) -> date | None:
    """The calendar day of an ISO timestamp; a missing or malformed one stays unknown."""
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value).date()
    except ValueError:
        return None


def _count(skipped: Counter[str] | None, reason: str) -> None:
    if skipped is not None:
        skipped[reason] += 1


# --- Dumps --------------------------------------------------------------------------------


def iter_dump(path: Path, containing: str | None = None) -> Iterator[Record]:
    """Yield each record of a dump, decompressing and parsing one line at a time.

    `containing` skips, before any JSON is parsed, every line that does not hold that
    string as a JSON value. Parsing is the dominant cost (about 55 s for the whole
    amendment dump against 5 s to decompress it), so a reader that wants one procedure
    passes its reference here; the caller still checks the field, because the string
    may sit in another field of an unrelated record.
    """
    needle = None if containing is None else json.dumps(containing, ensure_ascii=False).encode()
    try:
        with zstd.open(path, "rb") as stream:
            for line in stream:
                body = line.strip()
                if body[:1] in (b"[", b","):
                    body = body[1:]
                if body in (b"", b"]"):
                    continue
                if needle is not None and needle not in body:
                    continue
                record: object = json.loads(body)
                if not isinstance(record, dict):
                    raise ParltrackError(f"{path}: a dump line is not a JSON object")
                yield cast("Record", record)
    except (OSError, EOFError, zstd.ZstdError, ValueError) as error:
        raise ParltrackError(f"{path}: unreadable Parltrack dump: {error}") from error


def latest_date(path: Path) -> date | None:
    """The latest `"date"` any record of the dump states: how far the dump reaches.

    A raw scan of every line, with no JSON parsed, so one pass costs about what
    decompressing does (about 5 s for the amendment dump). The latest date of any
    record is a bound for all of them; a typo far in the future would hide staleness,
    never invent it. Linear in the dump's size; callers cache the answer per dump hash.
    """
    latest: bytes | None = None
    try:
        with zstd.open(path, "rb") as stream:
            for line in stream:
                for found in _DUMP_DATE.findall(line):
                    if latest is None or found > latest:
                        latest = found
    except (OSError, EOFError, zstd.ZstdError) as error:
        raise ParltrackError(f"{path}: unreadable Parltrack dump: {error}") from error
    return None if latest is None else date.fromisoformat(latest.decode())


def dump_source_document(path: Path, retrieved_at: datetime) -> SourceDocument:
    """Describe a dump file as the source its records came from, hashed as a stream.

    The dump covers every procedure, so the document names none; its publication time
    is not stated by the file and stays unknown.
    """
    if not path.name.endswith(DUMP_SUFFIX):
        raise ParltrackError(f"{path}: not a Parltrack dump name (*{DUMP_SUFFIX})")
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            while chunk := handle.read(_HASH_CHUNK_BYTES):
                digest.update(chunk)
    except OSError as error:
        raise ParltrackError(f"{path}: unreadable Parltrack dump: {error}") from error
    name = path.name.removesuffix(DUMP_SUFFIX)
    return SourceDocument(
        document_id=document_id("parltrack", name),
        procedure_id=None,
        source_kind="parltrack",
        url=f"{DUMP_BASE_URL}{path.name}",
        title=f"Parltrack dump {name}",
        published_at=None,
        retrieved_at=retrieved_at,
        sha256=digest.hexdigest(),
        media_type="application/zstd",
        extraction_status="not_applicable",
        reuse_terms=REUSE_TERMS,
    )


# --- Procedure catalog --------------------------------------------------------------------


def _status(stage: str | None) -> LawStatus:
    if stage is None:
        return "unknown"
    lowered = stage.lower()
    if lowered.startswith("procedure completed"):
        return "completed"
    if lowered in _ENDED_WITHOUT_ACT:
        return "withdrawn"
    if lowered.startswith(("awaiting", "preparatory")):
        return "ongoing"
    return "unknown"


def _subjects(value: object) -> tuple[str, ...]:
    """Subjects as `code label` strings; older dossiers already hold them in that form."""
    if isinstance(value, dict):
        pairs = cast("Record", value).items()
        return tuple(f"{code} {label}".strip() for code, label in pairs if isinstance(label, str))
    return tuple(_strings(value))


def _celex_final(procedure: Record) -> str | None:
    url = _mapping(procedure.get("final")).get("url")
    match = _CELEX_IN_URL.search(url) if isinstance(url, str) else None
    return match.group(1) if match else None


def _lead(committees: object) -> tuple[str | None, tuple[str, ...]]:
    """The responsible committee (joint ones joined with `/`) and its rapporteurs."""
    for item in _items(committees):
        committee = _mapping(item)
        if (
            committee.get("type") not in _LEAD_COMMITTEE_TYPES
            and committee.get("responsible") is not True
        ):
            continue
        names = "/".join(_strings(committee.get("committee")))
        rapporteurs = (
            _text(_mapping(person).get("name")) for person in _items(committee.get("rapporteur"))
        )
        return names or None, tuple(name for name in rapporteurs if name is not None)
    return None, ()


def _com_reference(title: object) -> str | None:
    """`COM(2021)0206` as `COM(2021)206`, the form EUR-Lex and the Commission write."""
    match = _COM_REFERENCE.fullmatch(title.strip()) if isinstance(title, str) else None
    return f"COM({match.group(1)}){int(match.group(2))}" if match else None


def _entry(dossier: Record, procedure: Record, reference: str) -> ProcedureEntry:
    stage = _text(procedure.get("stage_reached"))
    status = _status(stage)
    lead_committee, rapporteurs = _lead(dossier.get("committees"))
    days: list[date] = []
    proposed: list[date] = []
    published: list[date] = []
    ended: list[date] = []
    com_references: dict[str, None] = {}
    for item in _items(dossier.get("events")):
        event = _mapping(item)
        for document in _items(event.get("docs")):
            com = _com_reference(_mapping(document).get("title"))
            if com is not None:
                com_references[com] = None
        day = _day(event.get("date"))
        if day is None:
            continue
        days.append(day)
        kind = event.get("type")
        if kind in _PROPOSAL_EVENTS:
            proposed.append(day)
        elif kind == _FINAL_ACT_EVENT:
            published.append(day)
        elif kind == _END_IN_PARLIAMENT_EVENT:
            ended.append(day)
    days.extend(
        day for item in _items(dossier.get("docs")) if (day := _day(_mapping(item).get("date")))
    )
    completed = published or ended
    return ProcedureEntry(
        procedure_id=reference,
        title=_text(procedure.get("title")) or "",
        stage_reached=stage,
        status=status,
        subjects=_subjects(procedure.get("subject")),
        celex_final=_celex_final(procedure),
        com_references=tuple(com_references),
        lead_committee=lead_committee,
        rapporteurs=rapporteurs,
        proposed_on=min(proposed, default=None),
        completed_on=max(completed) if status == "completed" and completed else None,
        last_activity_on=max(days, default=None),
    )


def build_catalog(
    dossiers_path: Path, skipped: Counter[str] | None = None
) -> Iterator[ProcedureEntry]:
    """Yield one entry per dossier that is a procedure, counting the rest in `skipped`.

    About one dossier in seven is not a procedure at all but a Commission document
    (reference `COM(2019)0308`); those are counted as `reference_not_a_procedure`.
    """
    for dossier in iter_dump(dossiers_path):
        procedure = _mapping(dossier.get("procedure"))
        if not procedure:
            _count(skipped, SKIP_NO_PROCEDURE)
            continue
        reference = procedure.get("reference")
        if not isinstance(reference, str) or _PROCEDURE.fullmatch(reference) is None:
            _count(skipped, SKIP_NOT_A_PROCEDURE)
            continue
        try:
            yield _entry(dossier, procedure, reference)
        except ValidationError:
            _count(skipped, SKIP_INVALID)


def write_catalog(entries: Iterable[ProcedureEntry], path: Path) -> int:
    """Write the catalog as JSON Lines in one atomic step and return the entry count.

    The whole catalog (about 20,000 short entries, under 10 MB) is built in memory
    because an atomic write needs the complete content.
    """
    lines = [entry.model_dump_json() for entry in entries]
    write_bytes_atomic(path, "".join(f"{line}\n" for line in lines).encode())
    return len(lines)


def read_catalog(path: Path) -> Iterator[ProcedureEntry]:
    try:
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                yield ProcedureEntry.model_validate_json(line)
    except (OSError, ValueError) as error:
        raise ParltrackError(f"{path}: unreadable procedure catalog: {error}") from error


# --- Amendments ---------------------------------------------------------------------------


def _wording(record: Record, key: str) -> str | None:
    """The lines of one side of an amendment; None only when the record lacks the key."""
    if key not in record:
        return None
    return "\n".join(_strings(record[key]))


def _number(seq: object) -> int | None:
    if isinstance(seq, int) and seq >= 0:
        return seq
    if isinstance(seq, str) and seq.isascii() and seq.isdigit():
        return int(seq)
    return None


def _author_names(authors: object) -> tuple[str, ...]:
    """Split the comma-separated authors line and collapse the dump's stray whitespace."""
    parts = (" ".join(part.split()) for line in _strings(authors) for part in line.split(","))
    return tuple(part for part in parts if part)


def _location(value: object) -> str | None:
    """`Proposal for a regulation - Recital 1`; several targets are separated by `; `."""
    targets = (
        item.strip()
        if isinstance(item, str)
        else " - ".join(part.strip() for part in _strings(item))
        for item in _items(value)
    )
    return "; ".join(target for target in targets if target) or None


def _amendment(
    record: Record,
    procedure_id: str,
    stage: AmendmentStage,
    source_id: str,
    dump_document_id: str,
) -> Amendment:
    committee = "/".join(_strings(record.get("committee"))) or None
    label = "PLENARY" if stage == "plenary" else id_part(committee or "UNKNOWN")
    return Amendment(
        amendment_id=f"am:{id_part(procedure_id)}:{label}:{id_part(source_id)}",
        procedure_id=procedure_id,
        # The dump is the file this connector retrieves and hashes, so it is the source an
        # amendment can cite (`dump_source_document`). The Parliament document is not
        # downloaded; its number stays in the amendment's own identifier.
        document_id=dump_document_id,
        stage=stage,
        committee=committee,
        number=_number(record.get("seq")),
        author_ids=tuple(
            mep_actor_id(mep) for mep in _items(record.get("meps")) if isinstance(mep, int)
        ),
        author_names=_author_names(record.get("authors")),
        tabled_on=_day(record.get("date")),
        target_provision=_location(record.get("location")),
        old_text=_wording(record, "old"),
        new_text=_wording(record, "new") or "",
        justification=_text(record.get("justification")),
        language=(_text(record.get("orig_lang")) or "").lower() or None,
    )


def _amendments(
    path: Path, procedure_id: str, stage: AmendmentStage, skipped: Counter[str] | None
) -> Iterator[Amendment]:
    """One pass over the dump; memory grows only with the identifiers of the matches."""
    seen: set[str] = set()
    dump_document_id = document_id("parltrack", path.name.removesuffix(DUMP_SUFFIX))
    for record in iter_dump(path, containing=procedure_id):
        if record.get("reference") != procedure_id:
            continue
        source_id = _text(record.get("id"))
        if source_id is None:
            _count(skipped, SKIP_NO_ID)
            continue
        if (
            not (_wording(record, "old") or "").strip()
            and not (_wording(record, "new") or "").strip()
        ):
            _count(skipped, SKIP_NO_TEXT)
            continue
        try:
            # ValueError covers both a failed validation and an identifier with no
            # characters an Atlas ID accepts.
            amendment = _amendment(record, procedure_id, stage, source_id, dump_document_id)
        except ValueError:
            _count(skipped, SKIP_INVALID)
            continue
        if amendment.amendment_id in seen:
            _count(skipped, SKIP_DUPLICATE_ID)
            continue
        seen.add(amendment.amendment_id)
        yield amendment


def committee_amendments(
    path: Path,
    procedure_id: str,
    retrieved_at: datetime,
    skipped: Counter[str] | None = None,
) -> Iterator[Amendment]:
    """Amendments tabled in committee on one procedure, from `ep_amendments`.

    `retrieved_at` is accepted so every connector is called the same way; an amendment
    carries no retrieval time of its own (the dump's `SourceDocument` does).
    """
    del retrieved_at
    return _amendments(path, procedure_id, "committee", skipped)


def plenary_amendments(
    path: Path,
    procedure_id: str,
    retrieved_at: datetime,
    skipped: Counter[str] | None = None,
) -> Iterator[Amendment]:
    """Amendments tabled for the plenary vote, from `ep_plenary_amendments`.

    The plenary dump names the responsible committee, not a tabling one, so the
    identifier says `PLENARY` and `committee` keeps what the dump states.
    """
    del retrieved_at
    return _amendments(path, procedure_id, "plenary", skipped)


# --- Members ------------------------------------------------------------------------------


class GroupSpell(FrozenModel):
    """One Member's membership of one political group; None bounds are unknown."""

    group: NonEmpty
    start: date | None
    end: date | None


class Member(FrozenModel):
    """A Member as an actor, with every group spell, to tell the group on a given day."""

    actor: Actor
    groups: tuple[GroupSpell, ...] = ()


def _latest(spells: object, key: str) -> str | None:
    """The value of the spell that ends last (current spells end in year 9999).

    ISO timestamps sort as text, so no date is parsed.
    """
    dated = [
        ((_text(spell.get("end")) or "", _text(spell.get("start")) or ""), value)
        for spell in map(_mapping, _items(spells))
        if (value := _text(spell.get(key))) is not None
    ]
    return max(dated)[1] if dated else None


def _group_spells(spells: object) -> tuple[GroupSpell, ...]:
    return tuple(
        GroupSpell(group=group, start=_day(spell.get("start")), end=_day(spell.get("end")))
        for spell in map(_mapping, _items(spells))
        if (group := _text(spell.get("groupid"))) is not None
    )


def group_on(spells: Iterable[GroupSpell], day: date | None) -> str | None:
    """The group of the spell covering `day`, or None when no spell or no day says.

    Where spells overlap (a move dated the same day on both sides) the one that started
    last wins. An undated amendment gets None, never the latest group: a Member who
    changed group would otherwise be credited to the wrong one.
    """
    if day is None:
        return None
    covering = [
        (spell.start or date.min, spell.group)
        for spell in spells
        if (spell.start is None or spell.start <= day) and (spell.end is None or day <= spell.end)
    ]
    return max(covering)[1] if covering else None


def mep_members(
    meps_path: Path, mep_ids: Collection[int], skipped: Counter[str] | None = None
) -> Iterator[Member]:
    """The given Members only, stopping once every one has been found.

    `Actor.political_group` is the latest group, for display; `groups` holds every
    dated spell, so `group_on` can tell the group on the day an amendment was tabled.
    """
    wanted = set(mep_ids)
    for record in iter_dump(meps_path):
        if not wanted:
            return
        mep_id = record.get("UserID")
        if not isinstance(mep_id, int) or mep_id not in wanted:
            continue
        wanted.discard(mep_id)
        name = _text(_mapping(record.get("Name")).get("full"))
        if name is None:
            _count(skipped, SKIP_NO_NAME)
            continue
        try:
            yield Member(
                actor=Actor(
                    actor_id=mep_actor_id(mep_id),
                    kind="mep",
                    name=name,
                    mep_id=mep_id,
                    country=_latest(record.get("Constituencies"), "country"),
                    political_group=_latest(record.get("Groups"), "groupid"),
                    resolution="mep_id",
                ),
                groups=_group_spells(record.get("Groups")),
            )
        except ValidationError:
            _count(skipped, SKIP_INVALID)
