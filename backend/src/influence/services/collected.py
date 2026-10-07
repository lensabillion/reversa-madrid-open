"""Validated records of one completed collection run, shared by lineage and its CLI."""

from dataclasses import dataclass
from pathlib import Path

from influence.extraction.records import StageStore
from influence.schemas.atlas import (
    Actor,
    Amendment,
    ArticleVersion,
    AtlasRecord,
    DocumentText,
    LawRecord,
    Passage,
    RunManifest,
    SourceDocument,
)


class PipelineError(RuntimeError):
    """The law has no completed collect run to build on, or its records do not fit."""


@dataclass(frozen=True)
class Collected:
    """The records one completed collect run wrote, read back from its bundle."""

    manifest: RunManifest
    law: LawRecord
    documents: tuple[SourceDocument, ...]
    document_texts: tuple[DocumentText, ...]
    passages: tuple[Passage, ...]
    actors: tuple[Actor, ...]
    amendments: tuple[Amendment, ...]
    articles: tuple[ArticleVersion, ...]


def load_collected(bundle: Path) -> Collected:
    """Read the current manifest's stage outputs; every line is validated on the way in."""
    store = StageStore(bundle)
    manifest = store.current()
    if manifest is None:
        raise PipelineError(f"No completed collect run in {bundle}")
    receipts = {receipt.stage: receipt for receipt in manifest.stages}
    missing = {"texts", "amendments", "asks", "law"} - receipts.keys()
    if missing:
        raise PipelineError(f"The collect run in {bundle} lacks stages {sorted(missing)}")

    def read[T: AtlasRecord](stage: str, name: str, model: type[T]) -> tuple[T, ...]:
        return store.read_output(receipts[stage], name, model)

    laws = read("law", "laws.jsonl", LawRecord)
    if len(laws) != 1:
        raise PipelineError(f"The collect run in {bundle} holds {len(laws)} laws, not one")
    return Collected(
        manifest=manifest,
        law=laws[0],
        documents=(
            *read("texts", "documents.jsonl", SourceDocument),
            *read("amendments", "documents.jsonl", SourceDocument),
            *read("asks", "documents.jsonl", SourceDocument),
        ),
        document_texts=(
            *read("texts", "document_texts.jsonl", DocumentText),
            *read("asks", "document_texts.jsonl", DocumentText),
        ),
        passages=read("asks", "passages.jsonl", Passage),
        actors=read("law", "actors.jsonl", Actor),
        amendments=read("amendments", "amendments.jsonl", Amendment),
        articles=read("texts", "articles.jsonl", ArticleVersion),
    )
