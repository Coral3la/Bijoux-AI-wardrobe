"""The wardrobe and the weather in, one outfit out. The project's second door
to OpenAI.

`suggest_looks` assembles the three AI-free pieces Stage 2 built before it —
`build_rule` (2.1), the profile columns (2.2) and `serialize_wardrobe` (2.3) —
into the two messages `03-AI-CONTRACTS.md` specifies, and returns the model's
answer parsed and **unjudged**.

`validate_look_response` is what judges it — `03`'s validation table, the five
of its eight rules that have a field to read at Stage 2, run in the documented
order against the wardrobe that was actually sent. It calls nothing, raises
nothing and owns no loop: it returns a verdict beside the normalised response,
and 2.7 decides whether to spend the one retry through `correction=` or to
answer `502 stylist_failed`. That is 1.2b's split between `tag_item` and
`validate_tags` with the retry one seam further out, because re-calling the
stylist takes the whole request rather than one extra argument.

Pure with respect to the request: it holds no `Session` and reads no `Settings`
beyond the model pin and the fake flag, so 2.7 can decide *what* wardrobe the
stylist sees — `ready`-only, `is_archived`, and the swimwear/sleepwear exclusion
once that vocabulary exists (`AUDITS.md` O-21).

**What escapes, measured against openai 2.52.0 rather than read from its
documentation** — the practice `DECISIONS.md` 044 established against
Cloudinary's own exception base class, owed to this module since then and paid
here. `OpenAIError` covers less than it looks: a `200` whose body is not JSON raises
`json.JSONDecodeError` from inside the SDK, a `200` carrying JSON of the wrong
shape returns a `ChatCompletion` with `choices=None`, and a `200` with a
`text/html` body makes `create()` return a **`str`**. None of the three is an
`OpenAIError`, and all three would otherwise surface in a route as
`TypeError`/`AttributeError`. They are read here into the one `ValueError` this
module documents, so 2.7 catches two things — no usable answer, or a provider
exception — and not five.
"""

import json
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any, Final

from openai import AsyncOpenAI
from openai.types.chat import (
    ChatCompletionMessageParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
)
from openai.types.shared_params.response_format_json_schema import JSONSchema

from app.core.config import settings
from app.enums import Category, Layer
from app.schemas.item import ItemResponse
from app.services.serializer import serialize_wardrobe
from app.services.weather import requires_outerwear

logger = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "stylist_system.md"

# Read once at import, as `03-AI-CONTRACTS.md` requires of every prompt. Unlike
# the vision prompt there is no `{{VOCABULARY}}` to render: this one names no
# enum member, so the file is the prompt and nothing generates part of it. That
# is also why it carries no version constant — `PROMPT_VERSION` exists in
# `vision.py` because 1.11 mines it against a golden set, and nothing reads a
# stylist equivalent: no column, no task.
SYSTEM_PROMPT: Final = PROMPT_PATH.read_text(encoding="utf-8")

_LOOK_PROPERTIES: dict[str, Any] = {
    "occasion": {"type": "string"},
    "title": {"type": "string"},
    "item_ids": {"type": "array", "items": {"type": "string"}},
    "reasoning": {"type": "string"},
    "weather_note": {"type": "string"},
}

# `category` is a plain string rather than the seven `Category` members. It is
# display text — 2.9 renders the description, nothing branches on it — and the
# vocabulary is about to gain two members (O-21), so constraining it here would
# narrow a contract on behalf of a reader that does not exist.
_MISSING_PIECE_PROPERTIES: dict[str, Any] = {
    "category": {"type": "string"},
    "description": {"type": "string"},
    "reason": {"type": "string"},
}


def _object(properties: dict[str, Any]) -> dict[str, Any]:
    # Strict mode rejects a schema whose `required` differs from its properties,
    # so it is derived rather than restated — `VISION_SCHEMA`'s rule, which is
    # the reason a forgotten edit there is impossible rather than merely
    # unlikely.
    return {
        "type": "object",
        "additionalProperties": False,
        "required": list(properties),
        "properties": properties,
    }


