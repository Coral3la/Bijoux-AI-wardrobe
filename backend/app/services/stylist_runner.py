"""One model call judged, and the second one the first may have earned.

`suggest_looks` asks and `validate_look_response` judges; neither retries, and
`DECISIONS.md` 164 put the retry in `POST /looks/suggest` because that route was
the only thing holding the wardrobe and the context a second call needs. Task
4.3 gives it a second holder — `pack_trip` calls the same model with the same
two arguments — so the loop moved here rather than being written twice.

**This module is deliberately free of HTTP.** It raises no `ApiError`, imports
no `fastapi`, and holds no `Session`, so a service may import it: `packing.py`
does, and a service that imported `app.api.v1` instead would invert the
direction `01-ARCHITECTURE.md` states in one line. What is left in the route
layer is `_stylist_shared.py`'s pair — which wardrobe to send, and what a
failure is worth on the wire. `DECISIONS.md` 197.

Both context types travel through untouched — `AnyContext` since 4.3, when
`pack_trip` became the second caller. This module never reads a field on either
one; it counts calls and logs, and the two shapes are `stylist.py`'s business.

`judged` propagates whatever `suggest_looks` raises: a `ValueError` when no
usable answer arrived, a provider exception when none arrived at all. Both
callers map those to `502 stylist_failed` themselves, which is 164's split
unchanged — this module decides how many times to ask, not what a failure means.
"""

import logging
import time
from collections.abc import Sequence

from app.core.config import settings
from app.schemas.item import ItemResponse
from app.services.stylist import (
    AnyContext,
    LookValidation,
    suggest_looks,
    validate_look_response,
)

logger = logging.getLogger(__name__)


async def attempt(
    wardrobe: Sequence[ItemResponse],
    context: AnyContext,
    number: int,
    correction: str | None = None,
) -> LookValidation:
    """One model call, judged, with everything a failure would need reported.

    Both attempts log at `INFO` rather than only the failing one, because the
    question this path could not answer before was never "did it fail" — the
    `502` already said that — but "how often, how slowly, and against how big a
    wardrobe". A line only on failure cannot answer any of the three, since it
    has nothing to be compared against.

    `item_ids` is logged flat because rule 1 is the rule that fires most and the
    id it rejected is the whole diagnosis: an invented id and a real id the model
    shifted the case of are the same message and different bugs.

    The parameter is `number` rather than `attempt`, which is what it was called
    while this function was `_attempt` in the route: a public function cannot
    take a parameter that shadows its own name. The log key stays `attempt`, so
    nothing a reader greps for moved.
    """
    started = time.monotonic()
    validation = validate_look_response(
        await suggest_looks(wardrobe, context, correction=correction), wardrobe, context
    )
    logger.info(
        "Stylist attempt finished",
        extra={
            "attempt": number,
            "elapsed_ms": round((time.monotonic() - started) * 1000),
            # The model actually used, not the pin: `.env` can and does override
            # `OPENAI_STYLIST_MODEL`, and a rejection rate is meaningless beside
            # the name of a model that was not called.
            "model": settings.OPENAI_STYLIST_MODEL,
            "wardrobe_items": len(wardrobe),
            "violation": validation.violation,
            "item_ids": [
                item_id for look in validation.response.looks for item_id in look.item_ids
            ],
        },
    )
    return validation


async def judged(wardrobe: Sequence[ItemResponse], context: AnyContext) -> LookValidation:
    """One call, and a second one only when the first broke a named rule.

    The retry exists to carry a violation back to the model, so a failure with
    no violation to name does not spend it: a `ValueError` means no usable
    answer arrived and an `OpenAIError` means none arrived at all, and both are
    `502` at the caller without a second trip through the whole wardrobe.
    `03-AI-CONTRACTS.md` says the same thing about a timeout — "the request is
    not retried automatically". `DECISIONS.md` 171.
    """
    validation = await attempt(wardrobe, context, number=1)
    if validation.ok:
        return validation

    return await attempt(wardrobe, context, number=2, correction=validation.violation)
