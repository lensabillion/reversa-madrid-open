"""Time a complete read-only browse of a local LobbyPlag snapshot.

Run with `uv run --directory backend --locked python tests/rehearse_demo.py DATA_DIR`.
The reported hashes identify the exact inputs; times describe this machine and run only.
"""

import argparse
import hashlib
import json
import os
import platform
from pathlib import Path
from time import perf_counter
from typing import cast

from fastapi.testclient import TestClient

from influence.api import create_app
from influence.repositories.lobbyplag import DemoRepository
from influence.schemas.scoring import ScoreRequest, ScoreResult, TextChange
from influence.services.demo import DemoService

DATA_FILES = ("amendments", "proposals", "plags", "documents", "lobbyists")
SCORE_REPETITIONS = 60


def file_hash(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def rehearse(directory: Path) -> dict[str, object]:
    """Browse every amendment and time its source scoring on a fixed input snapshot."""
    hashes = {f"{name}.json": file_hash(directory / f"{name}.json") for name in DATA_FILES}
    load_started = perf_counter()
    service = DemoService(DemoRepository.load(directory))
    load_seconds = perf_counter() - load_started

    browse_started = perf_counter()
    overview = service.overview()
    page = service.list_amendments("", 0, 100, False)
    if page.total != overview.amendments:
        raise RuntimeError("Amendment page total differs from dataset overview")
    organizations = service.organizations()
    scored = unscorable = omitted = details = 0
    sample: ScoreRequest | None = None
    for amendment_id in service.repository.amendments:
        detail = service.amendment(amendment_id)
        details += 1
        omitted += detail.total_sources - len(detail.sources)
        for source in detail.sources:
            if source.score is None:
                unscorable += 1
            else:
                scored += 1
                if sample is None:
                    sample = ScoreRequest(
                        amendment=TextChange(old=detail.text.old, new=detail.text.new),
                        submission=TextChange(old=source.text.old, new=source.text.new),
                    )
    browse_seconds = perf_counter() - browse_started
    if sample is None:
        raise RuntimeError("No scorable pair exists for the HTTP score rehearsal")
    if details != overview.amendments:
        raise RuntimeError("Browse did not visit every amendment")

    score_started = perf_counter()
    with TestClient(create_app(data_dir=directory)) as client:
        for _ in range(SCORE_REPETITIONS):
            response = client.post("/api/v1/score", json=sample.model_dump(mode="json"))
            if response.status_code != 200:
                raise RuntimeError(f"Score endpoint returned HTTP {response.status_code}")
            ScoreResult.model_validate_json(response.content)
    score_seconds = perf_counter() - score_started

    return {
        "input_sha256": hashes,
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python": platform.python_version(),
            "cpu_count": os.cpu_count(),
        },
        "counts": {
            "amendments": overview.amendments,
            "proposals": overview.proposals,
            "candidate_links": overview.candidate_links,
            "details_browsed": details,
            "organizations_browsed": len(organizations.items),
            "sources_scored": scored,
            "sources_unscorable": unscorable,
            "sources_omitted_by_detail_limit": omitted,
            "score_requests": SCORE_REPETITIONS,
        },
        "seconds": {
            "load": round(load_seconds, 6),
            "browse_all": round(browse_seconds, 6),
            "score_requests_60": round(score_seconds, 6),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "data_dir", type=Path, help="Directory containing five LobbyPlag JSON files"
    )
    args = parser.parse_args()
    directory = cast("Path", args.data_dir)
    print(json.dumps(rehearse(directory), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