# Single-day only. `packing_list` and its `by_category` map are **not** built
# here: packing is Stage 4's headline feature and its schema is designed beside
# the trip user message and the reuse arithmetic, not guessed now as a field
# that would be null on every call this project makes for two stages.
# `03-AI-CONTRACTS.md` says so in the same words.
#
# `confidence`, `look_id` and `day` are struck from `03`'s look object rather
# than deferred: none has a column, a renderer or a task, and in strict mode
# every property is one the model must produce on every call. `AUDITS.md` O-9
# asked for that decision before this schema existed; `DECISIONS.md` 086 refused
# the vision `confidence` a branch on the same evidence.
#
# `day` survived O-9 at 2.4 and lost the same argument at 2.5, on a measurement
# rather than on principle: the one live call answered `"day": 14` for a request
# dated 2026-03-14 while `USE_FAKE_AI` answered `1`, so the model and the fake
# disagreed about what the field meant and nothing read either. `02-DATA-MODEL.md`
# gives a look `for_date`, not a day number, so no stage has a column for it.
# Stage 4 reintroduces it beside the trip schema that needs it. `AUDITS.md` O-24,
# `DECISIONS.md` 163.
#
# No `minItems` anywhere. It is not verified against this pin, and "at least one
# look" is rule 4 of `03`'s validation table, which is 2.5's.
STYLIST_SCHEMA: JSONSchema = {
    "name": "outfit_recommendation",
    "strict": True,
    "schema": _object(
        {
            "looks": {"type": "array", "items": _object(_LOOK_PROPERTIES)},
            "missing_pieces": {"type": "array", "items": _object(_MISSING_PIECE_PROPERTIES)},
            "message": {"type": "string"},
        }
    ),
}

# `03-AI-CONTRACTS.md`'s wording, the same sentence `vision.py` sends and
# deliberately not imported from it: the two contracts are independent, and a
# shared constant would make a change to one prompt's retry a silent change to
# the other's.
_CORRECTION: Final = "Your previous response was invalid: {reason}. Correct it."


@dataclass(frozen=True, slots=True)
class StylistContext:
    """Everything about the request that is not the wardrobe.

    Built by 2.7 from the request body, the user's row and the forecast, so that
    this module holds no `Session` and no clock: `forecast_summary` and
    `weather_rule` arrive already computed by `services/weather.py`, which is
    what keeps the weather behaviour a pure function of three numbers
    (`DECISIONS.md` 004).

    `include_outerwear` is three-state on purpose — `True` forces a coat,
    `False` forbids one, `None` leaves the weather rule in charge — and it is
    `04-API-SPEC.md`'s spelling. `01-ARCHITECTURE.md` called the same field
    `wants_outerwear`, corrected in this commit against the authoritative
    document.
    """

    date: date
    occasion: str
    forecast_summary: str
    weather_rule: str
    notes: str | None = None
    include_outerwear: bool | None = None
    height_cm: int | None = None
    style_notes: str | None = None


@dataclass(frozen=True, slots=True)
class MissingPiece:
    category: str
    description: str
    reason: str


@dataclass(frozen=True, slots=True)
class Look:
    occasion: str
    title: str
    item_ids: tuple[str, ...]
    reasoning: str
    weather_note: str


@dataclass(frozen=True, slots=True)
class StylistResponse:
    """The model's answer, parsed and not yet judged.

    Frozen slotted dataclasses rather than Pydantic models, following
    `ItemTags` at `DECISIONS.md` 086: Pydantic is this project's wire-body type
    and the wire body for a look is 2.7's *hydrated* shape, where `item_ids`
    have become full items. A Pydantic model here would validate the same shape
    a second time under rules that are not the schema's.
    """

    looks: tuple[Look, ...]
    missing_pieces: tuple[MissingPiece, ...]
    message: str


@lru_cache(maxsize=1)
def _client() -> AsyncOpenAI:
    """Built on first use, never at import — `DECISIONS.md` 079's reasoning,
    which is unchanged here: `AsyncOpenAI(api_key="")` raises in the
    constructor, `OPENAI_API_KEY` is empty in CI, and this module is on the
    import path to `app.main` from 2.7.

    Its own client rather than `vision._client`, so the two contracts can be
    given different timeouts or pins without touching each other. The cost is
    that `tests/conftest.py`'s no-live-OpenAI guard has to name both doors, and
    it now does.
    """
    return AsyncOpenAI(
        api_key=settings.OPENAI_API_KEY,
        timeout=settings.OPENAI_TIMEOUT_SECONDS,
    )


