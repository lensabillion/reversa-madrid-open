"""The source catalog: every source, its scope, its verification status and where to probe.

Verification status is part of the contract, because treating an unverified endpoint as a
promise is how a pipeline fails at 14:00:

- confirmed: documented on the provider's own pages or release notes.
- third_party: a community tool or aggregator; it works but is not an official contract.
- unverified: expected to exist, not checked. Probe before building on it.
- build_yourself: no feed exists; a targeted crawl is the only route.

No URL here has been confirmed by a live request from this repository. `probe` records
what each one actually returns, and nothing parses a response shape before then.
"""

from collections.abc import Iterable
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

type Verification = Literal["confirmed", "third_party", "unverified", "build_yourself"]
type Scope = Literal["global", "per_law", "enrichment"]


class SourceSpec(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)
    letter: str = Field(min_length=1, max_length=1)
    source_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    scope: Scope
    verification: Verification
    # None where there is nothing to probe: the source is a crawl or is reached through
    # another source's document links rather than a base URL of its own.
    probe_url: str | None
    notes: str


SOURCES: tuple[SourceSpec, ...] = (
    SourceSpec(
        letter="A",
        source_id="registry",
        name="EU Transparency Register",
        scope="global",
        verification="confirmed",
        probe_url="https://transparency-register.europa.eu/",
        notes=(
            "Master actor table; every other source joins back to it. One bulk download, "
            "no key. A snapshot, not a history: deregistered bodies are absent, and "
            "self-declared budgets are inconsistent, so spend is a weak signal."
        ),
    ),
    SourceSpec(
        letter="B",
        source_id="meetings_ec",
        name="Commission meetings with interest representatives",
        scope="global",
        verification="confirmed",
        probe_url="https://data.europa.eu/",
        notes=(
            "Carries the registration id, so it yields an actor-to-law edge with no text "
            "matching. Senior officials only, so a missing meeting is not evidence of no "
            "lobbying, and subject lines need fuzzy matching against law titles."
        ),
    ),
    SourceSpec(
        letter="C",
        source_id="meetings_mep",
        name="MEP lobby meetings (Integrity Watch EU)",
        scope="global",
        verification="confirmed",
        probe_url="https://www.integritywatch.eu/",
        notes=(
            "Where lobbying meets the people who table amendments. Organisation names are "
            "free text and only about half follow the register, so never join on name: "
            "route through names.ActorIndex and keep the raw name. Uneven publication "
            "means a silent MEP is not a clean MEP."
        ),
    ),
    SourceSpec(
        letter="D",
        source_id="ep_opendata",
        name="European Parliament Open Data Portal (API v2)",
        scope="global",
        verification="confirmed",
        probe_url="https://data.europarl.europa.eu/api/v2/meps",
        notes=(
            "REST JSON, no key expected. The MEP roster is global and attributes "
            "amendments; plenary-documents is the structured amendment route. Committee "
            "amendments, where most lobbying lands, are PDFs reached through OEIL."
        ),
    ),
    SourceSpec(
        letter="E",
        source_id="oeil",
        name="Legislative Observatory (OEIL)",
        scope="per_law",
        verification="unverified",
        probe_url="https://oeil.secure.europarl.europa.eu/",
        notes=(
            "The spine of the per-law pipeline and the step that writes the manifest. No "
            "documented API; expect HTML parsing. Non-COD procedures have different "
            "document sets, which is where an 'any law' demo usually breaks."
        ),
    ),
    SourceSpec(
        letter="F",
        source_id="eurlex",
        name="EUR-Lex / Cellar",
        scope="per_law",
        verification="confirmed",
        probe_url="http://publications.europa.eu/resource/celex/32024R1689",
        notes=(
            "SPARQL for discovery and identifier retrieval by CELEX for content. Split to "
            "one row per article, paragraph and recital with a stable unit id, then diff "
            "proposal against final act: unchanged text cannot be evidence of influence. "
            "One language only; align on text similarity, not article numbers."
        ),
    ),
    SourceSpec(
        letter="G",
        source_id="hys",
        name="Have Your Say consultations",
        scope="per_law",
        verification="third_party",
        probe_url="https://ec.europa.eu/info/law/better-regulation/have-your-say",
        notes=(
            "The richest text available and the 'what they ask' side. No official API; the "
            "publication id ends the initiative URL. Chunk attachments into one ask per "
            "paragraph with page and offset, separate organisations from citizens, and "
            "count scanned or non-English attachments instead of dropping them."
        ),
    ),
    SourceSpec(
        letter="H",
        source_id="amendments",
        name="Amendments (EP API and committee PDFs)",
        scope="per_law",
        verification="unverified",
        probe_url=None,
        notes=(
            "The weakest link in the chain. Reached through sources D and E rather than a "
            "base URL. Committee documents repeat a two-column before/after layout that "
            "yields original text, proposed text and target unit together. Infer adoption "
            "by text survival in the final act instead of parsing roll-call votes."
        ),
    ),
    SourceSpec(
        letter="I",
        source_id="lobbyfacts",
        name="LobbyFacts.eu",
        scope="enrichment",
        verification="unverified",
        probe_url="https://www.lobbyfacts.eu/",
        notes="Historical register snapshots: 2019-era budgets and deregistered bodies.",
    ),
    SourceSpec(
        letter="J",
        source_id="council",
        name="Council document register",
        scope="enrichment",
        verification="unverified",
        probe_url="https://www.consilium.europa.eu/en/documents-publications/public-register/",
        notes="Council positions and compromise texts: the missing trilogue side.",
    ),
    SourceSpec(
        letter="K",
        source_id="org_websites",
        name="Organisation websites",
        scope="enrichment",
        verification="build_yourself",
        probe_url=None,
        notes="Position papers and press releases; a targeted crawl of the top actors only.",
    ),
    SourceSpec(
        letter="L",
        source_id="gdelt",
        name="GDELT",
        scope="enrichment",
        verification="unverified",
        probe_url="https://www.gdeltproject.org/",
        notes="News coverage volume and framing per actor and topic; context, not evidence.",
    ),
    SourceSpec(
        letter="M",
        source_id="wikidata",
        name="Wikidata and GLEIF",
        scope="enrichment",
        verification="unverified",
        probe_url="https://query.wikidata.org/sparql",
        notes="Canonical identifiers and aliases for companies, to widen entity resolution.",
    ),
)

# Uniqueness of letters and ids is asserted by the catalog tests: a duplicate would be
# silently dropped by these dictionaries, so the test is the tripwire.
_BY_LETTER = {spec.letter: spec for spec in SOURCES}
_BY_ID = {spec.source_id: spec for spec in SOURCES}


class UnknownSourceError(KeyError):
    """No source in the catalog carries that letter or id."""


def source(letter_or_id: str) -> SourceSpec:
    spec = _BY_LETTER.get(letter_or_id.upper()) or _BY_ID.get(letter_or_id)
    if spec is None:
        raise UnknownSourceError(letter_or_id)
    return spec


def by_scope(scope: Scope) -> tuple[SourceSpec, ...]:
    return tuple(spec for spec in SOURCES if spec.scope == scope)


def probeable(specs: Iterable[SourceSpec]) -> tuple[SourceSpec, ...]:
    """Only sources with a base URL of their own can be probed."""
    return tuple(spec for spec in specs if spec.probe_url is not None)
