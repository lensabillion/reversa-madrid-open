"""Atlas records on disk, and the stage receipts that make a law's run resumable.

A law's bundle lives under `data/laws/<slug>/`. Each stage writes its JSON Lines files
into `stages/<stage>/<input hash>/` and then a receipt beside them, so a rerun with the
same inputs, code revision and configuration finds the receipt and skips the work, and a
changed input simply lands in a new directory. `manifest.json` is written last, after
every file a receipt names has been re-read and re-hashed: an interrupted or corrupted
run never leaves a manifest that claims to be complete.
"""

import hashlib
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from influence.extraction.files import write_bytes_atomic
from influence.schemas.atlas import AtlasRecord, OutputFile, RunManifest, StageReceipt, StageStatus

RECEIPT_NAME = "receipt.json"
MANIFEST_NAME = "manifest.json"
_FIELD_SEPARATOR = b"\x00"


class RecordError(ValueError):
    """A record file, receipt or manifest is unreadable or does not match its hash."""


def encode_records(records: Iterable[AtlasRecord]) -> tuple[bytes, int]:
    """JSON Lines bytes and the record count."""
    lines = [record.model_dump_json() for record in records]
    return "".join(f"{line}\n" for line in lines).encode("utf-8"), len(lines)


def read_records[T: AtlasRecord](path: Path, model: type[T]) -> Iterator[T]:
    """Validate every line, naming the line number of the first failure."""
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as error:
        raise RecordError(f"Cannot read {path}") from error
    for number, line in enumerate(content.splitlines(), start=1):
        try:
            yield model.model_validate_json(line)
        except ValidationError as error:
            raise RecordError(f"{path.name} line {number} is invalid: {error}") from error


def input_hash(*parts: str) -> str:
    """SHA-256 over the parts, separated so ("ab", "c") and ("a", "bc") differ."""
    digest = hashlib.sha256()
    for part in parts:
        digest.update(part.encode("utf-8"))
        digest.update(_FIELD_SEPARATOR)
    return digest.hexdigest()


def _file_sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as error:
        raise RecordError(f"Cannot read {path}") from error


@dataclass(frozen=True)
class StageStore:
    """One law's bundle directory. Receipt paths are relative to it, with `/` separators."""

    root: Path

    def stage_directory(self, stage: str, inputs: str) -> Path:
        return self.root / "stages" / stage / inputs

    def output_path(self, output: OutputFile) -> Path:
        return self.root / output.path

    def verify(self, receipt: StageReceipt) -> None:
        """Raise unless every output the receipt names exists with the recorded hash."""
        for output in receipt.outputs:
            if _file_sha256(self.output_path(output)) != output.sha256:
                raise RecordError(f"{output.path} no longer matches its receipt")

    def load(self, stage: str, inputs: str) -> StageReceipt | None:
        """The receipt for these inputs when its outputs are intact, otherwise None.

        A missing receipt and a receipt whose files changed both mean "run the stage":
        the caller never has to tell them apart.
        """
        path = self.stage_directory(stage, inputs) / RECEIPT_NAME
        try:
            receipt = StageReceipt.model_validate_json(path.read_bytes())
            self.verify(receipt)
        except OSError, ValidationError, RecordError:
            return None
        return receipt.model_copy(update={"status": "reused"})

    def save(
        self,
        stage: str,
        inputs: str,
        files: Mapping[str, Iterable[AtlasRecord]],
        *,
        status: StageStatus,
        seconds: float,
        counts: Mapping[str, int] | None = None,
        errors: Iterable[str] = (),
    ) -> StageReceipt:
        """Write each record file, then the receipt: the receipt marks the stage done."""
        directory = self.stage_directory(stage, inputs)
        outputs: list[OutputFile] = []
        for name, records in files.items():
            content, count = encode_records(records)
            write_bytes_atomic(directory / name, content)
            outputs.append(
                OutputFile(
                    path=(directory / name).relative_to(self.root).as_posix(),
                    sha256=hashlib.sha256(content).hexdigest(),
                    records=count,
                )
            )
        receipt = StageReceipt(
            stage=stage,
            status=status,
            input_hash=inputs,
            seconds=seconds,
            counts=dict(counts or {}),
            errors=tuple(errors),
            outputs=tuple(outputs),
        )
        write_bytes_atomic(directory / RECEIPT_NAME, receipt.model_dump_json().encode("utf-8"))
        return receipt

    def read_output[T: AtlasRecord](
        self, receipt: StageReceipt, name: str, model: type[T]
    ) -> tuple[T, ...]:
        """The records of the receipt's output file called `name`."""
        for output in receipt.outputs:
            if Path(output.path).name == name:
                return tuple(read_records(self.output_path(output), model))
        raise RecordError(f"Stage {receipt.stage} has no output named {name}")

    def publish(self, manifest: RunManifest) -> Path:
        """Re-verify every output, then write the run's manifest and make it current."""
        for receipt in manifest.stages:
            self.verify(receipt)
        content = manifest.model_dump_json(indent=2).encode("utf-8")
        write_bytes_atomic(self.root / "runs" / f"{_run_file(manifest.run_id)}.json", content)
        current = self.root / MANIFEST_NAME
        write_bytes_atomic(current, content)
        return current

    def current(self) -> RunManifest | None:
        """The last published manifest, or None when the law has never completed a run."""
        try:
            content = (self.root / MANIFEST_NAME).read_bytes()
        except OSError:
            return None
        try:
            return RunManifest.model_validate_json(content)
        except ValidationError as error:
            raise RecordError(f"The manifest in {self.root} is invalid: {error}") from error


def _run_file(run_id: str) -> str:
    return "".join(character if character.isalnum() else "-" for character in run_id)