def _profile_block(context: StylistContext) -> str:
    """`03`'s two-sentence profile line, with either half dropped when the
    column is null.

    The whole block is omitted rather than rendered empty when both are: a
    heading followed by nothing tells the model a profile exists and is blank,
    which is not what a user who has never opened the profile screen means.
    `AUDITS.md` O-6 closed the mechanism at 2.2 and recorded that in practice
    these two columns are usually still empty.
    """
    sentences = []
    if context.height_cm is not None:
        sentences.append(f"Height: {context.height_cm} cm.")
    if context.style_notes:
        sentences.append(f"Preferences: {context.style_notes}")
    if not sentences:
        return ""
    return "USER PROFILE:\n" + " ".join(sentences) + "\n\n"


def _outerwear_line(include_outerwear: bool | None) -> str:
    if include_outerwear is None:
        return ""
    if include_outerwear:
        return "Outerwear: the user has asked for outerwear. Include one.\n"
    return "Outerwear: the user has asked for no outerwear. Include none.\n"


def _user_message(wardrobe: Sequence[ItemResponse], context: StylistContext) -> str:
    """`03-AI-CONTRACTS.md`'s user message, single-day block.

    The outerwear preference is printed **after** the weather rule and not
    beside the occasion, because it overrides that rule and a reader — human or
    model — takes the later of two conflicting instructions as the operative
    one. The system prompt says which wins in words; this puts them in that
    order on the page as well.
    """
    request = f"REQUEST:\nDate: {context.date.isoformat()}\nOccasion: {context.occasion}\n"
    if context.notes:
        request += f"Notes: {context.notes}\n"
    request += (
        f"Weather: {context.forecast_summary}\n"
        f"Weather rule: {context.weather_rule}\n"
        f"{_outerwear_line(context.include_outerwear)}"
        f"Build 1 look."
    )
    return (
        f"WARDROBE ({len(wardrobe)} items):\n"
        f"{serialize_wardrobe(wardrobe)}\n\n"
        f"{_profile_block(context)}"
        f"{request}"
    )


def _first(wardrobe: Sequence[ItemResponse], category: Category) -> ItemResponse | None:
    return next((item for item in wardrobe if item.category == category), None)


def _fake_response(wardrobe: Sequence[ItemResponse], context: StylistContext) -> StylistResponse:
    """The `USE_FAKE_AI` answer, built from the wardrobe it was handed.

    `STAGE-2` 2.4 says "a recorded fixture" and `06-TESTING-STRATEGY.md` says
    fixtures are real recorded responses. **Neither is achievable here and the
    reason is arithmetic, not preference:** `short_id`s are generated per row by
    `scripts/seed_demo.py`, so they differ on every seed, and a fixture with
    literal ids would fail 2.5's rule 1 — the hallucination guard — on every
    call. The `USE_FAKE_AI` path exists to make E2E journeys 6 and 7
    deterministic, and a fake that can only ever produce a `502` does the
    opposite. `DECISIONS.md` 159.

    Deterministic and deliberately not clever: the first shoes, then the first
    top and bottom, falling back to the first dress when the wardrobe has no
    pair. No styling, no weather, no ordering by anything. The text says out
    loud that it is a placeholder, which is `DECISIONS.md` 081's mitigation for
    the same rule broken the same way on the vision side — a demo accidentally
    run with the flag on is visible on screen rather than passing for a look.
    """
    shoes = _first(wardrobe, Category.SHOES)
    top = _first(wardrobe, Category.TOP)
    bottom = _first(wardrobe, Category.BOTTOM)
    chosen = [shoes, top, bottom] if top and bottom else [shoes, _first(wardrobe, Category.DRESS)]

    return StylistResponse(
        looks=(
            Look(
                occasion=context.occasion,
                title="Placeholder look",
                item_ids=tuple(item.short_id for item in chosen if item is not None),
                reasoning=(
                    "Placeholder response: USE_FAKE_AI is on, so no model was called. "
                    "These items were picked by category, not styled."
                ),
                weather_note="Placeholder response: the weather rule was not applied.",
            ),
        ),
        missing_pieces=(),
        message="Placeholder response from USE_FAKE_AI. No model was called.",
    )


def _content(completion: Any) -> str:
    """The one string the model sent back, or `ValueError`.

    Every check here fires on something measured against openai 2.52.0, not on
    something imagined — see the module docstring. `getattr` rather than
    `completion.choices` because in the `text/html` case `completion` is a
    `str`, which the SDK's own type annotation says is impossible.
    """
    choices = getattr(completion, "choices", None)
    if not choices:
        logger.warning(
            "Stylist model returned no choices", extra={"answer_type": type(completion).__name__}
        )
        raise ValueError("The stylist model returned no choices.")

    content = choices[0].message.content
    if content is None:
        logger.warning(
            "Stylist model returned no content",
            extra={"finish_reason": choices[0].finish_reason},
        )
        raise ValueError("The stylist model returned no content.")
    return str(content)


