"""The lineage views `influence lineage` has written, read back for the API.

`services/lineage_assembly.py` builds and writes `lineage.json`; this only reads it, so the
routes stay thin and a file that no longer fits the contract is an explicit error.
"""

from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from influence.schemas.lineage import LineageLawList, LineageLawSummary, LineageView
from influence.services.lineage_assembly import VIEW_FILE
from influence.services.pipeline import PipelineError


@dataclass(frozen=True)
class ViewStat:
    """What identifies one written view without reading it: `write_lineage` replaces the file
    by an atomic rename, so a rewrite always yields a new inode with a fresh modification
    time, and (size, mtime in nanoseconds) changes whenever the content does."""

    slug: str
    size: int
    mtime_ns: int


def _stat(path: Path) -> ViewStat:
    stat = path.stat()
    return ViewStat(slug=path.parent.name, size=stat.st_size, mtime_ns=stat.st_mtime_ns)


def _view_paths(data_root: Path) -> list[Path]:
    return sorted((data_root / "laws").glob(f"*/{VIEW_FILE}"), reverse=True)


def view_stat(data_root: Path, slug: str) -> ViewStat | None:
    """The law's view file stat, or None when that law has none; the file is not read."""
    path = data_root / "laws" / slug / VIEW_FILE
    return _stat(path) if path.is_file() else None


def view_stats(data_root: Path) -> tuple[ViewStat, ...]:
    """The stat of every view `list_lineage_views` lists, in the same order, unread."""
    return tuple(_stat(path) for path in _view_paths(data_root))


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
    views = (_load(path) for path in _view_paths(data_root))
    return LineageLawList(
        laws=tuple(
            LineageLawSummary(
                slug=view.slug,
                procedure_id=view.procedure_id,
                title=view.title,
                run_id=view.run_id,
                status=view.status,
                adopted_phrases=view.counts.adopted_phrases,
                amendments_adopting=view.counts.amendments_adopting,
                documents_with_origin=view.counts.documents_with_origin,
            )
            for view in views
        )
    )
