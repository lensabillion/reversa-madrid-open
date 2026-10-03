"""Small invented records exercise the public data shape without redistributing source data."""

import json
from pathlib import Path


def write_dataset(
    directory: Path, records: dict[str, list[dict[str, object]]] | None = None
) -> dict[str, list[dict[str, object]]]:
    if records is None:
        records = {
            "amendments": [
                {
                    "uid": "a1",
                    "committee": "itre",
                    "number": 616,
                    "authors": ["Ada Example", "Ada Example"],
                    "relations": ["a26p1"],
                    "text": [
                        {"lang": "fr", "old": "Le texte", "new": "Le nouveau texte"},
                        {
                            "lang": "en",
                            "old": "The controller shall report.",
                            "new": "The controller may report.",
                        },
                    ],
                },
                {
                    "uid": "a2",
                    "committee": "libe",
                    "number": 42,
                    "authors": [],
                    "relations": [],
                    "text": [{"lang": "es", "old": "Texto", "new": "Otro texto"}],
                },
            ],
            "proposals": [
                {
                    "uid": "p1",
                    "doc_uid": "d1",
                    "page": "17",
                    "text": {
                        "old": "The controller shall report.",
                        "new": "The controller may report.",
                    },
                },
                {
                    "uid": "p2",
                    "doc_uid": "d2",
                    "page": "2-3",
                    "text": {
                        "old": "The controller shall report.",
                        "new": "The controller must report immediately.",
                    },
                },
            ],
            "plags": [
                {
                    "uid": "z-verified",
                    "amendment": "a1",
                    "proposal": "p1",
                    "verified": True,
                    "match": 1,
                    "processing": {"checked": 0, "verified": 0},
                },
                {
                    "uid": "a-unverified",
                    "amendment": "a1",
                    "proposal": "p2",
                    "verified": False,
                    "match": 0.5,
                    "processing": {"checked": 2, "verified": 0},
                },
            ],
            "documents": [
                {"uid": "d1", "filename": "public-paper.pdf", "lobbyist": "o1", "lang": "en"},
                {"uid": "d2", "filename": "other-paper.pdf", "lobbyist": "o2", "lang": "en"},
                {"uid": "d3", "filename": "unattributed.pdf", "lobbyist": None, "lang": "en"},
            ],
            "lobbyists": [
                {"id": "o1", "title": "Example association"},
                {"id": "o2", "title": "Other association"},
                {"id": "o3", "title": "No observed proposals"},
            ],
        }
    for name, rows in records.items():
        (directory / f"{name}.json").write_text(json.dumps(rows), encoding="utf-8")
    return records