def _build(payload: Any) -> StylistResponse:
    """The parsed JSON into the typed answer.

    Shape is `STYLIST_SCHEMA`'s guarantee and is not re-checked field by field;
    what this catches is an answer that is not that shape **at all**, which the
    measured leniencies above make reachable. Semantics — every id real, shoes
    present, no two outer layers — are `validate_look_response`'s below, and so
    is normalising the case of a returned id (`DECISIONS.md` 156).
    """
    try:
        return StylistResponse(
            looks=tuple(
                Look(
                    occasion=look["occasion"],
                    title=look["title"],
                    item_ids=tuple(look["item_ids"]),
                    reasoning=look["reasoning"],
                    weather_note=look["weather_note"],
                )
                for look in payload["looks"]
            ),
            missing_pieces=tuple(
                MissingPiece(
                    category=piece["category"],
                    description=piece["description"],
                    reason=piece["reason"],
                )
                for piece in payload["missing_pieces"]
            ),
            message=payload["message"],
        )
    except (KeyError, TypeError, IndexError) as exc:
        raise ValueError(f"The stylist model's answer was not the documented shape: {exc}") from exc


async def suggest_looks(
    wardrobe: Sequence[ItemResponse],
    context: StylistContext,
    correction: str | None = None,
) -> StylistResponse:
    """One wardrobe and one request in, one unjudged recommendation out.

    `correction` is the violation 2.5 found in the previous answer, and it is
    the whole of the retry: same wardrobe, same schema, one more instruction.
    Calling this twice is 2.5's decision, not this function's.

    Raises `ValueError` when no usable answer arrived — no choices, no content,
    unparseable JSON, or JSON that is not the documented shape. Lets the
    provider's own exceptions escape untouched, so 2.7 can tell "OpenAI did not
    answer" apart from "OpenAI answered nonsense" the way 1.3 does on the vision
    side (`DECISIONS.md` 086).
    """
    if settings.USE_FAKE_AI:
        return _fake_response(wardrobe, context)

    content: list[Any] = [{"type": "text", "text": _user_message(wardrobe, context)}]
    if correction is not None:
        content.append({"type": "text", "text": _CORRECTION.format(reason=correction)})

    messages: list[ChatCompletionMessageParam] = [
        ChatCompletionSystemMessageParam(role="system", content=SYSTEM_PROMPT),
        ChatCompletionUserMessageParam(role="user", content=content),
    ]

    completion = await _client().chat.completions.create(
        model=settings.OPENAI_STYLIST_MODEL,
        messages=messages,
        response_format={"type": "json_schema", "json_schema": STYLIST_SCHEMA},
    )

    # json.JSONDecodeError subclasses ValueError, so a truncated answer and an
    # empty one are one exception type for the caller to catch.
    return _build(json.loads(_content(completion)))


@dataclass(frozen=True, slots=True)
class LookValidation:
    """The verdict, and the response the caller should go on to use.

    `response` is normalised rather than the object that went in: the model's
    ids are upper-cased before rule 1 looks them up (`DECISIONS.md` 156), and
    2.7 persists and hydrates from this field so an id cannot be case-shifted in
    one place and not another. `violation` is the first rule that failed, worded
    for the model, or `None`.
    """

    response: StylistResponse
    violation: str | None

    @property
    def ok(self) -> bool:
        return self.violation is None


def _normalised(response: StylistResponse) -> StylistResponse:
    """`.upper()` on every returned id, and nothing else.

    `app/core/short_id.py`'s alphabet is upper-case only, so case is the one
    difference between what a model might send and what a row holds that is not
    a hallucination. It is deliberately not `.strip()` as well: nothing has been
    measured that pads an id, and a guess about whitespace would be code no test
    can justify. Transliteration is not an option at all — the alphabet drops
    *both* halves of every confusable pair, so a returned `0` maps to no legal
    character and is a hallucination rather than a typo.
    """
    return replace(
        response,
        looks=tuple(
            replace(look, item_ids=tuple(item_id.upper() for item_id in look.item_ids))
            for look in response.looks
        ),
    )


