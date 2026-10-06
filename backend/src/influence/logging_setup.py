"""Set how much the API logs from one environment variable, `INFLUENCE_LOG_LEVEL`.

A host (the container, compose, a platform's settings page) has one knob. It governs two
families of loggers that otherwise answer to nobody:

- the application's own, `influence` and every `influence.*` child, which have no handler
  of their own, so without this their records fall to Python's last-resort handler and
  anything below WARNING is lost;
- uvicorn's, which uvicorn configures from its `--log-level` option before it imports the
  app. Uvicorn imports the app before it logs "Started server process", so levels set here
  govern every line it writes while serving.

Third-party libraries' loggers are left alone: a debug level for the API should not turn on
debug output from every library it imports.
"""

import logging
import os
import sys
from typing import Final

ENV_VAR: Final = "INFLUENCE_LOG_LEVEL"
DEFAULT_LEVEL: Final = "info"
# The standard library's names, lower-cased as uvicorn's `--log-level` spells them.
# Uvicorn's extra "trace" is left out: no application logger emits it.
LEVELS: Final = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
    "critical": logging.CRITICAL,
}
APP_LOGGER: Final = "influence"
# The loggers uvicorn's own `--log-level` sets (uvicorn/config.py, configure_logging),
# plus their parent "uvicorn", so a child uvicorn adds later inherits the same level.
UVICORN_LOGGERS: Final = ("uvicorn", "uvicorn.error", "uvicorn.access", "uvicorn.asgi")
# One line per record, naming the logger so a host's log search can filter by module.
LOG_FORMAT: Final = "%(asctime)s %(levelname)s %(name)s: %(message)s"
# Marks the handler this module installs, so a second call finds it instead of adding
# another and printing every record twice.
HANDLER_NAME: Final = "influence-stderr"


class LogLevelError(ValueError):
    """`INFLUENCE_LOG_LEVEL` holds a value that is not a level name.

    Startup stops rather than falling back to the default: a host that asked for debug
    output and silently got info would be misled about what the logs can show.
    """


def log_level_from_env() -> int:
    """The level `INFLUENCE_LOG_LEVEL` names, case-insensitively, or INFO when it is unset."""
    raw = os.environ.get(ENV_VAR, DEFAULT_LEVEL)
    level = LEVELS.get(raw.strip().lower())
    if level is None:
        accepted = ", ".join(LEVELS)
        message = f"{ENV_VAR}={raw!r} is not a log level; use one of: {accepted}"
        raise LogLevelError(message)
    return level


def configure_logging() -> int:
    """Apply `INFLUENCE_LOG_LEVEL` to the application's and uvicorn's loggers.

    Safe to call more than once (every `create_app` call does): the stderr handler is
    added only when the `influence` logger does not already carry it. The handler sits on
    `influence`, not the root logger, so a host's own root configuration is untouched and
    records still propagate to it. Returns the level applied.
    """
    level = log_level_from_env()
    app_logger = logging.getLogger(APP_LOGGER)
    app_logger.setLevel(level)
    if not any(handler.name == HANDLER_NAME for handler in app_logger.handlers):
        handler = logging.StreamHandler(sys.stderr)
        handler.name = HANDLER_NAME
        handler.setFormatter(logging.Formatter(LOG_FORMAT))
        app_logger.addHandler(handler)
    for name in UVICORN_LOGGERS:
        logging.getLogger(name).setLevel(level)
    return level
