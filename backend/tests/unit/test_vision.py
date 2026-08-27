"""The vision service, with no AI call anywhere.

Everything here is a property of the schema, the rendered prompt, the fake, the
request `tag_item` builds, or the judgement `validate_tags` makes about an
answer. The live call is task 1.1's manual verification step and cannot be a
test — `CONVENTIONS.md` forbids any test calling OpenAI unless it is marked
`eval`.

Note what is deliberately *not* asserted: that the schema's enum arrays equal
`enums.py`'s. Both come from `enums.py`, so that comparison is a tautology and
`06-TESTING-STRATEGY.md` records it as one rather than letting it read as a
drift detector. What is asserted below is the part of the schema that is a
choice — the strict subset's shape, which a tidy-up would break.

The rendered *rules* are the opposite case and are pinned literally. Every
other prompt assertion here derives its expectation from `enums.py`, so a
mutation of a table would move the expectation with it and stay green — the
shape `06-TESTING-STRATEGY.md` describes and `test_enums.py` answers for the
tables themselves.
"""

import json
import logging
from collections.abc import Callable
from typing import Any

import pytest
from openai import AsyncOpenAI

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
    validate_tag_dict,
)
from app.services import vision

UNCONSTRAINED = ("subcategory", "fit", "length", "rise")
IMAGE_URL = "https://res.cloudinary.invalid/a"


# --- the response schema ----------------------------------------------------


def test_every_property_is_required() -> None:
    # Strict mode rejects a schema where they differ, so the failure would be a
    # 400 on the first live call, which reads as a model problem.
    schema = vision.VISION_SCHEMA["schema"]
    assert schema["required"] == list(schema["properties"])


def test_additional_properties_are_forbidden() -> None:
    assert vision.VISION_SCHEMA["schema"]["additionalProperties"] is False


def test_the_schema_is_strict() -> None:
    assert vision.VISION_SCHEMA["strict"] is True


def test_every_property_carries_a_type() -> None:
    # A bare {"enum": [...]} does not appear anywhere in the supported strict
    # subset; the documented form is always type plus enum.
    for name, spec in vision.VISION_SCHEMA["schema"]["properties"].items():
        assert "type" in spec, name


def test_a_nullable_enum_keeps_null_out_of_the_enum_array() -> None:
    # The vendor's documented shape for an optional enum, and it contradicts
    # plain JSON Schema — under which a null would fail the enum constraint.
    # Moving null into the array is the obvious tidy and is wrong.
    secondary = vision.VISION_SCHEMA["schema"]["properties"]["color_secondary"]

    assert secondary["type"] == ["string", "null"]
    assert None not in secondary["enum"]
    assert secondary["enum"] == ColorPrimary.values()


def test_the_category_dependent_and_coerced_fields_carry_no_enum() -> None:
    # subcategory because its validity depends on category, which JSON Schema
    # cannot express cleanly; fit, length and rise because an out-of-vocabulary
    # value there is coerced to null rather than retried, so constraining them
    # would buy nothing. All four are validated in Python instead.
    properties = vision.VISION_SCHEMA["schema"]["properties"]

    for name in UNCONSTRAINED:
        assert "enum" not in properties[name], name


def test_the_bounded_numbers_carry_both_bounds() -> None:
    properties = vision.VISION_SCHEMA["schema"]["properties"]

    assert (properties["formality"]["minimum"], properties["formality"]["maximum"]) == (1, 5)
    assert (properties["warmth"]["minimum"], properties["warmth"]["maximum"]) == (1, 5)
    assert (properties["confidence"]["minimum"], properties["confidence"]["maximum"]) == (0, 1)


# --- the rendered prompt ----------------------------------------------------


def test_the_placeholder_is_replaced() -> None:
    assert vision.VOCABULARY_PLACEHOLDER not in vision.SYSTEM_PROMPT


