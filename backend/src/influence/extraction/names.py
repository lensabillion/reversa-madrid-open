"""Organisation-name normalisation for entity resolution (part 2).

Consultation submissions and meeting records carry free-text organisation names, and only
slightly over half of them use the register's official spelling, so a join on the raw name
is wrong while looking right. These functions strip what varies between spellings of the
same body (case, punctuation, legal suffixes, filler words) so `services/actors.py` can
compare names and score near matches; the threshold below is the one it applies.
"""

from difflib import SequenceMatcher

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
