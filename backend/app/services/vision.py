"""Image URL in, raw tag dict out.

The first module in the project that leaves the process for OpenAI. It returns
the model's response **unvalidated** — task 1.2 owns `validate_tags`, which
reads `enums.validate_tag_dict`'s report and decides between a retry, a
coercion and `TaggingError` (`DECISIONS.md` 028). The tag dict therefore keeps
the model's own key `confidence`; the rename to the `items.ai_confidence`
column happens at persistence in 1.3.

Prompt, schema and validator all take their vocabulary from `app/enums.py`, so
none of the three can disagree with the other two. `02-DATA-MODEL.md` remains
authoritative over `enums.py` itself, by hand.

openai 2.x: `chat.completions.create` and `chat.completions.parse` are
top-level. Almost every Structured Outputs example online is written against
1.x's `client.beta.chat.completions.parse`, and `client.beta` still exists in
2.x, so the older shape looks current rather than superseded — see the pinned
majors section of `CONVENTIONS.md`. `.parse()` is not used here on purpose: it
builds a schema from a Pydantic model, and what this task exists to verify is
the schema `03-AI-CONTRACTS.md` wrote down.
"""

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI
from openai.types.chat import (
    ChatCompletionMessageParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
)
from openai.types.shared_params.response_format_json_schema import JSONSchema

from app.core.config import settings
from app.enums import (
    SUBCATEGORIES,
    Category,
    ColorPrimary,
    Fit,
    Layer,
    Length,
    Material,
    Pattern,
    Rise,
)

logger = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "vision_system.md"
VOCABULARY_PLACEHOLDER = "{{VOCABULARY}}"

# The separator `02-DATA-MODEL.md` uses, so the rendered block and the document
# can be compared by eye. Roughly a hundred extra tokens per call against a
# comma; at this project's call volume that is a fraction of a cent in total,
# so legibility decides it rather than cost.
_SEPARATOR = " · "


def _vocabulary_block() -> str:
    """The closed vocabulary, rendered for the prompt.

    Load-bearing rather than belt-and-braces for exactly three fields. `fit`,
    `length` and `rise` are plain strings in the response schema — an
    out-of-vocabulary value there is coerced to null rather than retried, so
    constraining them in the schema would buy nothing (`03-AI-CONTRACTS.md`).
    That makes this block the **only** place the model ever learns what those
    three may contain. For every other field Structured Outputs enforces the
    list and this is reinforcement.
    """
    subcategories = "\n".join(
        f"  {category.value:<14} {_SEPARATOR.join(subs)}"
        for category, subs in SUBCATEGORIES.items()
    )
    return f"""ALLOWED VALUES — use only these. Never invent a value.

category         {_SEPARATOR.join(Category.values())}

subcategory — must belong to the category given above
{subcategories}

fit              {_SEPARATOR.join(Fit.values())} — or null
length           {_SEPARATOR.join(Length.values())} — or null
rise             {_SEPARATOR.join(Rise.values())} — or null
color_primary    {_SEPARATOR.join(ColorPrimary.values())}
color_secondary  any color_primary value — or null
pattern          {_SEPARATOR.join(Pattern.values())}
material         {_SEPARATOR.join(Material.values())}
layer            {_SEPARATOR.join(Layer.values())}"""


def _load_system_prompt() -> str:
    template = PROMPT_PATH.read_text(encoding="utf-8")
    if VOCABULARY_PLACEHOLDER not in template:
        # Loud at import rather than silent at call time: a prompt missing its
        # vocabulary still produces plausible-looking tags, and the three
        # unconstrained fields are the ones that would quietly degrade.
        raise ValueError(
            f"{PROMPT_PATH.name} does not contain {VOCABULARY_PLACEHOLDER}; "
            "the closed vocabulary would never reach the model."
        )
    return template.replace(VOCABULARY_PLACEHOLDER, _vocabulary_block())


SYSTEM_PROMPT = _load_system_prompt()

_COLORS = ColorPrimary.values()

# `subcategory` is a plain string because its valid values depend on `category`,
# which JSON Schema cannot express cleanly. `fit`, `length` and `rise` are plain
# strings for a different reason: an out-of-vocabulary value there is coerced to
# null rather than retried, so constraining them here would buy nothing. All
# four are validated in Python. `03-AI-CONTRACTS.md`.
_PROPERTIES: dict[str, Any] = {
    "category": {"type": "string", "enum": Category.values()},
    "subcategory": {"type": "string"},
    "fit": {"type": ["string", "null"]},
    "length": {"type": ["string", "null"]},
    "rise": {"type": ["string", "null"]},
    "color_primary": {"type": "string", "enum": _COLORS},
    # A nullable enum adds "null" to the *type union* and leaves the enum array
    # alone. That contradicts plain JSON Schema, under which a null value would
    # fail the enum constraint, and it is the vendor's documented pattern for
    # strict mode. Moving null into the array is the obvious tidy and is wrong.
    "color_secondary": {"type": ["string", "null"], "enum": _COLORS},
    "pattern": {"type": "string", "enum": Pattern.values()},
    "material": {"type": "string", "enum": Material.values()},
    "formality": {"type": "integer", "minimum": 1, "maximum": 5},
    "warmth": {"type": "integer", "minimum": 1, "maximum": 5},
    "layer": {"type": "string", "enum": Layer.values()},
    "water_resistant": {"type": "boolean"},
    "display_name": {"type": "string"},
    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
}

