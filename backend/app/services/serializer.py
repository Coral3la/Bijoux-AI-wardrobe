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

**`set:<n>` at 4A.1 is the one extra that is not a property of its own item.**
Every other slot on a line is read off the row; this one is read off the
*wardrobe*, because `n` is a per-request ordinal over the sets that survive to
be serialised and a set with one surviving member gets no token at all. So the
function makes two passes, and the list is materialised for it — the ordinals
have to be known before the first line is written.

**`serialize_sets` is the second public function, and it states what those
tokens only imply.** A repeated `set:1` on two non-adjacent lines of a long list
is a pairing the reader has to notice; the block names it. It reads the same
`_set_ordinals`, so the block and the lines can never disagree about which set
is which — that shared reading is why it lives here rather than in the message
that prints it. The blank line under the block does not: `stylist.py` owns the
assembly, this module owns the format.
"""

import uuid
from collections import Counter
from collections.abc import Iterable, Sequence
from typing import Final

from app.schemas.item import ItemResponse

# U+2014. Transcribed from `03-AI-CONTRACTS.md`'s worked example, which has used
# it for the shoe with no `fit` since Stage 0.
MISSING: Final = "—"

_SEPARATOR: Final = " | "


def _slot(value: str | int | None) -> str:
    return MISSING if value is None else str(value)


def _set_ordinals(items: Sequence[ItemResponse]) -> dict[uuid.UUID, int]:
    """`1, 2, 3 …` over the sets that have more than one member in this list.

    **The ordinal is not the set's id**, which is `04-API-SPEC.md`'s standing
    rule that `short_id` is the only identifier the model ever sees — and about
    twelve tokens per member cheaper for saying the same thing.

    **A set with one surviving member is left out entirely**, so the ordinals
    stay contiguous. Its siblings were filtered out before serialisation —
    archived, `processing`, `failed`, or in an excluded category — and a `set:`
    token on a single line names a grouping the model cannot act on: there is
    nothing to pair the garment with. It is this function's reading of the rule
    `routes/sets.py` enforces on the way in, that fewer than two members is not
    a set.

    Numbered by first appearance rather than by count or by id, so the same
    wardrobe in the same order always produces the same lines.
    """
    members = Counter(item.set_id for item in items if item.set_id is not None)
    ordinals: dict[uuid.UUID, int] = {}
    for item in items:
        if item.set_id is None or members[item.set_id] < 2 or item.set_id in ordinals:
            continue
        ordinals[item.set_id] = len(ordinals) + 1
    return ordinals


def _extras(item: ItemResponse, set_ordinals: dict[uuid.UUID, int]) -> list[str]:
    # `rise`, `water_resistant`, then `set`. All three are reachable on one item
    # — a waterproof trouser that came with a jacket has each — and the order is
    # arbitrary but fixed, so a line is a function of the item rather than of
    # the order the code happened to test three flags in. `set` was appended
    # rather than inserted at 4A.1, so that no existing line changes shape.
    extras: list[str] = []
    if item.rise is not None:
        extras.append(f"rise:{item.rise}")
    if item.water_resistant:
        extras.append("water_resistant")
    if item.set_id in set_ordinals:
        extras.append(f"set:{set_ordinals[item.set_id]}")
    return extras


def _line(item: ItemResponse, set_ordinals: dict[uuid.UUID, int]) -> str:
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
            *_extras(item, set_ordinals),
        ]
    )


def serialize_wardrobe(items: Iterable[ItemResponse]) -> str:
    # Materialised because the set ordinals are a property of the whole list and
    # have to be counted before any line is written. The parameter stays
    # `Iterable` — every caller passes a list already.
    wardrobe = list(items)
    set_ordinals = _set_ordinals(wardrobe)
    return "\n".join(_line(item, set_ordinals) for item in wardrobe)


def serialize_sets(items: Iterable[ItemResponse]) -> str:
    """The pairing stated, rather than left to be inferred from the lines.

        SETS:
        set 1 = Z94NTD + 4G988B
        set 2 = D7HFST + DM5J59

    Sets in ordinal order and members in the order they appear in the wardrobe,
    so the block reads down the same list the lines were written from.

    **Empty when no set has two surviving members**, which is `_set_ordinals`'
    own rule reused rather than restated — the caller then omits the heading
    instead of printing it over nothing.
    """
    wardrobe = list(items)
    ordinals = _set_ordinals(wardrobe)
    if not ordinals:
        return ""
    members: dict[uuid.UUID, list[str]] = {set_id: [] for set_id in ordinals}
    for item in wardrobe:
        if item.set_id in members:
            members[item.set_id].append(item.short_id)
    return "SETS:\n" + "\n".join(
        f"set {ordinals[set_id]} = {' + '.join(short_ids)}" for set_id, short_ids in members.items()
    )
