"""
Gate probes: prove that the effective Ruff and basedpyright configuration still rejects
known violations. A gate whose configuration silently stopped applying (a section renamed,
a rule family dropped, a mode downgraded, a path excluded) keeps exiting 0; these tests
fail instead.

The probe sources are strings, so they are never inside the real lint or type scope. The
tools are the versions uv.lock pins, run from the backend directory as the gates run them.
"""

import json
import subprocess
import sys
from pathlib import Path
from textwrap import dedent

BACKEND = Path(__file__).resolve().parents[1]
# Not resolved: the virtual environment's python is a symlink into uv's Python install,
# which does not contain the project's tools.
VENV_BIN = Path(sys.executable).parent

RUFF_PROBE = dedent("""
    from .api import create_app


    def collect(items=[]):
        if items: return create_app
    """).lstrip()

TYPE_PROBE = dedent("""
    def echo(value):
        return value
    """).lstrip()


def run_tool(tool: str, *args: str, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    # Deliberate exception, not debt: the executable comes from this project's own virtual
    # environment and every argument is written in this file, so S603 cannot apply.
    return subprocess.run(  # noqa: S603
        [str(VENV_BIN / tool), *args],
        input=stdin,
        capture_output=True,
        text=True,
        check=False,
        cwd=BACKEND,
    )


def test_ruff_rejects_known_violations_in_src() -> None:
    # Linted as if it were a file under src/influence/. --force-exclude applies the
    # exclude settings to that path too, so a config that excluded src/ would fail here.
    result = run_tool(
        "ruff",
        "check",
        "--force-exclude",
        "--output-format=json",
        "--stdin-filename=src/influence/gate_probe.py",
        "-",
        stdin=RUFF_PROBE,
    )

    assert result.returncode == 1, result.stderr
    codes = {d["code"] for d in json.loads(result.stdout)}
    # Ruff's built-in default rules include B006 but not E701 or TID252, so those two
    # prove the root ruff.toml reaches this path through `extend`. TID252 on a sibling
    # import (`.api`, not `..api`) proves `ban-relative-imports = "all"` is applied.
    assert {"B006", "E701", "TID252"} <= codes


def test_basedpyright_strict_mode_rejects_unannotated_parameter(tmp_path: Path) -> None:
    probe = tmp_path / "type_probe.py"
    probe.write_text(TYPE_PROBE)

    result = run_tool("basedpyright", "--outputjson", str(probe))

    assert result.returncode == 1, result.stderr
    report = json.loads(result.stdout)
    assert report["summary"]["filesAnalyzed"] == 1
    severities = {d["rule"]: d["severity"] for d in report["generalDiagnostics"]}
    # "standard" mode does not report this rule, and basedpyright's no-config default
    # ("recommended") reports it as a warning: only the project's strict mode errors.
    assert severities["reportMissingParameterType"] == "error"


def test_basedpyright_analyzes_every_python_file_in_src_and_tests() -> None:
    # basedpyright exits 0 after analyzing zero files, so an over-broad `exclude` would
    # leave the type gate green while it checks nothing.
    result = run_tool("basedpyright", "--outputjson")

    report = json.loads(result.stdout)
    python_files = [*(BACKEND / "src").rglob("*.py"), *(BACKEND / "tests").rglob("*.py")]
    assert report["summary"]["filesAnalyzed"] == len(python_files)
