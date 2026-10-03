"""Actor resolution: one identity per organisation across sources, and a visible doubt.

A wrong merge is worse than a missed one: it moves one organisation's asks, meetings and
budget onto another, and the result still looks clean. So only two things establish an
identity, and everything weaker is recorded as a proposal a person can check:

1. A Transparency Register ID carried by the source. Two different IDs are never merged.
2. A normalised name equal to exactly one register entry's name. Without this the same
   organisation would split in two whenever one source omits the ID. Normalisation drops
   "Europe", "European" and "EU" as filler, yet those words also tell a European body
   from its parent ("Fair Trials" and "Fair Trials Europe" are separate entries in real
   data), so the match is accepted only when both names use those words equally often.

An acronym match and a fuzzy name match never merge. The actor keeps an identity of its
own (`actor:name:...`) and lists the register entries it might be in `candidate_ids`.
That identity keeps the scope words the matching key drops, so "Fair Trials" and "Fair
Trials Europe" stay two actors even when neither is in the register. An
association and its members are different actors: the register's member lists are free
text and are not used as a matching key at all. An actor absent from the register still
gets an identity and keeps its asks. Private citizens share one aggregate actor and are
never named.

Members of the European Parliament are keyed by Parliament ID in another connector.
"""

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from hashlib import sha256
from types import MappingProxyType
from typing import NamedTuple, get_args

from pydantic import TypeAdapter, ValidationError

from influence.extraction.names import FUZZY_THRESHOLD, normalise, token_set_ratio, tokenise
from influence.repositories.register import RegisterEntry, country_iso3, to_actor
from influence.schemas.atlas import (
    CITIZENS_ACTOR_ID,
    Actor,
    ActorAlias,
    RegisterId,
    ResolutionMethod,
    SourceKind,
    named_actor_id,
    register_actor_id,
)

# Have Your Say's two user types for private individuals.
CITIZEN_USER_TYPES = frozenset({"EU_CITIZEN", "NON_EU_CITIZEN"})
CITIZENS_NAME = "Private citizens (aggregated)"
# Written in `category` when a source cites a register ID the current export lacks, which
# is what a deregistered organisation looks like. The cited ID is still its identity.
ABSENT_FROM_REGISTER = "Not in the current Transparency Register export"
# The summary key for the citizens aggregate, which no resolution method describes.
CITIZENS_SUMMARY_KEY = "citizens"

# The filler words that carry meaning: they separate a European body from its namesake.
_SCOPE_WORD = re.compile(r"\b(?:europe|european|eu)\b")

_REGISTER_ID = TypeAdapter[str](RegisterId)
_METHODS: tuple[str, ...] = get_args(ResolutionMethod.__value__)

_CITIZENS = Actor(
    actor_id=CITIZENS_ACTOR_ID, kind="citizens", name=CITIZENS_NAME, resolution="unresolved"
)


class _IndexedName(NamedTuple):
    register_id: str
    name: str
    # Length of the sorted unique tokens joined by spaces: what `token_set_ratio` compares.
    length: int
    country_code: str | None


def _alias_order(alias: ActorAlias) -> tuple[str, str, str]:
    return alias.name, alias.source_kind, alias.document_id or ""


def _with_aliases(actor: Actor, aliases: Iterable[ActorAlias]) -> Actor:
    distinct = {_alias_order(alias): alias for alias in (*actor.aliases, *aliases)}
    return actor.model_copy(update={"aliases": tuple(distinct[key] for key in sorted(distinct))})


def _scope(name: str) -> int:
    return len(_SCOPE_WORD.findall(name.lower()))


def _usable_register_id(register_id: str | None) -> str | None:
    """A source's register ID, or None when it is absent or not shaped like one.

    Sources pad the ID with spaces. A value that is not an ID after trimming is a typing
    error whose intended ID is unknown, so it identifies nothing and the name decides.
    """
    try:
        return _REGISTER_ID.validate_python((register_id or "").strip())
    except ValidationError:
        return None


