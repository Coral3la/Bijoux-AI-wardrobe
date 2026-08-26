"""The wardrobe as the stylist prompt carries it: one compact line per item.

The format is `03-AI-CONTRACTS.md`'s and that document is authoritative. It is
**positional** — the model is given no key — so a null in the middle of a line
cannot simply be dropped: every later value would shift one column left and be
read as the wrong attribute. The core slots are therefore always written, with
an em dash where there is no value, and only the trailing extras are omitted.
`STAGE-2` 2.3's one-line "omit nulls" is the narrower half of that rule.
`DECISIONS.md` 156.

`short_id` is not upper-cased here. `app/core/short_id.py`'s alphabet has no
lower case in it, so `.upper()` could never change a character — the ids arrive
uppercase and the stage file's requirement is met by construction rather than by
a line of code. Normalising what the *model* sends back is a different problem
and belongs to `validate_look_response` at 2.5.

Pure, and it applies no filter of its own: it serialises exactly the items it is
handed. `ready`-only, `is_archived` and the swimwear/sleepwear exclusion are the
caller's at 2.7 — a serialiser that also decided membership could not be tested
as a format.
"""

from collections.abc import Iterable
from typing import Final

from app.schemas.item import ItemResponse

# U+2014. Transcribed from `03-AI-CONTRACTS.md`'s worked example, which has used
# it for the shoe with no `fit` since Stage 0.
MISSING: Final = "—"

_SEPARATOR: Final = " | "


def _slot(value: str | int | None) -> str:
    return MISSING if value is None else str(value)


def _extras(item: ItemResponse) -> list[str]:
    extras: list[str] = []
    if item.rise is not None:
        extras.append(f"rise:{item.rise}")
    if item.water_resistant:
        extras.append("water_resistant")
    return extras


def _line(item: ItemResponse) -> str:
    return _SEPARATOR.join(
        [
            item.short_id,
            f"{_slot(item.category)}/{_slot(item.subcategory)}",
            _slot(item.fit),
            _slot(item.length),
            _slot(item.color_primary),
            _slot(item.color_secondary),
            _slot(item.pattern),
            _slot(item.material),
            f"F{_slot(item.formality)} W{_slot(item.warmth)}",
            _slot(item.layer),
            *_extras(item),
        ]
    )


def serialize_wardrobe(items: Iterable[ItemResponse]) -> str:
    return "\n".join(_line(item) for item in items)
