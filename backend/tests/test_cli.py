"""Command-line usage errors: argparse rejects them with status 2 before any command runs."""

import pytest

from influence.cli import main


@pytest.mark.parametrize(
    ("value", "message"), [("0", "must be at least 1, got 0"), ("three", "not an integer: 'three'")]
)
def test_counts_must_be_positive_integers(
    value: str, message: str, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as caught:
        main(["report", "AI Act", "--links", value])
    assert caught.value.code == 2
    assert message in capsys.readouterr().err
