"""
Validate every softschema research catalog under `docs/research/`.

A catalog is any `*.yaml` file there that is not a compiled schema (`*.schema.yaml`).
The check fails when the validator accepts a known-bad fixture, when no catalog is found,
or when any catalog is invalid, so a broken validator or an empty run can never pass.

Run through `make check-docs`, which pins the validator version.
"""

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CATALOG_ROOT = REPO_ROOT / "docs" / "research"
KNOWN_BAD = REPO_ROOT / "scripts" / "fixtures" / "invalid-catalog.yaml"
# The validator CLI is installed next to the interpreter running this script.
SOFTSCHEMA = Path(sys.executable).with_name("softschema")


def find_catalogs(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.yaml") if not p.name.endswith(".schema.yaml"))


def validate(path: Path) -> str | None:
    """
    Return `None` if `path` is a valid catalog, otherwise a one-line reason.
    """
    result = subprocess.run(
        [str(SOFTSCHEMA), "validate", str(path)], capture_output=True, text=True, check=False
    )
    try:
        report = json.loads(result.stdout)
    except json.JSONDecodeError:
        return f"validator exited {result.returncode} without a report: {result.stderr.strip()}"
    if result.returncode == 0 and report.get("outcome") == "valid":
        return None
    errors = report.get("structural", {}).get("errors") or report.get("semantic", {}).get("errors")
    if errors:
        first = errors[0]
        return f"{'/'.join(map(str, first.get('path', [])))}: {first.get('message', first)}"
    return f"outcome {report.get('outcome')!r}, exit {result.returncode}"


def main() -> int:
    if validate(KNOWN_BAD) is None:
        print(f"FAIL: validator accepted the known-bad {KNOWN_BAD.relative_to(REPO_ROOT)}")
        return 1
    catalogs = find_catalogs(CATALOG_ROOT)
    if not catalogs:
        print(f"FAIL: no catalogs found under {CATALOG_ROOT.relative_to(REPO_ROOT)}")
        return 1
    failures = 0
    for path in catalogs:
        reason = validate(path)
        print(f"{'ok  ' if reason is None else 'FAIL'} {path.relative_to(REPO_ROOT)}")
        if reason is not None:
            print(f"     {reason}")
            failures += 1
    print(f"{len(catalogs) - failures} of {len(catalogs)} catalogs valid")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