def test_a_prompt_file_without_the_placeholder_raises_at_load(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The guard's logic is tested, not merely intended. A prompt that silently
    # lost its vocabulary still returns plausible tags, and the three fields the
    # schema does not constrain are exactly the ones that would quietly degrade.
    #
    # What this cannot defend is the shipped prompt file. Deleting the real
    # placeholder raises at import and takes this module with it, so the failure
    # is a collection error and no named test reports it — 1.2b's mutation 16.
    stripped = tmp_path / "vision_system.md"
    stripped.write_text(
        vision.SYSTEM_PROMPT.replace(vision._vocabulary_block(), ""), encoding="utf-8"
    )
    monkeypatch.setattr(vision, "PROMPT_PATH", stripped)

    with pytest.raises(ValueError, match=r"\{\{VOCABULARY\}\}"):
        vision._load_system_prompt()


@pytest.mark.parametrize(
    "vocabulary",
    [Category, Fit, Length, Rise, ColorPrimary, Pattern, Material, Layer],
    ids=lambda v: v.__name__.lower(),
)
def test_every_vocabulary_value_reaches_the_prompt(vocabulary: type) -> None:
    # The whole point of rendering the block rather than writing it out: drop a
    # field from _vocabulary_block and this fails, where the schema would not
    # notice for fit, length or rise at all.
    for value in vocabulary.values():
        assert value in vision.SYSTEM_PROMPT, value


def test_every_subcategory_reaches_the_prompt_under_its_category() -> None:
    # subcategory is a plain string in the schema, so the prompt is the only
    # place the mapping is ever stated to the model.
    for category, subs in SUBCATEGORIES.items():
        for sub in subs:
            assert sub in vision.SYSTEM_PROMPT, sub
        assert category.value in vision.SYSTEM_PROMPT


def test_the_prompt_keeps_the_rules_the_schema_cannot_express() -> None:
    # rise-only-for-bottoms and the 20% rule for color_secondary are semantic,
    # not structural; nothing but the prompt carries them to the model.
    assert "rise" in vision.SYSTEM_PROMPT
    assert "at least 20%" in vision.SYSTEM_PROMPT
    assert "0.35" in vision.SYSTEM_PROMPT


# --- the rendered category rules, pinned literally ---------------------------
#
# Task 1.2b's half of `DECISIONS.md` 084: the model is told the rules rather
# than only corrected by them. These are transcribed from `02-DATA-MODEL.md`,
# not read back out of `enums.py`, because a test that derives its expectation
# from the table under test measures nothing on its own.


def test_the_layer_table_reaches_the_prompt_for_every_category() -> None:
    for line in (
        "  top            base or mid",
        "  bottom         base",
        "  dress          standalone",
        "  outerwear      mid or outer",
        "  shoes          standalone",
        "  bag            standalone",
        "  accessory      standalone",
        "  swimwear       standalone",
        "  sleepwear      standalone",
    ):
        assert line in vision.SYSTEM_PROMPT, line


def test_the_narrowed_fit_words_reach_the_prompt() -> None:
    for line in (
        "  skinny         bottom",
        "  wide           bottom · dress",
        "  bodycon        top · bottom · dress",
    ):
        assert line in vision.SYSTEM_PROMPT, line


def test_the_narrowed_length_words_reach_the_prompt() -> None:
    for line in (
        "  sleeveless     top · dress · outerwear · swimwear · sleepwear",
        "  short_sleeve   top · dress · outerwear · swimwear · sleepwear",
        "  long_sleeve    top · dress · outerwear · swimwear · sleepwear",
        "  mini           bottom · dress · outerwear · swimwear · sleepwear",
        "  midi           bottom · dress · outerwear · swimwear · sleepwear",
        "  maxi           bottom · dress · outerwear · swimwear · sleepwear",
    ):
        assert line in vision.SYSTEM_PROMPT, line


def test_each_fields_applicability_reaches_the_prompt() -> None:
    for line in (
        "  applies to     top · bottom · dress · outerwear · swimwear · sleepwear"
        " — null for any other category",
        "  applies to     top · bottom · dress · outerwear · shoes · swimwear · sleepwear"
        " — null for any other category",
        "  applies to     bottom — null for any other category",
    ):
        assert line in vision.SYSTEM_PROMPT, line


def test_the_middle_of_the_length_list_gets_no_rule_of_its_own() -> None:
    # crop, regular, longline, ankle and full describe more than one axis and are
    # unenforced on purpose. Rendering a rule for them would teach the model a
    # narrowing the validator does not apply.
    for word in ("crop", "regular", "longline", "ankle", "full"):
        assert f"\n  {word:<14} " not in vision.SYSTEM_PROMPT, word


def test_the_prompt_file_hand_writes_no_category_rule_of_its_own() -> None:
    # 080's property extended from the values to the rules. Both of these
    # sentences were in the template before 1.2b and are now generated, so
    # leaving them would be a second copy that can drift — with nothing to
    # compare it against, since one of them is prose.
    template = vision.PROMPT_PATH.read_text(encoding="utf-8")

    assert "applies only when category" not in template
    assert "dresses, shoes" not in template


# --- the prompt version -----------------------------------------------------


def test_the_prompt_version_moves_when_the_prompt_does() -> None:
    assert vision._prompt_version("one prompt") != vision._prompt_version("another prompt")


def test_the_prompt_version_covers_the_generated_vocabulary() -> None:
    # Task 1.11 measures accuracy against this prompt and records the version
    # beside the model id. Hashing the file rather than the rendered text is the
    # plausible mistake: it would hold still while enums.py moved underneath it.
    template = vision.PROMPT_PATH.read_text(encoding="utf-8")
    narrowed = vision.SYSTEM_PROMPT.replace(
        "  skinny         bottom", "  skinny         bottom · top"
    )

    from_the_file = vision._prompt_version(template)
    from_a_wider_rule = vision._prompt_version(narrowed)

    assert from_the_file != vision.PROMPT_VERSION
    assert from_a_wider_rule != vision.PROMPT_VERSION


# --- the fake ---------------------------------------------------------------


def test_the_fake_is_valid_input_to_the_validator() -> None:
    # If 1.2 tightens validate_tag_dict, this fails here rather than at 5.1.
    # A fixture that has quietly stopped being valid input is the same shape of
    # problem as a test that has quietly stopped asserting anything.
    report = validate_tag_dict(vision._FAKE_TAGS)

    assert report.errors == ()
    assert report.coerced == ()


def test_the_fake_survives_validation_unchanged() -> None:
    assert validate_tag_dict(vision._FAKE_TAGS).tags == vision._FAKE_TAGS


def test_the_fake_carries_exactly_the_documented_fields() -> None:
    assert set(vision._FAKE_TAGS) == set(vision.VISION_SCHEMA["schema"]["properties"])


def test_the_fake_confidence_is_above_the_threshold_the_prompt_names() -> None:
    # The threshold is the prompt's, not the code's: 1.2b decided against a
    # review branch (`DECISIONS.md` 086), so nothing compares this number. What
    # it protects is the column — every fake-tagged item in Stages 1 to 4 would
    # otherwise read as a poor tagging result to 1.11 and to anyone querying it.
    assert vision._FAKE_TAGS["confidence"] >= 0.35


@pytest.mark.asyncio
async def test_the_fake_branch_never_builds_a_client(monkeypatch: pytest.MonkeyPatch) -> None:
    # CI configures no OPENAI_API_KEY, and AsyncOpenAI raises on an empty one.
    # This is what keeps USE_FAKE_AI usable there.
    monkeypatch.setattr(settings, "USE_FAKE_AI", True)

    def explode() -> AsyncOpenAI:
        raise AssertionError("the OpenAI client was built")

    monkeypatch.setattr(vision, "_client", explode)

    assert await vision.tag_item("https://example.invalid/x") == vision._FAKE_TAGS


@pytest.mark.asyncio
async def test_the_fake_branch_returns_a_copy(monkeypatch: pytest.MonkeyPatch) -> None:
    # 1.3 renames `confidence` to `ai_confidence` on the way to the column, so a
    # caller mutating the result must not reach the module constant.
    monkeypatch.setattr(settings, "USE_FAKE_AI", True)

    first = await vision.tag_item("https://example.invalid/x")
    first["category"] = "mutated"

    assert vision._FAKE_TAGS["category"] == "top"
    assert (await vision.tag_item("https://example.invalid/x"))["category"] == "top"


# --- the request tag_item builds --------------------------------------------


class _RecordingCompletions:
    def __init__(self, content: str | None, finish_reason: str = "stop") -> None:
        self._content = content
        self._finish_reason = finish_reason
        self.kwargs: dict[str, Any] = {}

    async def create(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        message = type("Message", (), {"content": self._content})()
        choice = type("Choice", (), {"message": message, "finish_reason": self._finish_reason})()
        return type("Completion", (), {"choices": [choice]})()


@pytest.fixture
def recorded(monkeypatch: pytest.MonkeyPatch) -> _RecordingCompletions:
    monkeypatch.setattr(settings, "USE_FAKE_AI", False)
    completions = _RecordingCompletions(json.dumps(vision._FAKE_TAGS))
    client = type("Client", (), {"chat": type("Chat", (), {"completions": completions})()})()
    monkeypatch.setattr(vision, "_client", lambda: client)
    return completions


@pytest.mark.asyncio
async def test_the_call_sends_the_documented_schema(recorded: _RecordingCompletions) -> None:
    await vision.tag_item(IMAGE_URL)

    assert recorded.kwargs["response_format"] == {
        "type": "json_schema",
        "json_schema": vision.VISION_SCHEMA,
    }


@pytest.mark.asyncio
async def test_the_call_sends_the_image_at_low_detail(recorded: _RecordingCompletions) -> None:
    # detail: "low" is the cost decision in 03-AI-CONTRACTS.md — roughly four
    # times cheaper than "high" and sufficient for garment classification.
    await vision.tag_item(IMAGE_URL)

    image = recorded.kwargs["messages"][1]["content"][0]
    assert image == {
        "type": "image_url",
        "image_url": {"url": IMAGE_URL, "detail": "low"},
    }


@pytest.mark.asyncio
async def test_the_call_sends_the_rendered_prompt_as_the_system_message(
    recorded: _RecordingCompletions,
) -> None:
    await vision.tag_item(IMAGE_URL)

    system = recorded.kwargs["messages"][0]
    assert system["role"] == "system"
    assert system["content"] == vision.SYSTEM_PROMPT


@pytest.mark.asyncio
async def test_the_call_uses_the_configured_vision_model(
    recorded: _RecordingCompletions, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "OPENAI_VISION_MODEL", "a-different-model")

    await vision.tag_item(IMAGE_URL)

    assert recorded.kwargs["model"] == "a-different-model"


@pytest.mark.asyncio
async def test_a_call_with_no_correction_sends_the_image_alone(
    recorded: _RecordingCompletions,
) -> None:
    await vision.tag_item(IMAGE_URL)

    assert len(recorded.kwargs["messages"][1]["content"]) == 1


@pytest.mark.asyncio
async def test_a_correction_is_sent_beside_the_image_in_03s_words(
    recorded: _RecordingCompletions,
) -> None:
    # Same image, same schema, one more instruction — the whole of the retry.
    await vision.tag_item(IMAGE_URL, correction="layer 'standalone' is wrong")

    content = recorded.kwargs["messages"][1]["content"]
    assert content[1] == {
        "type": "text",
        "text": "Your previous response was invalid: layer 'standalone' is wrong. Correct it.",
    }


@pytest.mark.asyncio
async def test_the_response_is_returned_unvalidated(recorded: _RecordingCompletions) -> None:
    # validate_tags owns validation. A tag dict this function silently corrected
    # would rob it of the input it exists to judge.
    assert await vision.tag_item(IMAGE_URL) == vision._FAKE_TAGS


@pytest.mark.asyncio
async def test_a_response_with_no_content_raises_a_value_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "USE_FAKE_AI", False)
    completions = _RecordingCompletions(None, finish_reason="length")
    client = type("Client", (), {"chat": type("Chat", (), {"completions": completions})()})()
    monkeypatch.setattr(vision, "_client", lambda: client)

    with pytest.raises(ValueError):
        await vision.tag_item(IMAGE_URL)


@pytest.mark.asyncio
async def test_a_truncated_response_raises_a_value_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # json.JSONDecodeError subclasses ValueError, so the caller has one type to
    # catch for "the response was not usable" rather than two.
    monkeypatch.setattr(settings, "USE_FAKE_AI", False)
    completions = _RecordingCompletions('{"category": "to')
    client = type("Client", (), {"chat": type("Chat", (), {"completions": completions})()})()
    monkeypatch.setattr(vision, "_client", lambda: client)

    with pytest.raises(ValueError):
        await vision.tag_item(IMAGE_URL)


# --- validate_tags ----------------------------------------------------------


class _ScriptedCompletions:
    """Answers with each scripted response in turn, and refuses a call past the end.

    The refusal is how "never retry more than once" is defended: a second call
    inside `validate_tags` fails the test by raising, whether or not any
    assertion counts the calls.
    """

    def __init__(self, responses: tuple[dict[str, Any], ...]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if not self._responses:
            raise AssertionError("the vision model was called more often than the test scripted")
        message = type("Message", (), {"content": json.dumps(self._responses.pop(0))})()
        choice = type("Choice", (), {"message": message, "finish_reason": "stop"})()
        return type("Completion", (), {"choices": [choice]})()


@pytest.fixture
def scripted(
    monkeypatch: pytest.MonkeyPatch,
) -> Callable[..., _ScriptedCompletions]:
    def install(*responses: dict[str, Any]) -> _ScriptedCompletions:
        monkeypatch.setattr(settings, "USE_FAKE_AI", False)
        completions = _ScriptedCompletions(responses)
        client = type("Client", (), {"chat": type("Chat", (), {"completions": completions})()})()
        monkeypatch.setattr(vision, "_client", lambda: client)
        return completions

    return install


def _raw(**overrides: Any) -> dict[str, Any]:
    """A well-formed answer, altered one field at a time."""
    return {**vision._FAKE_TAGS, **overrides}


def _correction(completions: _ScriptedCompletions) -> str:
    text: str = completions.calls[0]["messages"][1]["content"][1]["text"]
    return text


@pytest.mark.asyncio
async def test_a_clean_answer_is_accepted_without_calling_the_model(
    scripted: Callable[..., _ScriptedCompletions],
) -> None:
    completions = scripted()

    tags = await vision.validate_tags(_raw(), IMAGE_URL)

    assert completions.calls == []
    assert tags.display_name == "placeholder white shirt"


@pytest.mark.asyncio
async def test_the_result_carries_the_vocabulary_types(
    scripted: Callable[..., _ScriptedCompletions],
) -> None:
    # 080's trade-off closed: tag_item returns dict[str, Any] and this is where
    # types arrive, so 1.3 writes members to the columns rather than strings.
    scripted()

    tags = await vision.validate_tags(_raw(), IMAGE_URL)

    assert tags.category is Category.TOP
    assert tags.layer is Layer.BASE
    assert tags.fit is Fit.RELAXED
    assert tags.length is Length.LONG_SLEEVE
    assert tags.rise is None
    assert tags.color_secondary is None
    assert tags.confidence == 0.5


@pytest.mark.asyncio
async def test_an_integer_confidence_arrives_as_a_float(
    scripted: Callable[..., _ScriptedCompletions],
) -> None:
    # 1 is a legal confidence under the schema's number type and the column is a
    # float, so the conversion happens once, here.
    scripted()

    tags = await vision.validate_tags(_raw(confidence=1), IMAGE_URL)

    assert isinstance(tags.confidence, float)


# --- validate_tags: coercions are accepted, never retried --------------------


@pytest.mark.asyncio
async def test_an_out_of_vocabulary_fit_is_nulled_and_not_retried(
    scripted: Callable[..., _ScriptedCompletions],
) -> None:
    # `fit: "flared"` on real jeans at task 1.1. The membership check works; the
    # question this task answers is whether anything remembers.
    completions = scripted()

    tags = await vision.validate_tags(_raw(fit="flared"), IMAGE_URL)

    assert completions.calls == []
    assert tags.fit is None


@pytest.mark.asyncio
async def test_the_discarded_value_survives_on_the_result(
    scripted: Callable[..., _ScriptedCompletions],
) -> None:
    # 1.3 persists these into items.attributes. Without them the item screen
    # shows an empty field and 1.11 has nothing to mine but nulls.
    scripted()

    tags = await vision.validate_tags(_raw(fit="flared"), IMAGE_URL)

    assert [(issue.field, issue.value) for issue in tags.coerced] == [("fit", "flared")]


@pytest.mark.asyncio
async def test_the_discarded_value_is_logged_with_its_field_and_category(
    scripted: Callable[..., _ScriptedCompletions], caplog: pytest.LogCaptureFixture
) -> None:
    # The field and the value are what 1.11 needs to count the two failures
    # apart: whether the value is in its own enum says which kind it was.
    scripted()

    with caplog.at_level(logging.WARNING, logger="app.services.vision"):
        await vision.validate_tags(_raw(fit="skinny", category="top"), IMAGE_URL)

    coerced = [r for r in caplog.records if r.getMessage() == "Vision tag coerced"]
    assert len(coerced) == 1
    assert (coerced[0].field, coerced[0].value, coerced[0].category) == ("fit", "skinny", "top")


@pytest.mark.asyncio
async def test_a_layer_the_category_can_answer_for_is_coerced_and_not_retried(
    scripted: Callable[..., _ScriptedCompletions],
) -> None:
    # outerwear admits mid and outer and still answers `outer`, because the
    # document says a coat is outer. This is the row a plausible simplification
    # would turn into an error path.
    completions = scripted()

    tags = await vision.validate_tags(
        _raw(category="outerwear", subcategory="coat", layer="base", fit=None, length="regular"),
        IMAGE_URL,
    )

    assert completions.calls == []
    assert tags.layer is Layer.OUTER


# --- validate_tags: the retry, and the one path that reaches TaggingError -----


@pytest.mark.asyncio
async def test_a_top_refusing_a_layer_is_retried_once(
    scripted: Callable[..., _ScriptedCompletions],
) -> None:
    # The only category-dependent rule that errors rather than coerces, because
    # `top` is the only category 02-DATA-MODEL.md names no answer for.
    completions = scripted(_raw(layer="mid"))

    tags = await vision.validate_tags(_raw(layer="standalone"), IMAGE_URL)

    assert len(completions.calls) == 1
    assert tags.layer is Layer.MID


@pytest.mark.asyncio
async def test_the_retry_names_the_violation(
    scripted: Callable[..., _ScriptedCompletions],
) -> None:
    completions = scripted(_raw())

    await vision.validate_tags(_raw(layer="standalone"), IMAGE_URL)

    assert _correction(completions) == (
        "Your previous response was invalid: layer 'standalone' is not valid for "
        "category 'top', which takes base or mid. Correct it."
    )


@pytest.mark.asyncio
async def test_the_retry_sends_the_same_image(
    scripted: Callable[..., _ScriptedCompletions],
) -> None:
    completions = scripted(_raw())

    await vision.validate_tags(_raw(layer="standalone"), IMAGE_URL)

    image = completions.calls[0]["messages"][1]["content"][0]
    assert image["image_url"]["url"] == IMAGE_URL


@pytest.mark.asyncio
async def test_a_top_refusing_a_layer_twice_ends_in_a_tagging_error(
    scripted: Callable[..., _ScriptedCompletions],
) -> None:
    # The give-up, tested against the rule that reaches it. An item finishing
    # `failed` with no tags is the accepted cost of refusing to guess (085): the
    # tile is visible and carries a retry button, where a wrong `layer` would
    # surface two stages later as a bad look with nothing pointing back here.
    completions = scripted(_raw(layer="standalone"))

    with pytest.raises(vision.TaggingError, match="layer 'standalone' is not valid"):
        await vision.validate_tags(_raw(layer="standalone"), IMAGE_URL)

    # One call, not two: the first answer was the caller's, made in 1.3.
    assert len(completions.calls) == 1


@pytest.mark.asyncio
async def test_the_tagging_error_carries_the_second_violation(
    scripted: Callable[..., _ScriptedCompletions],
) -> None:
    # 1.3 stores this in items.error_message, so it describes the answer that was
    # actually rejected rather than the one before it.
    completions = scripted(_raw(category="top", subcategory="jeans"))

    with pytest.raises(vision.TaggingError, match="subcategory 'jeans' is not valid"):
        await vision.validate_tags(_raw(layer="standalone"), IMAGE_URL)

    assert len(completions.calls) == 1


@pytest.mark.asyncio
async def test_only_the_accepted_answers_coercions_are_carried(
    scripted: Callable[..., _ScriptedCompletions],
) -> None:
    # The rejected answer's `fit` describes tags that were never written.
    # Carrying it would let 1.3 record "fit was discarded" beside a row whose
    # fit came back fine on the retry.
    scripted(_raw(fit="oversized"))

    tags = await vision.validate_tags(_raw(layer="standalone", fit="flared"), IMAGE_URL)

    assert tags.fit is Fit.OVERSIZED
    assert tags.coerced == ()


@pytest.mark.asyncio
async def test_the_rejected_answers_coercion_is_still_logged(
    scripted: Callable[..., _ScriptedCompletions], caplog: pytest.LogCaptureFixture
) -> None:
    # Which is why dropping it from the result loses nothing: the log is where a
    # missing vocabulary word is mined from, and it records both attempts.
    scripted(_raw(fit="oversized"))

    with caplog.at_level(logging.WARNING, logger="app.services.vision"):
        await vision.validate_tags(_raw(layer="standalone", fit="flared"), IMAGE_URL)

    coerced = [r for r in caplog.records if r.getMessage() == "Vision tag coerced"]
    assert [(r.attempt, r.value) for r in coerced] == [(1, "flared")]


@pytest.mark.asyncio
async def test_the_give_up_is_logged_as_an_error(
    scripted: Callable[..., _ScriptedCompletions], caplog: pytest.LogCaptureFixture
) -> None:
    scripted(_raw(layer="standalone"))

    with (
        caplog.at_level(logging.WARNING, logger="app.services.vision"),
        pytest.raises(vision.TaggingError),
    ):
        await vision.validate_tags(_raw(layer="standalone"), IMAGE_URL)

    levels = [r.levelno for r in caplog.records if r.getMessage().startswith("Vision tags")]
    assert levels == [logging.WARNING, logging.ERROR]


@pytest.mark.asyncio
async def test_a_retry_that_returns_nothing_usable_is_not_relabelled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A ValueError says no answer arrived, which is a different fact from an
    # answer that could not be accepted. 1.3 catches both and keeps them apart
    # in error_message, so validate_tags does not flatten one into the other.
    monkeypatch.setattr(settings, "USE_FAKE_AI", False)
    completions = _RecordingCompletions(None, finish_reason="length")
    client = type("Client", (), {"chat": type("Chat", (), {"completions": completions})()})()
    monkeypatch.setattr(vision, "_client", lambda: client)

    with pytest.raises(ValueError):
        await vision.validate_tags(_raw(layer="standalone"), IMAGE_URL)


# --- validate_tags: the fields the schema types with no null ------------------


def test_the_required_fields_are_the_eleven_with_no_null_in_the_schema() -> None:
    # Literal, for the same reason as the tables in test_enums.py: every test
    # below reads this tuple, so a mutation of it would move them all together.
    assert vision._REQUIRED_FIELDS == (
        "category",
        "subcategory",
        "color_primary",
        "pattern",
        "material",
        "formality",
        "warmth",
        "layer",
        "water_resistant",
        "display_name",
        "confidence",
    )


def test_no_required_field_is_nullable_in_the_schema() -> None:
    # A second reading of the same claim, from the schema rather than the tuple:
    # required here means "the schema types it with no null", and the four
    # fields that are nullable are exactly the ones left out.
    properties = vision.VISION_SCHEMA["schema"]["properties"]
    nullable = {name for name, spec in properties.items() if "null" in spec["type"]}

    assert set(vision._REQUIRED_FIELDS) == set(properties) - nullable


@pytest.mark.parametrize(
    "field",
    [
        "category",
        "subcategory",
        "color_primary",
        "pattern",
        "material",
        "formality",
        "warmth",
        "layer",
        "water_resistant",
        "display_name",
        "confidence",
    ],
)
@pytest.mark.asyncio
async def test_a_missing_required_field_is_retried_naming_the_field(
    scripted: Callable[..., _ScriptedCompletions], field: str
) -> None:
    # Stated literally rather than parametrised from _REQUIRED_FIELDS: a
    # parametrisation read from the thing under test moves the failure from a
    # named test to collection, which is easy to misread as a survivor.
    completions = scripted(_raw())
    short = _raw()
    del short[field]

    await vision.validate_tags(short, IMAGE_URL)

    assert f"{field} must be present and not empty" in _correction(completions)


@pytest.mark.asyncio
async def test_a_null_required_field_counts_as_missing(
    scripted: Callable[..., _ScriptedCompletions],
) -> None:
    # validate_tag_dict reads every field with .get, so a null and an absent key
    # are the same thing there and both pass — correct for PATCH's partial
    # bodies, and wrong as input to a typed object.
    completions = scripted(_raw())

    await vision.validate_tags(_raw(display_name=None), IMAGE_URL)

    assert "display_name must be present and not empty" in _correction(completions)


@pytest.mark.asyncio
async def test_a_blank_display_name_counts_as_missing(
    scripted: Callable[..., _ScriptedCompletions],
) -> None:
    # A tile with nothing written on it is a visible defect where the other ten
    # required fields fail structurally.
    completions = scripted(_raw())

    await vision.validate_tags(_raw(display_name="   "), IMAGE_URL)

    assert "display_name must be present and not empty" in _correction(completions)


@pytest.mark.asyncio
async def test_a_false_water_resistant_is_not_missing(
    scripted: Callable[..., _ScriptedCompletions],
) -> None:
    # The falsy trap: `is None` rather than truthiness, or every garment that is
    # not water resistant is retried and then failed.
    completions = scripted()

    tags = await vision.validate_tags(_raw(water_resistant=False), IMAGE_URL)

    assert completions.calls == []
    assert tags.water_resistant is False


@pytest.mark.asyncio
async def test_a_required_field_missing_twice_ends_in_a_tagging_error(
    scripted: Callable[..., _ScriptedCompletions],
) -> None:
    short = _raw()
    del short["display_name"]
    completions = scripted(short)

    with pytest.raises(vision.TaggingError, match="display_name must be present"):
        await vision.validate_tags(short, IMAGE_URL)

    assert len(completions.calls) == 1
