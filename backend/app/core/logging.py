import json
import logging
import sys
from typing import Any, override

from app.core.config import settings
from app.core.request_id import RequestIdFilter

# Anything not on a freshly built record came from extra={...} and is worth logging.
_RESERVED = frozenset(
    logging.LogRecord(
        name="", level=0, pathname="", lineno=0, msg="", args=(), exc_info=None
    ).__dict__
) | {"message", "asctime"}


def _extras(record: logging.LogRecord) -> dict[str, Any]:
    return {key: value for key, value in record.__dict__.items() if key not in _RESERVED}


class JsonFormatter(logging.Formatter):
    @override
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        payload.update(_extras(record))
        return json.dumps(payload, default=str)


class TextFormatter(logging.Formatter):
    """The development formatter, and the reason `extra={...}` is worth writing.

    Until this existed the development format string named four fields and
    printed exactly those, so **every `extra=` in the backend was dropped in the
    one environment where somebody is watching the terminal**: the rule a look
    violated, the exception behind an unusable stylist answer, the coordinates a
    forecast failed for. All of them were logged, none of them were printed, and
    `JsonFormatter` carried them in production only — where nobody is reading a
    stream to find out why a button just failed.

    `formatMessage` rather than `format`, so the extras land on the message line
    and an exception's traceback still comes last. `_extras` rather than a second
    comprehension, so the two formatters cannot come to disagree about what
    counts as an extra. `@override` rather than a `noqa` for the camel-case name:
    it is the reason the name is spelled that way, where the suppression would
    only have been a note that ruff had been told to stop asking.
    """

    @override
    def formatMessage(self, record: logging.LogRecord) -> str:
        line = super().formatMessage(record)
        extras = _extras(record)
        if not extras:
            return line
        return f"{line}  " + " ".join(f"{key}={value!r}" for key, value in extras.items())


def configure_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    if settings.is_production:
        handler.setFormatter(JsonFormatter())
        level = logging.INFO
    else:
        handler.setFormatter(
            TextFormatter(
                "%(asctime)s  %(levelname)-8s %(name)s  %(message)s",
                datefmt="%H:%M:%S",
            )
        )
        level = logging.DEBUG

    # On the handler rather than on the root logger: a filter on a logger is not
    # consulted for records that propagate up from a child, and uvicorn's three
    # loggers below are exactly that case.
    handler.addFilter(RequestIdFilter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    for name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True