# Typed as the SDK's own TypedDict rather than dict[str, Any], so mypy checks
# the envelope — `name`, `strict`, `schema` — against what the API expects
# instead of only at the call site.
VISION_SCHEMA: JSONSchema = {
    "name": "garment_tags",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        # Derived rather than restated. Strict mode requires every property to
        # appear here, and a second hand-written list is one forgotten edit away
        # from a 400 that reads as a model problem.
        "required": list(_PROPERTIES),
        "properties": _PROPERTIES,
    },
}
# A hand-written placeholder, replaced at task 5.1 by responses recorded from
# the live API and keyed by input. `06-TESTING-STRATEGY.md` requires recorded
# fixtures and this is a deliberate exception to that rule for four stages —
# `DECISIONS.md` 081. It passes `validate_tag_dict` with no errors and no
# coercions, which is asserted rather than assumed, and `rise` and
# `color_secondary` are null so the null paths are exercised too.
#
# `layer: "base"` is the semantically right answer for a shirt and is NOT
# defended by that assertion. The vocabulary's layer rules are one-directional
# — they force `standalone` where it is required and never reject it where it
# is nonsense — so this fake tagged `standalone` would validate just as
# cleanly. Found by mutation; the gap belongs to task 1.2.
_FAKE_TAGS: dict[str, Any] = {
    "category": "top",
    "subcategory": "shirt",
    "fit": "relaxed",
    "length": "long_sleeve",
    "rise": None,
    "color_primary": "white",
    "color_secondary": None,
    "pattern": "solid",
    "material": "cotton",
    "formality": 3,
    "warmth": 2,
    "layer": "base",
    "water_resistant": False,
    # Says so out loud: a demo accidentally run with USE_FAKE_AI=true is then
    # visible on screen rather than looking like a real tagging result.
    "display_name": "placeholder white shirt",
    # Above 03-AI-CONTRACTS.md's 0.35 threshold, so the fake takes the happy
    # path instead of flagging every seeded item for review.
    "confidence": 0.5,
}


@lru_cache(maxsize=1)
def _client() -> AsyncOpenAI:
    """Built on first use, never at import.

    Measured: `AsyncOpenAI(api_key="")` raises `openai.OpenAIError` in the
    constructor. `OPENAI_API_KEY` defaults to an empty string precisely so CI
    can run without an OpenAI account (`07-DEPLOYMENT.md`), so a module-level
    client would raise on *import* — and from task 1.3 this module is on the
    import path to `app.main`, which would stop the whole suite collecting.
    This is 046's lesson about `cloudinary.config()` arriving through a second
    door, with a harder failure.
    """
    return AsyncOpenAI(
        api_key=settings.OPENAI_API_KEY,
        timeout=settings.OPENAI_TIMEOUT_SECONDS,
    )


async def tag_item(image_url: str) -> dict[str, Any]:
    """One garment photograph in, the model's raw tag dict out.

    Raises `ValueError` when the response cannot be turned into a dict, and
    lets the provider's own exceptions escape untouched. Task 1.2 wraps both
    into `TaggingError`; inventing that name here would be building 1.2.
    """
    if settings.USE_FAKE_AI:
        # A copy: 1.3 renames `confidence` on the way to the column and must not
        # reach through the return value into the module constant.
        return dict(_FAKE_TAGS)

    messages: list[ChatCompletionMessageParam] = [
        ChatCompletionSystemMessageParam(role="system", content=SYSTEM_PROMPT),
        ChatCompletionUserMessageParam(
            role="user",
            content=[
                # detail: "low" is sufficient for garment classification and
                # roughly four times cheaper than "high".
                {"type": "image_url", "image_url": {"url": image_url, "detail": "low"}}
            ],
        ),
    ]

    completion = await _client().chat.completions.create(
        model=settings.OPENAI_VISION_MODEL,
        messages=messages,
        response_format={"type": "json_schema", "json_schema": VISION_SCHEMA},
    )

    message = completion.choices[0].message
    if message.content is None:
        logger.warning(
            "Vision model returned no content",
            extra={"finish_reason": completion.choices[0].finish_reason},
        )
        raise ValueError("The vision model returned no content.")

    # json.JSONDecodeError subclasses ValueError, so a truncated response and an
    # empty one are one exception type for 1.2 to catch.
    tags: dict[str, Any] = json.loads(message.content)
    return tags