def _unknown_id(looks: tuple[Look, ...], known: Mapping[str, ItemResponse]) -> str | None:
    for look in looks:
        for item_id in look.item_ids:
            if item_id not in known:
                return f"unknown item id {item_id}; it is not in the wardrobe you were given"
    return None


def _incomplete(looks: tuple[Look, ...], known: Mapping[str, ItemResponse]) -> str | None:
    for look in looks:
        categories = {known[item_id].category for item_id in look.item_ids}
        if Category.SHOES not in categories:
            return "the look has no shoes"
        if Category.DRESS in categories:
            continue
        if not {Category.TOP, Category.BOTTOM} <= categories:
            return "the look has neither a top and a bottom nor a dress"
    return None


def _two_outer_layers(looks: tuple[Look, ...], known: Mapping[str, ItemResponse]) -> str | None:
    # By `layer`, not by category, which is the prompt's own wording — "Never
    # place two `outer` layer items". `LAYERS_BY_CATEGORY` lets outerwear be
    # `mid`, so a blazer worn under a coat is a legal look and two coats are not.
    for look in looks:
        outer = [item_id for item_id in look.item_ids if known[item_id].layer is Layer.OUTER]
        if len(outer) > 1:
            return f"the look contains two outer layer items: {outer[0]} and {outer[1]}"
    return None


def _wrong_count(looks: tuple[Look, ...]) -> str | None:
    # `03`'s rule 4 is `len(looks) == expected_days`; a single-day request is a
    # trip of length one, so the expected count is 1 and is not a parameter until
    # Stage 4 has a request that can ask for another number.
    if len(looks) != 1:
        return f"you returned {len(looks)} looks and exactly 1 was requested"
    return None


def _missing_outerwear(
    looks: tuple[Look, ...], known: Mapping[str, ItemResponse], context: StylistContext
) -> str | None:
    """Rule 6, and the one narrowing `03`'s table does not print.

    It does not run when the user asked for no outerwear. `DECISIONS.md` 158
    gave an explicit `include_outerwear` precedence over the weather rule and
    the system prompt says so in words, so a look that obeyed the user at 12°C
    is correct — and enforcing the rule over it would spend the retry and then
    answer `502` to the one answer that did what it was told.
    """
    if context.include_outerwear is False:
        return None
    if not requires_outerwear(context.weather_rule):
        return None
    for look in looks:
        if not any(known[item_id].category is Category.OUTERWEAR for item_id in look.item_ids):
            return "the weather rule requires outerwear and the look contains none"
    return None


def _violation(
    response: StylistResponse, wardrobe: Sequence[ItemResponse], context: StylistContext
) -> str | None:
    """`03`'s table, in `03`'s order, stopping at the first failure.

    The order is load-bearing rather than cosmetic. Rule 1 is what makes every
    later rule able to look an id up at all, so it runs first and returns before
    the rest can raise a `KeyError` on a hallucinated id. One violation rather
    than a list because it is a sentence sent back to the model, and one
    concrete instruction is likelier to be obeyed than five.

    Rule 5 is absent: it reads `packing_list.item_ids`, and `STYLIST_SCHEMA`
    carries no `packing_list` until Stage 4 designs it beside the trip message
    (`DECISIONS.md` 157). Rules 7 and 8 arrive with the anchor at 2.10 and the
    swap at 2.11.
    """
    known = {item.short_id: item for item in wardrobe}
    return (
        _unknown_id(response.looks, known)
        or _incomplete(response.looks, known)
        or _two_outer_layers(response.looks, known)
        or _wrong_count(response.looks)
        or _missing_outerwear(response.looks, known, context)
    )


def validate_look_response(
    response: StylistResponse,
    wardrobe: Sequence[ItemResponse],
    context: StylistContext,
) -> LookValidation:
    """One answer judged against the wardrobe it was built from.

    `wardrobe` is the sequence that was **sent** to the model, not every row the
    user owns. After 2.6a that is the narrower list — `ready`, not archived, no
    swimwear or sleepwear — and an id the model was never shown is a
    hallucination whether or not the garment is in the drawer.

    Calls nothing and raises nothing. The retry, the give-up log and
    `502 stylist_failed` are 2.7's, which is the only place that holds the
    request needed to ask the model a second time.
    """
    normalised = _normalised(response)
    violation = _violation(normalised, wardrobe, context)
    if violation is not None:
        logger.warning("Stylist response rejected", extra={"violation": violation})
    return LookValidation(response=normalised, violation=violation)
