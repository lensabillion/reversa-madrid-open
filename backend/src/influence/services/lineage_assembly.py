"""Lineage assembly: one law's adoption and origins as the `LineageView` in `lineage.json`.

`influence lineage <law>` collects the law, then calls `build_lineage` and `write_lineage`.
Adoption (`services/lineage.py`) needs the proposal and the final act; without either the
view says "unknown" with the reason and searches no origins. Origins
(`services/origin.py`) are searched only in the law's consultation documents that have
text: adopted phrases first, then inserted wording whether or not it was adopted. A
document counts toward `documents_with_origin` only through a match that counts as an
origin (dated before every carrying amendment, and not a citation). With a Jev `judge`,
reworded origins (`services/lineage_jev.py`) are added for the adopting amendments: BM25
shortlists passages and Jev judges each pair.

The cost is that of the pieces: adoption is linear in the law's words plus one diff per
amendment, and each origin search is linear in the documents' words.
"""

from datetime import datetime
from pathlib import Path

from influence.extraction.files import write_bytes_atomic
from influence.extraction.layout import procedure_slug
from influence.schemas.lineage import LineageView, OriginMatch, TabledPhrase
from influence.services.collected import Collected
from influence.services.jev_judge import JevJudge
from influence.services.lineage import Rarity, adopt
from influence.services.lineage_jev import reworded_origins
from influence.services.origin import (
    CONSULTATION_KINDS,
    find_origins,
    find_tabled_origins,
    submitters_from,
)

VIEW_FILE = "lineage.json"
METHOD = "verbatim-adopted-phrases"
METHOD_REVISION = "lineage-2.0"
VERBATIM_ONLY = "Verbatim wording only: a request the final act says in other words is not traced."
LIMITATIONS = (
    VERBATIM_ONLY,
    "Shared wording is evidence, not proof of authorship: the Council, the trilogues, a "
    "common draft or a coalition can explain the same words.",
    "Every holder of a phrase is credited with the whole phrase (no fractional credit); a "
    "phrase with several holders is joint. Members are ranked by their rate per amendment "
    "tabled.",
)


REWORDED = (
    "Reworded origins are Jev's judgement on BM25's shortlist of passages per adopting "
    "amendment: a request that shares none of the amendment's rare words is not judged, and "
    "adoption itself (amendment to final act) is still traced word for word."
)


def build_lineage(
    collected: Collected, *, generated_at: datetime, judge: JevJudge | None = None
) -> LineageView:
    """Adoption, then origins in the law's consultation documents, as one `LineageView`."""
    adoption = adopt(collected)
    texts = {text.document_id: text for text in collected.document_texts}
    documents = [
        (document, texts[document.document_id])
        for document in collected.documents
        if document.source_kind in CONSULTATION_KINDS and document.document_id in texts
    ]
    notes = [*LIMITATIONS, *adoption.limitations]
    read: int | None = None
    with_origin: int | None = None
    origins: tuple[OriginMatch, ...] = ()
    tabled: tuple[TabledPhrase, ...] = ()
    if adoption.status == "unknown":
        notes.append("Origins were not searched: adoption could not be computed.")
    elif not documents:
        notes.append("No consultation document text was collected; origins are unknown.")
    else:
        rarity = Rarity.of(article.text for article in collected.articles)
        submitters = submitters_from(collected.passages, collected.actors)
        adopted = find_origins(
            adoption.phrases,
            adoption.adoptions,
            documents,
            rarity=rarity,
            amendments={amendment.amendment_id: amendment for amendment in collected.amendments},
            submitters=submitters,
        )
        others = find_tabled_origins(
            collected.amendments,
            documents,
            rarity=rarity,
            adopted=adoption.phrases,
            submitters=submitters,
            proposal_texts=[a.text for a in collected.articles if a.stage == "proposal"],
        )
        origins = (*adopted, *others.origins)
        if judge is not None:
            known = frozenset(
                (origin.document_id, amendment_id)
                for origin in adopted
                for amendment_id in origin.amendment_ids
            )
            reworded, note = reworded_origins(
                collected, adoption.adoptions, judge, submitters=submitters, known=known
            )
            origins = (*origins, *reworded)
            notes[notes.index(VERBATIM_ONLY)] = REWORDED
            notes.append(note)
        tabled = others.phrases
        read = len(documents)
        with_origin = len({origin.document_id for origin in origins if origin.counts_as_origin})
    law = collected.law
    return LineageView(
        procedure_id=law.procedure_id,
        slug=procedure_slug(law.procedure_id),
        title=law.title,
        run_id=collected.manifest.run_id,
        generated_at=generated_at,
        method=METHOD,
        method_revision=METHOD_REVISION,
        coverage=law.coverage,
        status=adoption.status,
        reason=adoption.reason,
        counts=adoption.counts(documents_read=read, documents_with_origin=with_origin),
        adopted_phrases=adoption.phrases,
        tabled_phrases=tabled,
        adoptions=adoption.adoptions,
        origins=origins,
        credits=adoption.credits,
        limitations=tuple(notes),
    )


def write_lineage(view: LineageView, bundle: Path) -> Path:
    """Write `lineage.json` into the law's bundle atomically, and return its path."""
    path = bundle / VIEW_FILE
    write_bytes_atomic(path, view.model_dump_json().encode("utf-8"))
    return path
