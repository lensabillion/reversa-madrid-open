"""Lineage assembly: one collected law in, the `lineage-1` view the explorer reads out.

This joins the lineage pieces in order over what `influence collect` wrote: verbatim adoption
(`services/lineage.py`) finds the final act's new wording and the amendments that carry it,
then origin (`services/origin.py`) finds the submissions that say the adopted wording, and the
submissions that say what amendments inserted whether or not it was adopted. Nothing here
matches, scores or ranks on its own; it only chooses the inputs and writes the result.

Only submissions are searched for origins: Have Your Say comments, their attachments and
public statements. The Commission's proposal and the final act are excluded, because the
final act holds every adopted phrase by construction and would be its own origin.

Cost: adoption plus the two origin scans, each linear in the words read (see those modules);
the view is written once, atomically. Semantic adoption (`lineage_semantic`) is not run here
yet, so the view holds verbatim matches only and says so.
"""

from datetime import datetime
from pathlib import Path

from pydantic import ValidationError

from influence.extraction.files import write_bytes_atomic
from influence.extraction.layout import procedure_slug
from influence.schemas.atlas import DocumentText, SourceDocument
from influence.schemas.lineage import (
    MIN_ADOPTED_RUN_WORDS,
    LineageLawList,
    LineageLawSummary,
    LineageView,
)
from influence.services.lineage import MIN_RARE_WORDS, Rarity, adopt
from influence.services.origin import (
    OriginError,
    find_origins,
    find_tabled_origins,
    submitters_from,
)
from influence.services.pipeline import Collected, PipelineError

VIEW_FILE = "lineage.json"
METHOD = "lineage-verbatim"
METHOD_REVISION = f"verbatim-{MIN_ADOPTED_RUN_WORDS}w-{MIN_RARE_WORDS}rare-v1"
SUBMISSION_KINDS = frozenset({"hys_feedback", "hys_attachment", "public_statement"})
LIMITATIONS = (
    f"Verbatim matching only: a phrase is a run of at least {MIN_ADOPTED_RUN_WORDS} identical "
    f"words holding at least {MIN_RARE_WORDS} of the law's rare words; reworded adoptions are "
    "not found yet.",
    "Shared wording is evidence of shared text, not of authorship: the final act is also shaped "
    "by the Council and the trilogues, and the same wording can come from a common draft, a "
    "coalition or a quotation.",
    "Credit splits each phrase equally among the holders of the amendments that carry it; it "
    "measures adopted wording, not political weight.",
    "These claims have not passed the human review gate (practice/lineage_review.py) yet.",
)


def build_lineage_view(collected: Collected, *, generated_at: datetime) -> LineageView:
    """Adoption, then origins of adopted and of tabled wording, as one validated view."""
    law = collected.law
    adoption = adopt(collected)
    rarity = Rarity.of(article.text for article in collected.articles)
    proposal_texts = tuple(
        article.text for article in collected.articles if article.stage == "proposal"
    )
    texts = {text.document_id: text for text in collected.document_texts}
    documents: tuple[tuple[SourceDocument, DocumentText], ...] = tuple(
        (document, texts[document.document_id])
        for document in collected.documents
        if document.source_kind in SUBMISSION_KINDS and document.document_id in texts
    )
    submitters = submitters_from(collected.passages, collected.actors)
    try:
        origins = find_origins(
            adoption.phrases,
            adoption.adoptions,
            documents,
            rarity=rarity,
            amendments={a.amendment_id: a for a in collected.amendments},
            submitters=submitters,
            proposal_texts=proposal_texts,
        )
        tabled = find_tabled_origins(
            collected.amendments,
            documents,
            rarity=rarity,
            adopted=adoption.phrases,
            submitters=submitters,
            proposal_texts=proposal_texts,
        )
        every_origin = (*origins, *tabled.origins)
        return LineageView(
            procedure_id=law.procedure_id,
            slug=procedure_slug(law.procedure_id),
            title=law.title,
            run_id=collected.manifest.run_id,
            generated_at=generated_at,
            method=METHOD,
            method_revision=METHOD_REVISION,
            coverage=law.coverage,
            counts=adoption.counts(
                documents_read=len(documents),
                documents_with_origin=len({origin.document_id for origin in every_origin}),
            ),
            adopted_phrases=adoption.phrases,
            tabled_phrases=tabled.phrases,
            adoptions=adoption.adoptions,
            origins=every_origin,
            credits=adoption.credits,
            limitations=(*LIMITATIONS, *adoption.limitations),
        )
    except (OriginError, ValidationError) as error:
        raise PipelineError(f"The lineage view cannot be built from this run: {error}") from error


def write_lineage_view(view: LineageView, bundle: Path) -> Path:
    path = bundle / VIEW_FILE
    write_bytes_atomic(path, view.model_dump_json().encode("utf-8"))
    return path


def _load(path: Path) -> LineageView:
    try:
        return LineageView.model_validate_json(path.read_bytes())
    except ValidationError as error:
        raise PipelineError(f"The lineage view at {path} is invalid: {error}") from error


def read_lineage_view(data_root: Path, slug: str) -> LineageView | None:
    """The law's last written lineage view, or None when that law has none."""
    path = data_root / "laws" / slug / VIEW_FILE
    return _load(path) if path.is_file() else None


def list_lineage_views(data_root: Path) -> LineageLawList:
    """Every law with a written lineage view, newest procedure first."""
    views = (
        _load(path) for path in sorted((data_root / "laws").glob(f"*/{VIEW_FILE}"), reverse=True)
    )
    return LineageLawList(
        laws=tuple(
            LineageLawSummary(
                slug=view.slug,
                procedure_id=view.procedure_id,
                title=view.title,
                run_id=view.run_id,
                adopted_phrases=view.counts.adopted_phrases,
                amendments_adopting=view.counts.amendments_adopting,
                documents_with_origin=view.counts.documents_with_origin,
            )
            for view in views
        )
    )
