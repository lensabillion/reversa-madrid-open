"""Tests for `INFLUENCE_LOG_LEVEL`: the levels it sets, its failure and its one handler."""

import logging
from collections.abc import Iterator

import pytest

from influence.api import create_app
from influence.logging_setup import (
    APP_LOGGER,
    ENV_VAR,
    HANDLER_NAME,
    UVICORN_LOGGERS,
    LogLevelError,
    configure_logging,
)

TOUCHED = (APP_LOGGER, *UVICORN_LOGGERS)


@pytest.fixture(autouse=True)
def restore_loggers() -> Iterator[None]:
    """Put back each touched logger's level and handlers, so no other test sees a change."""
    saved = {
        name: (logging.getLogger(name).level, list(logging.getLogger(name).handlers))
        for name in TOUCHED
    }
    yield
    for name, (level, handlers) in saved.items():
        logger = logging.getLogger(name)
        logger.setLevel(level)
        logger.handlers[:] = handlers


def levels() -> dict[str, int]:
    return {name: logging.getLogger(name).level for name in TOUCHED}


def test_unset_variable_applies_info(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(ENV_VAR, raising=False)
    for name in TOUCHED:
        logging.getLogger(name).setLevel(logging.CRITICAL)

    assert configure_logging() == logging.INFO
    assert levels() == dict.fromkeys(TOUCHED, logging.INFO)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("DEBUG", logging.DEBUG),
        ("Info", logging.INFO),
        ("warning", logging.WARNING),
        (" error ", logging.ERROR),
        ("CriTical", logging.CRITICAL),
    ],
)
def test_each_name_sets_app_and_uvicorn_loggers_in_any_case(
    monkeypatch: pytest.MonkeyPatch, value: str, expected: int
) -> None:
    monkeypatch.setenv(ENV_VAR, value)

    assert configure_logging() == expected
    assert levels() == dict.fromkeys(TOUCHED, expected)


@pytest.mark.parametrize("value", ["bogus", "", "trace", "10"])
def test_invalid_value_stops_create_app_naming_variable_and_choices(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv(ENV_VAR, value)
    before = levels()

    with pytest.raises(LogLevelError) as raised:
        create_app()

    assert str(raised.value) == (
        f"INFLUENCE_LOG_LEVEL={value!r} is not a log level; "
        "use one of: debug, info, warning, error, critical"
    )
    assert levels() == before


def test_create_app_applies_the_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV_VAR, "warning")

    create_app()

    assert levels() == dict.fromkeys(TOUCHED, logging.WARNING)


def test_repeated_setup_keeps_one_handler(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV_VAR, "info")

    configure_logging()
    configure_logging()
    create_app()

    ours = [h for h in logging.getLogger(APP_LOGGER).handlers if h.name == HANDLER_NAME]
    assert len(ours) == 1


def test_debug_record_reaches_stderr_only_at_debug(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    logger = logging.getLogger(f"{APP_LOGGER}.probe")
    logging.getLogger(APP_LOGGER).handlers[:] = [
        h for h in logging.getLogger(APP_LOGGER).handlers if h.name != HANDLER_NAME
    ]

    monkeypatch.setenv(ENV_VAR, "info")
    configure_logging()
    logger.debug("hidden at info")
    monkeypatch.setenv(ENV_VAR, "debug")
    configure_logging()
    logger.debug("shown at debug")

    err = capsys.readouterr().err
    assert "hidden at info" not in err
    assert " DEBUG influence.probe: shown at debug\n" in err
