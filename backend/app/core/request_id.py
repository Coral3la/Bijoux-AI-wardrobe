"""One id per request, on the response and on every log line it produced.

Infrastructure rather than domain, and it holds itself to `core/short_id.py`'s
own constraint: no ORM, no session, no settings. Only `app/main.py` imports it,
once, at wiring time. **No route ever asks for the id and no function signature
gains a parameter** — the value travels in a `ContextVar` and is read by a
logging filter, which is the whole reason this is worth having: a correlation id
threaded by hand through `suggest_look` → `_judged` → `suggest_looks` would be an
argument on three functions that have nothing to do with logging.

The value is a `short_id`. Its alphabet already drops both halves of every
confusable pair, which is exactly what a code read off a screen and typed into a
`grep` needs; that the same generator numbers items is a coincidence of
requirements, not a shared meaning.
"""

import logging
import re
from contextvars import ContextVar

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.short_id import generate_short_id

HEADER_NAME = "X-Request-ID"

# An inbound header is a string a caller chose, and it reaches two places that
# treat strings as structure: a log line and a response header. A newline in it
# forges a log record and a carriage return forges a header, so the id is
# accepted only when it is already the shape we would have generated, and
# replaced rather than sanitised when it is not. Length is bounded for the same
# reason the pattern is: neither is a guess about a caller, both are limits on
# what this process will repeat back.
_ACCEPTABLE = re.compile(r"\A[A-Za-z0-9_-]{1,64}\Z")

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)


def current_request_id() -> str | None:
    """The id of the request on this task, or `None` outside one.

    `None` is a real answer rather than a missing one: `run_startup_sweep` logs
    from the lifespan, where there is no request and inventing an id would
    suggest there was.
    """
    return _request_id.get()


class RequestIdFilter(logging.Filter):
    """Stamps the id on every record that has one to stamp.

    A filter rather than a formatter, so the id arrives as a record attribute:
    `core/logging.py`'s `_RESERVED` already means "not on a freshly built record,
    therefore from `extra=`, therefore worth printing", and **both** formatters
    pick it up under that one rule without either being taught this module
    exists.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        request_id = _request_id.get()
        if request_id is not None:
            record.request_id = request_id
        return True


def _inbound(scope: Scope) -> str | None:
    for name, value in scope["headers"]:
        if name == b"x-request-id":
            candidate = value.decode("latin-1")
            return candidate if _ACCEPTABLE.fullmatch(candidate) else None
    return None


class RequestIdMiddleware:
    """Pure ASGI, not `BaseHTTPMiddleware`.

    `BaseHTTPMiddleware` runs the downstream app in a separate task, and a
    `ContextVar` set in the middleware is not visible to a route that way round.
    That is the failure this class exists to avoid, and it is the reason the
    plainer-looking base class is the wrong one here.

    **A bare `500` carries no header.** An exception that escapes the route
    propagates through `__call__` before any response is sent, and Starlette's
    `ServerErrorMiddleware` — which sits outside every middleware added with
    `add_middleware` — answers it with the original `send`. The log line for that
    request still carries the id, because the filter reads the `ContextVar` and
    not the response; only the client loses it. Every answer the application
    itself produces, error envelopes included, passes through `send_with_id`.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = _inbound(scope) or generate_short_id()
        token = _request_id.set(request_id)

        async def send_with_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)[HEADER_NAME] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            _request_id.reset(token)
