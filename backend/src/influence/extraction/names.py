"""Entity resolution: three populations of names, one actor id, and a visible unresolved.

Only the Transparency Register and Commission meetings carry a registration id. MEP
meetings and consultation submissions carry free text, and only slightly over half of
MEP entries use the register's official name, so a join on name alone is wrong while
looking right. The layers below run most reliable first and record which one fired; a
visible unresolved count is more credible than a silently wrong join.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher
from types import MappingProxyType

from influence.extraction.tables import ActorRow, MatchMethod

# Stripped before comparison: the same organisation files as "X GmbH", "X" and "X, e.V.".
LEGAL_SUFFIXES = frozenset(
    {
        "ab",
        "ag",
        "aisbl",
        "aps",
        "as",
        "asbl",
        "bv",
        "corp",
        "ev",
        "gmbh",
        "inc",
        "kg",
        "limited",
        "llc",
        "ltd",
        "nv",
        "oy",
        "plc",
        "sa",
        "sarl",
        "sas",
        "sl",
        "spa",
        "srl",
        "vzw",
    }
)
# Carried by nearly every organisation name, so they separate nothing and only inflate
# similarity between unrelated bodies.
STOP_WORDS = frozenset({"the", "of", "and", "for", "european", "europe", "eu"})
# Below this token-set similarity the pair is left unresolved rather than guessed.
FUZZY_THRESHOLD = 0.90


def tokenise(name: str) -> tuple[str, ...]:
    """Lowercase, drop punctuation, legal suffixes and filler, and keep the rest in order."""
    # Dots and apostrophes close up rather than split, so "e.V." becomes the suffix "ev"
    # and "L'Oreal" one token; every other separator becomes a space.
    squeezed = name.lower().replace(".", "").replace("'", "").replace("\u2019", "")
    cleaned = "".join(character if character.isalnum() else " " for character in squeezed)
    return tuple(
        token
        for token in cleaned.split()
        if token not in LEGAL_SUFFIXES and token not in STOP_WORDS
    )


def normalise(name: str) -> str:
    """The comparison key: tokens joined by single spaces, empty when nothing survives."""
    return " ".join(tokenise(name))


def token_set_ratio(left: str, right: str) -> float:
    """Similarity on sorted unique tokens, so word order and repetition do not matter."""
    first = " ".join(sorted(set(tokenise(left))))
    second = " ".join(sorted(set(tokenise(right))))
    if not first or not second:
        return 0.0
    return SequenceMatcher(None, first, second).ratio()


@dataclass(frozen=True)
class Resolution:
    """Always stored beside the raw name, including when `actor_id` is None."""

    actor_id: str | None
    method: MatchMethod
    score: float | None


UNRESOLVED = Resolution(None, "unresolved", None)


def _add(index: dict[str, set[str]], key: str, actor_id: str) -> None:
    if key:
        index.setdefault(key, set()).add(actor_id)


@dataclass(frozen=True)
class ActorIndex:
    """Lookup tables built once from the register; resolution is then O(actors) at worst."""

    by_id: Mapping[str, ActorRow]
    by_name: Mapping[str, tuple[str, ...]]
    by_acronym: Mapping[str, tuple[str, ...]]

    @classmethod
    def build(cls, actors: Iterable[ActorRow]) -> ActorIndex:
        by_id: dict[str, ActorRow] = {}
        names: dict[str, set[str]] = {}
        acronyms: dict[str, set[str]] = {}
        for actor in actors:
            by_id[actor.actor_id] = actor
            _add(names, normalise(actor.name), actor.actor_id)
            if actor.acronym is not None:
                # Acronyms stay in their own index. Many submissions carry only "BEUC",
                # and keeping the two indexes apart records which one resolved the name.
                _add(acronyms, normalise(actor.acronym), actor.actor_id)
        return cls(
            MappingProxyType(by_id),
            MappingProxyType({key: tuple(sorted(value)) for key, value in names.items()}),
            MappingProxyType({key: tuple(sorted(value)) for key, value in acronyms.items()}),
        )

    def resolve(self, raw_name: str, registration_id: str | None = None) -> Resolution:
        """Stop at the first layer that matches; ambiguity is reported, never broken by a coin flip.

        Complexity is O(1) for the first three layers and O(number of actors) for the
        fuzzy layer, which runs only on names the exact layers missed. Designed for a
        register of roughly 13,000 organisations.
        """
        if registration_id is not None and registration_id in self.by_id:
            return Resolution(registration_id, "registration_id", 1.0)
        key = normalise(raw_name)
        if not key:
            return UNRESOLVED
        exact = self.by_name.get(key)
        if exact is not None:
            return self._single(exact, "normalised_exact", 1.0)
        acronym = self.by_acronym.get(key)
        if acronym is not None:
            return self._single(acronym, "acronym", 1.0)
        return self._fuzzy(raw_name)

    def _single(self, candidates: Sequence[str], method: MatchMethod, score: float) -> Resolution:
        if len(candidates) > 1:
            # One parent with twelve national entries looks like a perfect match twelve
            # times over. Report it instead of attributing the ask to an arbitrary one.
            return Resolution(None, "ambiguous", score)
        return Resolution(candidates[0], method, score)

    def _fuzzy(self, raw_name: str) -> Resolution:
        best_score = 0.0
        best: list[str] = []
        for actor in self.by_id.values():
            score = token_set_ratio(raw_name, actor.name)
            if score > best_score:
                best_score = score
                best = [actor.actor_id]
            elif score == best_score and score >= FUZZY_THRESHOLD:
                best.append(actor.actor_id)
        if best_score < FUZZY_THRESHOLD:
            return UNRESOLVED
        return self._single(best, "fuzzy", best_score)
