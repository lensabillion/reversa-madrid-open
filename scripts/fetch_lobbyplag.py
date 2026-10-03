"""
Download the LobbyPlag snapshot the practice harness measures, and verify it.

LobbyPlag (https://github.com/lobbyplag/lobbyplag-data) is public data of 2013 GDPR
amendments matched to lobbyist proposals. The practice loop uses it for labelled pairs.
The files go under `data/lobbyplag/`, which is never committed, so this script is how
anyone reproduces the snapshot.

The download is pinned to one commit, and each file is checked against the SHA-256 digest
recorded in `backend/evaluation/practice-results.json`. A file that does not match is
deleted and the script fails, so a moved branch or a tampered mirror cannot change what
the evaluation measures. A file that already matches is left alone and nothing is fetched.

Run through `make fetch-lobbyplag`.
"""

import hashlib
import sys
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DESTINATION = REPO_ROOT / "data" / "lobbyplag"
COMMIT = "6880188eb528b5eb00cf7efdadfccdd3d5e73795"
BASE_URL = f"https://raw.githubusercontent.com/lobbyplag/lobbyplag-data/{COMMIT}/data"
# The same digests as `input_sha256` in backend/evaluation/practice-results.json.
SHA256 = {
    "amendments.json": "1ef4693a2b6e4101678f4fa0dc73c58d037b6a465ecbbd317d4e19b307ad1d9a",
    "documents.json": "7f138e82d581fa5838119c272c93badf1d9c4d30ca3baf4d473a1ad25853f814",
    "lobbyists.json": "e4613e538dab2de0c71fbb165c798f0c6e132aa0c42f17da8b28788c5382c323",
    "plags.json": "fb21f05cc0c372fdc60a2117219262cb7b00d52196ebbb118b29fc786dfb9a3c",
    "proposals.json": "5ba1a001c62f88d40d1a1ae29929eaca9177c1b579e36b65b0065f7e67f587af",
}
TIMEOUT_SECONDS = 60


def digest(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def fetch(name: str, destination: Path) -> str:
    """Make `destination/name` hold the pinned file; return what was done."""
    target = destination / name
    if target.is_file() and digest(target) == SHA256[name]:
        return "present"
    staged = target.with_name(f".{name}.download")
    try:
        with urllib.request.urlopen(f"{BASE_URL}/{name}", timeout=TIMEOUT_SECONDS) as response:  # noqa: S310
            staged.write_bytes(response.read())
        if digest(staged) != SHA256[name]:
            raise SystemExit(f"{name}: downloaded file does not match its pinned SHA-256")
        staged.replace(target)
    finally:
        staged.unlink(missing_ok=True)
    return "downloaded"


def main(argv: list[str]) -> int:
    destination = Path(argv[0]) if argv else DEFAULT_DESTINATION
    destination.mkdir(parents=True, exist_ok=True)
    for name in SHA256:
        print(f"{name}: {fetch(name, destination)}")
    print(f"LobbyPlag snapshot at commit {COMMIT[:7]} is in {destination}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