def _named_id(source_kind: SourceKind, normalised: str, spelling: str) -> str:
    """An identity for a name with no register identity, stable across runs.

    The key is the normalised name followed by its scope words, which normalisation
    drops but which separate a European body from its namesake. An ASCII key maps to an
    ID one to one. Other scripts lose their letters in an ID, so two different names
    could collide; a digest of the key (or of the spelling, when nothing is left) keeps
    them apart.
    """
    key = " ".join((normalised, *_SCOPE_WORD.findall(spelling.lower()))).strip()
    if key and key.isascii():
        return named_actor_id(source_kind, key)
    digest = sha256((key or spelling.casefold()).encode()).hexdigest()[:12]
    return named_actor_id(source_kind, f"{key} {digest}")


@dataclass(frozen=True)
class ActorResolver:
    """Register lookups built once; each resolution then touches only plausible entries."""

    by_id: Mapping[str, RegisterEntry]
    by_name: Mapping[str, tuple[str, ...]]
    by_acronym: Mapping[str, tuple[str, ...]]
    # (normalised name, number of scope words) of every register name: see the module text.
    scoped_names: frozenset[tuple[str, int]]
    names: tuple[_IndexedName, ...]
    by_token: Mapping[str, tuple[int, ...]]

    @classmethod
    def build(cls, entries: Iterable[RegisterEntry]) -> ActorResolver:
        """Index the register by ID, normalised name, acronym and name token.

        Linear in the total length of the names. An ID repeated in the export keeps its
        last record. Designed for about 18,000 entries (measured: under a second).
        """
        by_id: dict[str, RegisterEntry] = {}
        by_name: dict[str, set[str]] = {}
        by_acronym: dict[str, set[str]] = {}
        scoped_names: set[tuple[str, int]] = set()
        names: list[_IndexedName] = []
        by_token: dict[str, list[int]] = {}
        for entry in entries:
            by_id[entry.register_id] = entry
            for name in filter(None, (entry.name, entry.latin_name)):
                tokens = sorted(set(tokenise(name)))
                if not tokens:
                    # A name made only of filler ("European Union") separates nothing.
                    continue
                by_name.setdefault(normalise(name), set()).add(entry.register_id)
                scoped_names.add((normalise(name), _scope(name)))
                for token in tokens:
                    by_token.setdefault(token, []).append(len(names))
                names.append(
                    _IndexedName(entry.register_id, name, len(" ".join(tokens)), entry.country_code)
                )
            acronym = normalise(entry.acronym or "")
            if acronym:
                # A separate index: an acronym is shared by unrelated bodies, so a hit on
                # it is weaker evidence than a hit on a name and must stay distinguishable.
                by_acronym.setdefault(acronym, set()).add(entry.register_id)
        return cls(
            MappingProxyType(by_id),
            MappingProxyType({key: tuple(sorted(ids)) for key, ids in by_name.items()}),
            MappingProxyType({key: tuple(sorted(ids)) for key, ids in by_acronym.items()}),
            frozenset(scoped_names),
            tuple(names),
            MappingProxyType({token: tuple(where) for token, where in by_token.items()}),
        )

    def resolve(
        self,
        name: str | None,
        *,
        register_id: str | None,
        source_kind: SourceKind,
        user_type: str | None = None,
        country: str | None = None,
        document_id: str | None = None,
    ) -> Actor:
        """Give one source's mention of an actor its identity, most reliable evidence first.

        Every step but the fuzzy one is a dictionary lookup; see `_fuzzy` for its cost.
        """
        spelling = " ".join((name or "").split())
        code = _usable_register_id(register_id)
        if user_type in CITIZEN_USER_TYPES or (not spelling and code is None):
            return _CITIZENS
        aliases = (
            (ActorAlias(name=spelling, source_kind=source_kind, document_id=document_id),)
            if spelling
            else ()
        )
        source_country = country_iso3(country) or country
        if code is not None:
            entry = self.by_id.get(code)
            if entry is not None:
                return _with_aliases(to_actor(entry), aliases)
            # Deregistered since the source was written. The cited ID is still the
            # identity; matching the name to some other entry would merge two IDs.
            return Actor(
                actor_id=register_actor_id(code),
                kind="organisation",
                name=spelling or f"Transparency Register {code}",
                register_id=code,
                category=ABSENT_FROM_REGISTER,
                country=source_country,
                aliases=aliases,
                resolution="register_id",
                resolution_score=1.0,
            )
        key = normalise(spelling)
        exact = self.by_name.get(key, ())
        if len(exact) == 1 and (key, _scope(spelling)) in self.scoped_names:
            accepted = to_actor(self.by_id[exact[0]]).model_copy(
                update={"resolution": "normalised_exact"}
            )
            return _with_aliases(accepted, aliases)
        method: ResolutionMethod
        score: float | None
        if exact:
            # Several register entries under one name (national branches, re-registrations):
            # attributing the mention to any one would be a coin flip, reported below as
            # ambiguous. One entry differing only in scope words is a proposal, scored as
            # the fuzzy comparison scores it: identical tokens, 1.0.
            candidates, method, score = exact, "fuzzy", 1.0
        elif key in self.by_acronym:
            # No similarity was measured, so no score: equal acronyms prove little.
            candidates, method, score = self.by_acronym[key], "acronym", None
        else:
            score, candidates = self._fuzzy(spelling, country)
            method = "fuzzy" if candidates else "unresolved"
        return Actor(
            actor_id=_named_id(source_kind, key, spelling),
            kind="organisation",
            name=spelling,
            country=source_country,
            aliases=aliases,
            resolution="ambiguous" if len(candidates) > 1 else method,
            resolution_score=score,
            candidate_ids=tuple(register_actor_id(candidate) for candidate in candidates),
        )

    def _fuzzy(self, spelling: str, country: str | None) -> tuple[float | None, tuple[str, ...]]:
        """The register entries whose name is nearly this one: (best score, their IDs).

        Only entries sharing at least one name token with the query are scored, found
        through the inverted token index, so the cost is the sum of the posting lists of
        the query's tokens rather than the whole register. Of those, a pair whose compared
        strings differ too much in length to reach the threshold is dropped without
        scoring (an exact bound: the ratio is at most 2 min(a, b) / (a + b)). Each scored
        pair costs one `difflib` comparison, quadratic in the name length at worst.
        Consequence: a misspelling of a one-word name shares no token and is not proposed.

        Entries tied on the best score are all returned; the caller reports the tie as
        ambiguous. A candidate in a different country is not proposed when both sides
        state one, compared as ISO-3 codes.

        Measured on the 2026-10-02 export (17,897 entries): 100 Have Your Say submitters
        resolve in well under a second.
        """
        tokens = sorted(set(tokenise(spelling)))
        length = len(" ".join(tokens))
        wanted = country_iso3(country)
        best_score: float | None = None
        best: set[str] = set()
        for position in {where for token in tokens for where in self.by_token.get(token, ())}:
            candidate = self.names[position]
            if 2 * min(length, candidate.length) < FUZZY_THRESHOLD * (length + candidate.length):
                continue
            if wanted is not None and candidate.country_code not in (None, wanted):
                continue
            score = token_set_ratio(spelling, candidate.name)
            if score < (best_score or FUZZY_THRESHOLD):
                continue
            if score != best_score:
                best_score, best = score, set()
            best.add(candidate.register_id)
        return best_score, tuple(sorted(best))


def merge_actors(actors: Iterable[Actor]) -> tuple[Actor, ...]:
    """One record per `actor_id`, with every spelling seen, in a fixed order.

    Records sharing an ID already are the same identity, so nothing is decided here: the
    aliases are united and sorted, and the other fields come from the record that sorts
    first, which makes the result independent of input order. O(n log n).
    """
    groups: dict[str, list[Actor]] = {}
    for actor in actors:
        groups.setdefault(actor.actor_id, []).append(actor)
    merged: list[Actor] = []
    for actor_id in sorted(groups):
        group = sorted(groups[actor_id], key=Actor.model_dump_json)
        merged.append(
            _with_aliases(group[0], (alias for actor in group[1:] for alias in actor.aliases))
        )
    return tuple(merged)


def resolution_summary(actors: Iterable[Actor]) -> dict[str, int]:
    """How many actors each method produced, with every method present even at zero.

    The citizens aggregate is counted under its own key so that it does not inflate the
    unresolved count the coverage report shows.
    """
    counts = dict.fromkeys((*_METHODS, CITIZENS_SUMMARY_KEY), 0)
    for actor in actors:
        counts[CITIZENS_SUMMARY_KEY if actor.kind == "citizens" else actor.resolution] += 1
    return counts
