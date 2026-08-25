"""The demo wardrobe, built from a committed table rather than from the AI.

Two modes that do not overlap. The default reads `SEED_ITEMS` — Cloudinary
`public_id`s and hand-written tags — and writes rows, making no network call
but the database one. `--upload DIR` sends a folder of images to Cloudinary and
logs the table to paste back into this file; it writes no rows.

No AI call is made, so the wardrobe a defence is given is the same wardrobe
every time. What replaces the model is `validate_tag_dict`, run over every row
before anything is inserted, on `PATCH /items/{id}`'s policy rather than the
vision path's: any error **and any coercion** aborts the run. A coercion here
means the table holds a value the vocabulary does not admit, and a silently
nulled seed tag is a demo item with a hole in it. `DECISIONS.md` 130.

Run it from `backend/`, as a module:

    python -m scripts.seed_demo --yes

`python scripts/seed_demo.py` cannot work. That form puts `backend/scripts` on
`sys.path` instead of `backend/`, so `import app` raises — the same gap
`pyproject.toml`'s `pythonpath = ["."]` closes for pytest.
"""

import argparse
import logging
import sys
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import func, select
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import configure_logging
from app.core.security import hash_password
from app.core.short_id import generate_short_id
from app.db.session import SessionLocal
from app.enums import REQUIRED_TAG_FIELDS, ItemStatus, validate_tag_dict
from app.models.item import Item
from app.models.user import User
from app.services.storage import upload_image, validate_image

logger = logging.getLogger(__name__)

# Published, not secret. This account is the demo and its credentials are in
# `frontend/src/app/features/auth/login.page.ts` as well, where the button that
# signs a visitor in has to know them. `07-DEPLOYMENT.md` says so out loud so
# that nobody finds this string and reports it as a leaked password.
DEMO_EMAIL = "demo@bijoux.app"
DEMO_PASSWORD = "bijoux-demo-wardrobe"
DEMO_DISPLAY_NAME = "Demo wardrobe"

# Pinned rather than generated. `--upload` has to name a folder
# (`bijoux/{user_id}/`) before any row exists, and `--reset` deletes the user,
# so an id minted per run would leave every committed `public_id` in the folder
# of a user that no longer exists — the orphan problem `STAGE-0` 0.6 named,
# made permanent and widened on every reset. `User.id`'s server default only
# fires when no value is supplied, so passing one is legal and changes nothing
# else. `DECISIONS.md` 132.
DEMO_USER_ID = uuid.UUID("01821186-a63e-4b4b-8fef-7a83d6377056")

# Bumped by hand when the table below changes in a way worth telling apart on a
# row that was seeded before the change.
SEED_VERSION = 1

# 31**6 is 8.9e8 and this table is tens of rows, so a collision is not expected;
# catching it is what makes that a claim rather than a hope. Same insert-and-
# catch shape as `items.py`, for the reason `DECISIONS.md` 432 gives.
SHORT_ID_ATTEMPTS = 3


@dataclass(frozen=True, slots=True)
class SeedItem:
    """One committed row: where the photograph came from, where it now lives,
    and what it is. `tags` keys are `items` column names, so the dict is
    splatted into the model unchanged."""

    source: str
    public_id: str
    tags: dict[str, Any] = field(default_factory=dict)
    status: str = ItemStatus.READY
    error_message: str | None = None


# Filled in by hand from `--upload`'s output. Every row was tagged from the
# photograph rather than from its filename; `DECISIONS.md` 141 has the rate at
# which filenames were wrong and why the silent columns are the ones that matter.
SEED_ITEMS: tuple[SeedItem, ...] = (
    SeedItem(
        source="01-top-blouse-beige-satin.jpg",
        public_id="bijoux/01821186-a63e-4b4b-8fef-7a83d6377056/cheic2osnpks38dunkim",
        tags={
            "category": "top",
            "subcategory": "blouse",
            "fit": "relaxed",
            "length": "long_sleeve",
            "rise": None,
            "color_primary": "beige",
            "color_secondary": None,
            "pattern": "solid",
            "material": "silk",
            "formality": 3,
            "warmth": 1,
            "layer": "base",
            "water_resistant": False,
            "display_name": "beige satin blouse",
        },
    ),
    SeedItem(
        source="02-top-blouse-pink-linen.jpg",
        public_id="bijoux/01821186-a63e-4b4b-8fef-7a83d6377056/r41ofuitqr7fxyw6nebv",
        tags={
            "category": "top",
            "subcategory": "blouse",
            "fit": "oversized",
            "length": "long_sleeve",
            "rise": None,
            "color_primary": "pink",
            "color_secondary": None,
            "pattern": "solid",
            "material": "linen",
            "formality": 3,
            "warmth": 1,
            "layer": "base",
            "water_resistant": False,
            "display_name": "pink linen shirt",
        },
    ),
    SeedItem(
        source="03-top-bodysuit-black.jpg",
        public_id="bijoux/01821186-a63e-4b4b-8fef-7a83d6377056/u82jlhffv3jjdf8uvxhr",
        tags={
            "category": "top",
            "subcategory": "bodysuit",
            "fit": "slim",
            "length": "sleeveless",
            "rise": None,
            "color_primary": "black",
            "color_secondary": None,
            "pattern": "solid",
            "material": "synthetic",
            "formality": 3,
            "warmth": 2,
            "layer": "base",
            "water_resistant": False,
            "display_name": "black sleeveless bodysuit",
        },
    ),
    SeedItem(
        source="04-top-bodysuit-white.jpg",
        public_id="bijoux/01821186-a63e-4b4b-8fef-7a83d6377056/y9rgcxubfg3fdgsqw75b",
        tags={
            "category": "top",
            "subcategory": "bodysuit",
            "fit": "slim",
            "length": "sleeveless",
            "rise": None,
            "color_primary": "white",
            "color_secondary": None,
            "pattern": "solid",
            "material": "synthetic",
            "formality": 3,
            "warmth": 2,
            "layer": "base",
            "water_resistant": False,
            "display_name": "white sleeveless bodysuit",
        },
    ),
    SeedItem(
        source="05-top-sweater-beige-rollneck.jpg",
        public_id="bijoux/01821186-a63e-4b4b-8fef-7a83d6377056/ld1dbiv2yhor7kb9ucpy",
        tags={
            "category": "top",
            "subcategory": "sweater",
            "fit": "oversized",
            "length": "long_sleeve",
            "rise": None,
            "color_primary": "beige",
            "color_secondary": None,
            "pattern": "solid",
            "material": "knit",
            "formality": 3,
            "warmth": 3,
            "layer": "mid",
            "water_resistant": False,
            "display_name": "beige ribbed roll-neck knit",
        },
    ),
    SeedItem(
        source="06-top-sweater-beige-pointelle.jpg",
        public_id="bijoux/01821186-a63e-4b4b-8fef-7a83d6377056/dvva0uwbdipfgpaow95c",
        tags={
            "category": "top",
            "subcategory": "sweater",
            "fit": "slim",
            "length": "long_sleeve",
            "rise": None,
            "color_primary": "beige",
            "color_secondary": None,
            "pattern": "solid",
            "material": "knit",
            "formality": 3,
            "warmth": 3,
            "layer": "mid",
            "water_resistant": False,
            "display_name": "cream pointelle collared knit",
        },
    ),
    SeedItem(
        source="07-top-sweater-white-waffle.jpg",
        public_id="bijoux/01821186-a63e-4b4b-8fef-7a83d6377056/qx8lmarosh5p36imoa1r",
        tags={
            "category": "top",
            "subcategory": "sweater",
            "fit": "relaxed",
            "length": "long_sleeve",
            "rise": None,
            "color_primary": "white",
            "color_secondary": None,
            "pattern": "solid",
            "material": "knit",
            "formality": 3,
            "warmth": 2,
            "layer": "mid",
            "water_resistant": False,
            "display_name": "white waffle-knit top",
        },
    ),
    SeedItem(
        source="08-top-t_shirt-black-longsleeve.jpg",
        public_id="bijoux/01821186-a63e-4b4b-8fef-7a83d6377056/gp8on5fj7hojebrvehp6",
        tags={
            "category": "top",
            "subcategory": "t_shirt",
            "fit": "slim",
            "length": "long_sleeve",
            "rise": None,
            "color_primary": "black",
            "color_secondary": None,
            "pattern": "solid",
            "material": "cotton",
            "formality": 2,
            "warmth": 2,
            "layer": "base",
            "water_resistant": False,
            "display_name": "black ribbed long-sleeve top",
        },
    ),
    SeedItem(
        source="09-top-t_shirt-light_blue-vneck.jpg",
        public_id="bijoux/01821186-a63e-4b4b-8fef-7a83d6377056/btrbwdjabfmggzmajfab",
        tags={
            "category": "top",
            "subcategory": "t_shirt",
            "fit": "relaxed",
            "length": "short_sleeve",
            "rise": None,
            "color_primary": "light_blue",
            "color_secondary": None,
            "pattern": "solid",
            "material": "cotton",
            "formality": 2,
            "warmth": 2,
            "layer": "base",
            "water_resistant": False,
            "display_name": "light blue V-neck t-shirt",
        },
    ),
    SeedItem(
        source="10-top-t_shirt-black-vneck.jpg",
        public_id="bijoux/01821186-a63e-4b4b-8fef-7a83d6377056/q4bg2m50pkqehqkggpto",
        tags={
            "category": "top",
            "subcategory": "t_shirt",
            "fit": "relaxed",
            "length": "short_sleeve",
            "rise": None,
            "color_primary": "black",
            "color_secondary": None,
            "pattern": "solid",
            "material": "cotton",
            "formality": 2,
            "warmth": 2,
            "layer": "base",
            "water_resistant": False,
            "display_name": "black V-neck t-shirt",
        },
    ),
    SeedItem(
        source="11-top-t_shirt-white-vneck.jpg",
        public_id="bijoux/01821186-a63e-4b4b-8fef-7a83d6377056/tkczaxdrnd6hxmfrufwa",
        tags={
            "category": "top",
            "subcategory": "t_shirt",
            "fit": "relaxed",
            "length": "short_sleeve",
            "rise": None,
            "color_primary": "white",
            "color_secondary": None,
            "pattern": "solid",
            "material": "linen",
            "formality": 2,
            "warmth": 2,
            "layer": "base",
            "water_resistant": False,
            "display_name": "white V-neck t-shirt",
        },
    ),
    SeedItem(
        source="12-top-tank-blue-turquoise-satin.jpg",
        public_id="bijoux/01821186-a63e-4b4b-8fef-7a83d6377056/c6u6uvs7ddhpzwq9o7cw",
        tags={
            "category": "top",
            "subcategory": "tank",
            "fit": "slim",
            "length": "sleeveless",
            "rise": None,
            "color_primary": "blue",
            "color_secondary": None,
            "pattern": "solid",
            "material": "silk",
            "formality": 3,
            "warmth": 1,
            "layer": "base",
            "water_resistant": False,
            "display_name": "turquoise satin cami",
        },
    ),
    SeedItem(
        source="13-top-tank-beige-satin.jpg",
        public_id="bijoux/01821186-a63e-4b4b-8fef-7a83d6377056/geztdihrursxk2aqxfrp",
        tags={
            "category": "top",
            "subcategory": "tank",
            "fit": "slim",
            "length": "sleeveless",
            "rise": None,
            "color_primary": "beige",
            "color_secondary": None,
            "pattern": "solid",
            "material": "silk",
            "formality": 3,
            "warmth": 1,
            "layer": "base",
            "water_resistant": False,
            "display_name": "beige satin cami",
        },
    ),
    SeedItem(
        source="14-top-tank-black-velvet.jpg",
        public_id="bijoux/01821186-a63e-4b4b-8fef-7a83d6377056/edyt57uybg9a2u3x4l0u",
        tags={
            "category": "top",
            "subcategory": "tank",
            "fit": "slim",
            "length": "sleeveless",
            "rise": None,
            "color_primary": "black",
            "color_secondary": None,
            "pattern": "solid",
            "material": "other",
            "formality": 3,
            "warmth": 2,
            "layer": "base",
            "water_resistant": False,
            "display_name": "black velvet cami",
        },
    ),
    SeedItem(
        source="15-top-tank-black-halter.jpg",
        public_id="bijoux/01821186-a63e-4b4b-8fef-7a83d6377056/mnrdk0lrbhgwp3m6vdfn",
        tags={
            "category": "top",
            "subcategory": "tank",
            "fit": "slim",
            "length": "sleeveless",
            "rise": None,
            "color_primary": "black",
            "color_secondary": None,
            "pattern": "solid",
            "material": "cotton",
            "formality": 3,
            "warmth": 1,
            "layer": "base",
            "water_resistant": False,
            "display_name": "black textured halter top",
        },
    ),
    SeedItem(
        source="16-top-tank-brown-ribbed.jpg",
        public_id="bijoux/01821186-a63e-4b4b-8fef-7a83d6377056/eyylttvcjc3nrtjfjc5i",
        tags={
            "category": "top",
            "subcategory": "tank",
            "fit": "slim",
            "length": "sleeveless",
            "rise": None,
            "color_primary": "brown",
            "color_secondary": None,
            "pattern": "solid",
            "material": "cotton",
            "formality": 2,
            "warmth": 1,
            "layer": "base",
            "water_resistant": False,
            "display_name": "brown ribbed tank",
        },
    ),
    SeedItem(
        source="17-top-tank-brown-halter.jpg",
        public_id="bijoux/01821186-a63e-4b4b-8fef-7a83d6377056/gvqeyaiovsihevqgv9kx",
        tags={
            "category": "top",
            "subcategory": "tank",
            "fit": "slim",
            "length": "sleeveless",
            "rise": None,
            "color_primary": "brown",
            "color_secondary": None,
            "pattern": "solid",
            "material": "cotton",
            "formality": 3,
            "warmth": 1,
            "layer": "base",
            "water_resistant": False,
            "display_name": "brown textured halter top",
        },
    ),
    SeedItem(
        source="18-top-tank-beige-animal.jpg",
        public_id="bijoux/01821186-a63e-4b4b-8fef-7a83d6377056/fmeryutnh0ma8u7cwalz",
        tags={
            "category": "top",
            "subcategory": "tank",
            "fit": "slim",
            "length": "sleeveless",
            "rise": None,
            "color_primary": "beige",
            "color_secondary": "brown",
            "pattern": "animal",
            "material": "silk",
            "formality": 3,
            "warmth": 1,
            "layer": "base",
            "water_resistant": False,
            "display_name": "animal-print cami",
        },
    ),
    SeedItem(
        source="19-top-tank-white-satin.jpg",
        public_id="bijoux/01821186-a63e-4b4b-8fef-7a83d6377056/roijwxg153ulpjt7zhyz",
        tags={
            "category": "top",
            "subcategory": "tank",
            "fit": "slim",
            "length": "sleeveless",
            "rise": None,
            "color_primary": "white",
            "color_secondary": None,
            "pattern": "solid",
            "material": "silk",
            "formality": 3,
            "warmth": 1,
            "layer": "base",
            "water_resistant": False,
            "display_name": "cream satin cami",
        },
    ),
    SeedItem(
        source="20-top-tank-white-ribbed.jpg",
        public_id="bijoux/01821186-a63e-4b4b-8fef-7a83d6377056/m0rgoomvjpqeebiaqimd",
        tags={
            "category": "top",
            "subcategory": "tank",
            "fit": "slim",
            "length": "sleeveless",
            "rise": None,
            "color_primary": "white",
            "color_secondary": None,
            "pattern": "solid",
            "material": "cotton",
            "formality": 2,
            "warmth": 1,
            "layer": "base",
            "water_resistant": False,
            "display_name": "white ribbed tank",
        },
    ),
    SeedItem(
        source="21-top-tank-yellow-satin.jpg",
        public_id="bijoux/01821186-a63e-4b4b-8fef-7a83d6377056/v0eizjaajya6jcnp3zsr",
        tags={
            "category": "top",
            "subcategory": "tank",
            "fit": "slim",
            "length": "sleeveless",
            "rise": None,
            "color_primary": "yellow",
            "color_secondary": None,
            "pattern": "solid",
            "material": "silk",
            "formality": 3,
            "warmth": 1,
            "layer": "base",
            "water_resistant": False,
            "display_name": "yellow satin cami",
        },
    ),
    SeedItem(
        source="22-bottom-jeans-light_blue-wide.jpg",
        public_id="bijoux/01821186-a63e-4b4b-8fef-7a83d6377056/v3fvryu17galq5wcas5i",
        tags={
            "category": "bottom",
            "subcategory": "jeans",
            "fit": "wide",
            "length": "full",
            "rise": "high",
            "color_primary": "light_blue",
            "color_secondary": None,
            "pattern": "denim_wash",
            "material": "denim",
            "formality": 2,
            "warmth": 2,
            "layer": "base",
            "water_resistant": False,
            "display_name": "light blue wide-leg jeans",
        },
    ),
    SeedItem(
        source="23-bottom-jeans-black-flare.jpg",
        public_id="bijoux/01821186-a63e-4b4b-8fef-7a83d6377056/aeuafqft3uruxqcsu3vl",
        tags={
            "category": "bottom",
            "subcategory": "jeans",
            "fit": "wide",
            "length": "full",
            "rise": "high",
            "color_primary": "black",
            "color_secondary": None,
            "pattern": "denim_wash",
            "material": "denim",
            "formality": 2,
            "warmth": 2,
            "layer": "base",
            "water_resistant": False,
            "display_name": "washed black flare jeans",
        },
    ),
    SeedItem(
        source="24-bottom-jeans-light_blue-straight.jpg",
        public_id="bijoux/01821186-a63e-4b4b-8fef-7a83d6377056/pqe3cgcb7xqqnwkopuut",
        tags={
            "category": "bottom",
            "subcategory": "jeans",
            "fit": "straight",
            "length": "ankle",
            "rise": "high",
            "color_primary": "light_blue",
            "color_secondary": None,
            "pattern": "denim_wash",
            "material": "denim",
            "formality": 2,
            "warmth": 2,
            "layer": "base",
            "water_resistant": False,
            "display_name": "pale blue straight jeans",
        },
    ),
    SeedItem(
        source="25-bottom-jeans-light_blue-mom.jpg",
        public_id="bijoux/01821186-a63e-4b4b-8fef-7a83d6377056/vjj0fbfdpxwljtbmuffn",
        tags={
            "category": "bottom",
            "subcategory": "jeans",
            "fit": "relaxed",
            "length": "ankle",
            "rise": "high",
            "color_primary": "light_blue",
            "color_secondary": None,
            "pattern": "denim_wash",
            "material": "denim",
            "formality": 2,
            "warmth": 2,
            "layer": "base",
            "water_resistant": False,
            "display_name": "light blue mom jeans",
        },
    ),
    SeedItem(
        source="26-bottom-jeans-black-skinny.jpg",
        public_id="bijoux/01821186-a63e-4b4b-8fef-7a83d6377056/zwisahxwkqybjirwgynn",
        tags={
            "category": "bottom",
            "subcategory": "jeans",
            "fit": "skinny",
            "length": "full",
            "rise": "high",
            "color_primary": "black",
            "color_secondary": None,
            "pattern": "denim_wash",
            "material": "denim",
            "formality": 2,
            "warmth": 2,
            "layer": "base",
            "water_resistant": False,
            "display_name": "black skinny jeans",
        },
    ),
    SeedItem(
        source="27-bottom-shorts-beige-boucle.jpg",
        public_id="bijoux/01821186-a63e-4b4b-8fef-7a83d6377056/nviaaelrq532jts7my6l",
        tags={
            "category": "bottom",
            "subcategory": "shorts",
            "fit": "straight",
            "length": "mini",
            "rise": "high",
            "color_primary": "beige",
            "color_secondary": None,
            "pattern": "solid",
            "material": "knit",
            "formality": 3,
            "warmth": 2,
            "layer": "base",
            "water_resistant": False,
            "display_name": "cream boucle shorts",
        },
    ),
    SeedItem(
        source="28-bottom-shorts-black-boucle.jpg",
        public_id="bijoux/01821186-a63e-4b4b-8fef-7a83d6377056/obudjqk87fbp28ydkvet",
        tags={
            "category": "bottom",
            "subcategory": "shorts",
            "fit": "straight",
            "length": "mini",
            "rise": "high",
            "color_primary": "black",
            "color_secondary": None,
            "pattern": "solid",
            "material": "knit",
            "formality": 3,
            "warmth": 2,
            "layer": "base",
            "water_resistant": False,
            "display_name": "black boucle shorts",
        },
    ),
    SeedItem(
        source="29-bottom-shorts-white-lounge.jpg",
        public_id="bijoux/01821186-a63e-4b4b-8fef-7a83d6377056/j7iophhjhcynndexyj5t",
        tags={
            "category": "bottom",
            "subcategory": "shorts",
            "fit": "relaxed",
            "length": "mini",
            "rise": "mid",
            "color_primary": "white",
            "color_secondary": None,
            "pattern": "floral",
            "material": "silk",
            "formality": 1,
            "warmth": 1,
            "layer": "base",
            "water_resistant": False,
            "display_name": "white satin lounge shorts",
        },
    ),
    SeedItem(
        source="30-bottom-shorts-white-tailored.jpg",
        public_id="bijoux/01821186-a63e-4b4b-8fef-7a83d6377056/iszoelqtgvd2sjyp4aj2",
        tags={
            "category": "bottom",
            "subcategory": "shorts",
            "fit": "straight",
            "length": "mini",
            "rise": "high",
            "color_primary": "white",
            "color_secondary": None,
            "pattern": "solid",
            "material": "synthetic",
            "formality": 3,
            "warmth": 2,
            "layer": "base",
            "water_resistant": False,
            "display_name": "cream tailored shorts",
        },
    ),
    SeedItem(
        source="31-bottom-trousers-beige-tailored.jpg",
        public_id="bijoux/01821186-a63e-4b4b-8fef-7a83d6377056/srrbscy7zqifjm6wnx0u",
        tags={
            "category": "bottom",
            "subcategory": "trousers",
            "fit": "wide",
            "length": "full",
            "rise": "mid",
            "color_primary": "beige",
            "color_secondary": None,
            "pattern": "solid",
            "material": "synthetic",
            "formality": 4,
            "warmth": 2,
            "layer": "base",
            "water_resistant": False,
            "display_name": "beige tailored trousers",
        },
    ),
    SeedItem(
        source="32-bottom-trousers-beige-linen-wide.jpg",
        public_id="bijoux/01821186-a63e-4b4b-8fef-7a83d6377056/aw3vrujahiuglzacv956",
        tags={
            "category": "bottom",
            "subcategory": "trousers",
            "fit": "wide",
            "length": "full",
            "rise": "high",
            "color_primary": "beige",
            "color_secondary": None,
            "pattern": "solid",
            "material": "linen",
            "formality": 3,
            "warmth": 2,
            "layer": "base",
            "water_resistant": False,
            "display_name": "beige linen wide-leg trousers",
        },
    ),
    SeedItem(
        source="33-bottom-trousers-black-tailored.jpg",
        public_id="bijoux/01821186-a63e-4b4b-8fef-7a83d6377056/w68apqlvnwn6ew1sskhg",
        tags={
            "category": "bottom",
            "subcategory": "trousers",
            "fit": "wide",
            "length": "full",
            "rise": "mid",
            "color_primary": "black",
            "color_secondary": None,
            "pattern": "solid",
            "material": "synthetic",
            "formality": 4,
            "warmth": 2,
            "layer": "base",
            "water_resistant": False,
            "display_name": "black tailored trousers",
        },
    ),
    SeedItem(
        source="34-bottom-trousers-black-crinkle.jpg",
        public_id="bijoux/01821186-a63e-4b4b-8fef-7a83d6377056/wwk9r0po8hpfa4qyssw5",
        tags={
            "category": "bottom",
            "subcategory": "trousers",
            "fit": "wide",
            "length": "full",
            "rise": "high",
            "color_primary": "black",
            "color_secondary": None,
            "pattern": "solid",
            "material": "other",
            "formality": 3,
            "warmth": 2,
            "layer": "base",
            "water_resistant": False,
            "display_name": "black crinkle wide-leg trousers",
        },
    ),
    SeedItem(
        source="35-bottom-trousers-brown-crinkle.jpg",
        public_id="bijoux/01821186-a63e-4b4b-8fef-7a83d6377056/ct2lzlrsc8q6vuiorgrg",
        tags={
            "category": "bottom",
            "subcategory": "trousers",
            "fit": "wide",
            "length": "full",
            "rise": "high",
            "color_primary": "brown",
            "color_secondary": None,
            "pattern": "solid",
            "material": "other",
            "formality": 3,
            "warmth": 2,
            "layer": "base",
            "water_resistant": False,
            "display_name": "brown crinkle wide-leg trousers",
        },
    ),
    SeedItem(
        source="36-bottom-trousers-olive-kaki.jpg",
        public_id="bijoux/01821186-a63e-4b4b-8fef-7a83d6377056/vmfdxoxi7fyf6xvigakl",
        tags={
            "category": "bottom",
            "subcategory": "trousers",
            "fit": "straight",
            "length": "full",
            "rise": "mid",
            "color_primary": "olive",
            "color_secondary": None,
            "pattern": "solid",
            "material": "synthetic",
            "formality": 3,
            "warmth": 2,
            "layer": "base",
            "water_resistant": False,
            "display_name": "khaki straight trousers",
        },
    ),
    SeedItem(
        source="37-dress-dress-black-lace-maxi.jpg",
        public_id="bijoux/01821186-a63e-4b4b-8fef-7a83d6377056/hhtrlgrudcswxntarebz",
        tags={
            "category": "dress",
            "subcategory": "dress",
            "fit": "slim",
            "length": "maxi",
            "rise": None,
            "color_primary": "black",
            "color_secondary": None,
            "pattern": "solid",
            "material": "silk",
            "formality": 5,
            "warmth": 1,
            "layer": "standalone",
            "water_resistant": False,
            "display_name": "black lace-trim slip gown",
        },
    ),
    SeedItem(
        source="38-dress-dress-navy-maxi.jpg",
        public_id="bijoux/01821186-a63e-4b4b-8fef-7a83d6377056/pm80mm3ezboxqbr90uu5",
        tags={
            "category": "dress",
            "subcategory": "dress",
            "fit": "slim",
            "length": "maxi",
            "rise": None,
            "color_primary": "navy",
            "color_secondary": None,
            "pattern": "solid",
            "material": "silk",
            "formality": 4,
            "warmth": 1,
            "layer": "standalone",
            "water_resistant": False,
            "display_name": "navy satin slip dress",
        },
    ),
    SeedItem(
        source="39-dress-dress-green-lace-midi.jpg",
        public_id="bijoux/01821186-a63e-4b4b-8fef-7a83d6377056/wyqxfo0xpodyee4xia0a",
        tags={
            "category": "dress",
            "subcategory": "dress",
            "fit": "slim",
            "length": "mini",
            "rise": None,
            "color_primary": "green",
            "color_secondary": None,
            "pattern": "floral",
            "material": "synthetic",
            "formality": 4,
            "warmth": 2,
            "layer": "standalone",
            "water_resistant": False,
            "display_name": "green lace mini dress",
        },
    ),
    SeedItem(
        source="40-dress-dress-orange-mini.jpg",
        public_id="bijoux/01821186-a63e-4b4b-8fef-7a83d6377056/zwh2wizkdotnczf5r3cf",
        tags={
            "category": "dress",
            "subcategory": "dress",
            "fit": "bodycon",
            "length": "mini",
            "rise": None,
            "color_primary": "orange",
            "color_secondary": None,
            "pattern": "solid",
            "material": "synthetic",
            "formality": 3,
            "warmth": 1,
            "layer": "standalone",
            "water_resistant": False,
            "display_name": "orange ruched mini dress",
        },
    ),
    SeedItem(
        source="41-dress-dress-pink-maxi.jpg",
        public_id="bijoux/01821186-a63e-4b4b-8fef-7a83d6377056/qtzbmcpyu143maofg22u",
        tags={
            "category": "dress",
            "subcategory": "dress",
            "fit": "slim",
            "length": "maxi",
            "rise": None,
            "color_primary": "pink",
            "color_secondary": None,
            "pattern": "solid",
            "material": "silk",
            "formality": 5,
            "warmth": 1,
            "layer": "standalone",
            "water_resistant": False,
            "display_name": "fuchsia satin slip gown",
        },
    ),
    SeedItem(
        source="42-outerwear-blazer-light_blue.jpg",
        public_id="bijoux/01821186-a63e-4b4b-8fef-7a83d6377056/ervgzq17laa7qxuzy1aw",
        tags={
            "category": "outerwear",
            "subcategory": "blazer",
            "fit": "relaxed",
            "length": "regular",
            "rise": None,
            "color_primary": "light_blue",
            "color_secondary": None,
            "pattern": "solid",
            "material": "synthetic",
            "formality": 4,
            "warmth": 3,
            "layer": "mid",
            "water_resistant": False,
            "display_name": "light blue double-breasted blazer",
        },
    ),
    SeedItem(
        source="43-outerwear-blazer-black.jpg",
        public_id="bijoux/01821186-a63e-4b4b-8fef-7a83d6377056/vjtvici68fdibbnvtvih",
        tags={
            "category": "outerwear",
            "subcategory": "blazer",
            "fit": "oversized",
            "length": "regular",
            "rise": None,
            "color_primary": "black",
            "color_secondary": None,
            "pattern": "solid",
            "material": "synthetic",
            "formality": 4,
            "warmth": 3,
            "layer": "mid",
            "water_resistant": False,
            "display_name": "black double-breasted blazer",
        },
    ),
    SeedItem(
        source="44-outerwear-coat-grey-wool.jpg",
        public_id="bijoux/01821186-a63e-4b4b-8fef-7a83d6377056/zxsrh6cfnsjj3mrs2ro2",
        tags={
            "category": "outerwear",
            "subcategory": "coat",
            "fit": "straight",
            "length": "longline",
            "rise": None,
            "color_primary": "grey",
            "color_secondary": None,
            "pattern": "solid",
            "material": "wool",
            "formality": 4,
            "warmth": 5,
            "layer": "outer",
            "water_resistant": False,
            "display_name": "grey wool longline coat",
        },
    ),
    SeedItem(
        source="45-outerwear-jacket-black-shearling.jpg",
        public_id="bijoux/01821186-a63e-4b4b-8fef-7a83d6377056/wa24luorg2mnozipgmsx",
        tags={
            "category": "outerwear",
            "subcategory": "jacket",
            "fit": "relaxed",
            "length": "crop",
            "rise": None,
            "color_primary": "black",
            "color_secondary": None,
            "pattern": "solid",
            "material": "leather",
            "formality": 3,
            "warmth": 5,
            "layer": "outer",
            "water_resistant": False,
            "display_name": "black shearling aviator jacket",
        },
    ),
    SeedItem(
        source="46-outerwear-jacket-brown-shearling.jpg",
        public_id="bijoux/01821186-a63e-4b4b-8fef-7a83d6377056/dsy0pq9vr96hrcgdmk4r",
        tags={
            "category": "outerwear",
            "subcategory": "jacket",
            "fit": "relaxed",
            "length": "crop",
            "rise": None,
            "color_primary": "brown",
            "color_secondary": None,
            "pattern": "solid",
            "material": "leather",
            "formality": 3,
            "warmth": 5,
            "layer": "outer",
            "water_resistant": False,
            "display_name": "brown suede shearling jacket",
        },
    ),
    SeedItem(
        source="47-shoes-boots-black-knee.jpg",
        public_id="bijoux/01821186-a63e-4b4b-8fef-7a83d6377056/xoug1jyznvz6o5wym0xd",
        tags={
            "category": "shoes",
            "subcategory": "boots",
            "fit": None,
            "length": "full",
            "rise": None,
            "color_primary": "black",
            "color_secondary": None,
            "pattern": "solid",
            "material": "leather",
            "formality": 3,
            "warmth": 4,
            "layer": "standalone",
            "water_resistant": False,
            "display_name": "black knee-high harness boots",
        },
    ),
    SeedItem(
        source="48-shoes-boots-black-ankle.jpg",
        public_id="bijoux/01821186-a63e-4b4b-8fef-7a83d6377056/gqykyzszudntrkzu41h0",
        tags={
            "category": "shoes",
            "subcategory": "boots",
            "fit": None,
            "length": "ankle",
            "rise": None,
            "color_primary": "black",
            "color_secondary": None,
            "pattern": "solid",
            "material": "leather",
            "formality": 3,
            "warmth": 4,
            "layer": "standalone",
            "water_resistant": False,
            "display_name": "black suede ankle boots",
        },
    ),
    SeedItem(
        source="49-shoes-heels-beige-crystal.jpg",
        public_id="bijoux/01821186-a63e-4b4b-8fef-7a83d6377056/hq1iv6j5kgtycx5ppot9",
        tags={
            "category": "shoes",
            "subcategory": "heels",
            "fit": None,
            "length": None,
            "rise": None,
            "color_primary": "beige",
            "color_secondary": None,
            "pattern": "solid",
            "material": "synthetic",
            "formality": 5,
            "warmth": 1,
            "layer": "standalone",
            "water_resistant": False,
            "display_name": "nude crystal stiletto sandals",
        },
    ),
    SeedItem(
        source="50-shoes-heels-white-crystal.jpg",
        public_id="bijoux/01821186-a63e-4b4b-8fef-7a83d6377056/rleiaupp6usliipnehkg",
        tags={
            "category": "shoes",
            "subcategory": "heels",
            "fit": None,
            "length": None,
            "rise": None,
            "color_primary": "white",
            "color_secondary": None,
            "pattern": "solid",
            "material": "synthetic",
            "formality": 4,
            "warmth": 1,
            "layer": "standalone",
            "water_resistant": False,
            "display_name": "cream crystal block heels",
        },
    ),
    SeedItem(
        source="51-shoes-sandals-brown-slide.jpg",
        public_id="bijoux/01821186-a63e-4b4b-8fef-7a83d6377056/yeyxid5pfvmvhztxbtpg",
        tags={
            "category": "shoes",
            "subcategory": "sandals",
            "fit": None,
            "length": None,
            "rise": None,
            "color_primary": "brown",
            "color_secondary": "beige",
            "pattern": "solid",
            "material": "leather",
            "formality": 2,
            "warmth": 1,
            "layer": "standalone",
            "water_resistant": False,
            "display_name": "brown disc slide sandals",
        },
    ),
    SeedItem(
        source="52-shoes-sandals-black-studded.jpg",
        public_id="bijoux/01821186-a63e-4b4b-8fef-7a83d6377056/szcf4nydxjhkslzcvrk5",
        tags={
            "category": "shoes",
            "subcategory": "sandals",
            "fit": None,
            "length": None,
            "rise": None,
            "color_primary": "black",
            "color_secondary": "gold",
            "pattern": "solid",
            "material": "leather",
            "formality": 2,
            "warmth": 1,
            "layer": "standalone",
            "water_resistant": False,
            "display_name": "black gold-studded slides",
        },
    ),
    SeedItem(
        source="53-shoes-sandals-white-slide.jpg",
        public_id="bijoux/01821186-a63e-4b4b-8fef-7a83d6377056/naasflkdpuhorgz8hu3d",
        tags={
            "category": "shoes",
            "subcategory": "sandals",
            "fit": None,
            "length": None,
            "rise": None,
            "color_primary": "white",
            "color_secondary": "brown",
            "pattern": "solid",
            "material": "leather",
            "formality": 2,
            "warmth": 1,
            "layer": "standalone",
            "water_resistant": False,
            "display_name": "cream toe-post slides",
        },
    ),
    SeedItem(
        source="54-shoes-sneakers-white-mesh.jpg",
        public_id="bijoux/01821186-a63e-4b4b-8fef-7a83d6377056/y0t9v9peg6q12t5h8uly",
        tags={
            "category": "shoes",
            "subcategory": "sneakers",
            "fit": None,
            "length": None,
            "rise": None,
            "color_primary": "white",
            "color_secondary": "grey",
            "pattern": "solid",
            "material": "synthetic",
            "formality": 2,
            "warmth": 2,
            "layer": "standalone",
            "water_resistant": False,
            "display_name": "white mesh running sneakers",
        },
    ),
    SeedItem(
        source="55-shoes-sneakers-white-platform.jpg",
        public_id="bijoux/01821186-a63e-4b4b-8fef-7a83d6377056/e8hjt7cliy2zozlug2pf",
        tags={
            "category": "shoes",
            "subcategory": "sneakers",
            "fit": None,
            "length": None,
            "rise": None,
            "color_primary": "white",
            "color_secondary": None,
            "pattern": "solid",
            "material": "synthetic",
            "formality": 2,
            "warmth": 2,
            "layer": "standalone",
            "water_resistant": False,
            "display_name": "white platform sneakers",
        },
    ),
    SeedItem(
        source="56-bag-crossbody-beige-python-strap.jpg",
        public_id="bijoux/01821186-a63e-4b4b-8fef-7a83d6377056/z0n9ciz4oof83enltrws",
        tags={
            "category": "bag",
            "subcategory": "crossbody",
            "fit": None,
            "length": None,
            "rise": None,
            "color_primary": "beige",
            "color_secondary": "brown",
            "pattern": "solid",
            "material": "leather",
            "formality": 3,
            "warmth": 1,
            "layer": "standalone",
            "water_resistant": False,
            "display_name": "cream fold-over crossbody",
        },
    ),
    SeedItem(
        source="57-bag-crossbody-black-camera.jpg",
        public_id="bijoux/01821186-a63e-4b4b-8fef-7a83d6377056/yjn0sosqwaeoicfyfo3t",
        tags={
            "category": "bag",
            "subcategory": "crossbody",
            "fit": None,
            "length": None,
            "rise": None,
            "color_primary": "black",
            "color_secondary": None,
            "pattern": "solid",
            "material": "leather",
            "formality": 2,
            "warmth": 1,
            "layer": "standalone",
            "water_resistant": False,
            "display_name": "black snake-embossed camera bag",
        },
    ),
    SeedItem(
        source="58-bag-shoulder-black-patent.jpg",
        public_id="bijoux/01821186-a63e-4b4b-8fef-7a83d6377056/kac7qd9rokdv1t59yxfr",
        tags={
            "category": "bag",
            "subcategory": "shoulder",
            "fit": None,
            "length": None,
            "rise": None,
            "color_primary": "black",
            "color_secondary": "silver",
            "pattern": "solid",
            "material": "leather",
            "formality": 4,
            "warmth": 1,
            "layer": "standalone",
            "water_resistant": False,
            "display_name": "black patent chain shoulder bag",
        },
    ),
    SeedItem(
        source="59-bag-shoulder-grey-suede.jpg",
        public_id="bijoux/01821186-a63e-4b4b-8fef-7a83d6377056/cb9s0eouoxnzuukzd0rb",
        tags={
            "category": "bag",
            "subcategory": "shoulder",
            "fit": None,
            "length": None,
            "rise": None,
            "color_primary": "grey",
            "color_secondary": None,
            "pattern": "solid",
            "material": "leather",
            "formality": 4,
            "warmth": 1,
            "layer": "standalone",
            "water_resistant": False,
            "display_name": "grey suede chain shoulder bag",
        },
    ),
    SeedItem(
        source="60-bag-shoulder-orange.jpg",
        public_id="bijoux/01821186-a63e-4b4b-8fef-7a83d6377056/rvhbt4s1pikpru7w63sw",
        tags={
            "category": "bag",
            "subcategory": "shoulder",
            "fit": None,
            "length": None,
            "rise": None,
            "color_primary": "orange",
            "color_secondary": None,
            "pattern": "solid",
            "material": "leather",
            "formality": 4,
            "warmth": 1,
            "layer": "standalone",
            "water_resistant": False,
            "display_name": "orange chain shoulder bag",
        },
    ),
    SeedItem(
        source="61-bag-shoulder-grey-denim.jpg",
        public_id="bijoux/01821186-a63e-4b4b-8fef-7a83d6377056/aqksvcwmmxsqlprw8eg6",
        tags={
            "category": "bag",
            "subcategory": "shoulder",
            "fit": None,
            "length": None,
            "rise": None,
            "color_primary": "grey",
            "color_secondary": None,
            "pattern": "denim_wash",
            "material": "denim",
            "formality": 2,
            "warmth": 1,
            "layer": "standalone",
            "water_resistant": False,
            "display_name": "grey denim baguette bag",
        },
    ),
    SeedItem(
        source="62-accessory-belt-black-gold-buckle.jpg",
        public_id="bijoux/01821186-a63e-4b4b-8fef-7a83d6377056/vsluxxnaecvnlnbbgwds",
        tags={
            "category": "accessory",
            "subcategory": "belt",
            "fit": None,
            "length": None,
            "rise": None,
            "color_primary": "black",
            "color_secondary": "gold",
            "pattern": "solid",
            "material": "leather",
            "formality": 3,
            "warmth": 1,
            "layer": "standalone",
            "water_resistant": False,
            "display_name": "black belt with gold buckle",
        },
    ),
    SeedItem(
        source="63-accessory-jewelry-gold-shell.jpg",
        public_id="bijoux/01821186-a63e-4b4b-8fef-7a83d6377056/bq4ky9lgkpulsqt2saew",
        tags={
            "category": "accessory",
            "subcategory": "jewelry",
            "fit": None,
            "length": None,
            "rise": None,
            "color_primary": "gold",
            "color_secondary": "green",
            "pattern": "solid",
            "material": "other",
            "formality": 2,
            "warmth": 1,
            "layer": "standalone",
            "water_resistant": False,
            "display_name": "gold shell charm necklace",
        },
    ),
    SeedItem(
        source="64-accessory-jewelry-silver-crystal.jpg",
        public_id="bijoux/01821186-a63e-4b4b-8fef-7a83d6377056/ddxl3l6nsslvxo7gnvqz",
        tags={
            "category": "accessory",
            "subcategory": "jewelry",
            "fit": None,
            "length": None,
            "rise": None,
            "color_primary": "silver",
            "color_secondary": None,
            "pattern": "solid",
            "material": "other",
            "formality": 5,
            "warmth": 1,
            "layer": "standalone",
            "water_resistant": False,
            "display_name": "silver crystal tennis necklace",
        },
    ),
)


# Two rows that no `ready` row can stand in for, and they are not the same
# shape as each other. The first is what an item looks like when tagging never
# produced anything: the failed tile, its retry button, and the "Add manually"
# entrance 1.9 built the promotion rule for. The second is `02-DATA-MODEL.md`'s
# failed row that *carries* tags — a retag that failed over a good row — which
# nothing in this database has ever had, and which is the only row that can
# demonstrate 1.8's rule that a null is never hidden by that field's filter,
# because `REQUIRED_TAG_FIELDS` forbids a null there on anything `ready`.
# `DECISIONS.md` 135.
FAILURE_ITEMS: tuple[SeedItem, ...] = (
    SeedItem(
        source="07-top-sweater-white-waffle.jpg",
        public_id="bijoux/01821186-a63e-4b4b-8fef-7a83d6377056/qx8lmarosh5p36imoa1r",
        status=ItemStatus.FAILED,
        error_message="No usable answer arrived: APITimeoutError",
    ),
    SeedItem(
        source="34-bottom-trousers-black-crinkle.jpg",
        public_id="bijoux/01821186-a63e-4b4b-8fef-7a83d6377056/wwk9r0po8hpfa4qyssw5",
        tags={
            "category": "bottom",
            "subcategory": "trousers",
            "fit": "wide",
            "length": "full",
            "rise": "high",
            "color_primary": "black",
            "color_secondary": None,
            "pattern": "solid",
            "material": "other",
            "formality": None,
            "warmth": None,
            "layer": "base",
            "water_resistant": False,
            "display_name": "black crinkle wide-leg trousers",
        },
        status=ItemStatus.FAILED,
        error_message=(
            "The tags could not be accepted: layer 'outer' is not valid "
            "for category 'top', which takes base or mid"
        ),
    ),
)


class _TestDatabaseUrl(BaseSettings):
    """Deliberately not a field on `Settings`. `DECISIONS.md` 073 keeps
    `TEST_DATABASE_URL` off it because no application code reads it and it must
    never be set on Render; this script is not application code and needs to
    compare against it, so it reads the same `.env` the way `conftest.py` does."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    TEST_DATABASE_URL: str = ""


def _problems(item: SeedItem) -> list[str]:
    """Every reason this row may not be inserted. Never raises: the caller
    reports all of them at once, because fixing a hand-written table one
    aborted run at a time is the slow way to do it."""
    found: list[str] = []
    report = validate_tag_dict(item.tags)

    found.extend(f"{issue.field}: {issue.reason}" for issue in report.errors)
    # A coercion is an error here and is not one in `vision.py`. There the
    # source is a model and throwing away fourteen good tags over one word is
    # the worse answer; here the source is this file and the fix is to correct
    # the word. `DECISIONS.md` 089 drew the line, 130 puts this side of it.
    found.extend(
        f"{issue.field}: {issue.reason} (coerced, which this table may not do)"
        for issue in report.coerced
    )

    if item.status == ItemStatus.READY:
        missing = [name for name in REQUIRED_TAG_FIELDS if item.tags.get(name) is None]
        if missing:
            found.append(f"ready row is missing {', '.join(missing)}")
        if item.error_message is not None:
            found.append("ready row carries an error_message")
    elif item.status == ItemStatus.FAILED and not item.error_message:
        found.append("failed row carries no error_message")

    if item.status == ItemStatus.PROCESSING:
        # The startup sweep fails any `processing` row older than ten minutes
        # and writes its own `error_message`, so a seeded one changes on its own
        # between the seed and the demo. `DECISIONS.md` 135.
        found.append("processing is never seeded")

    return found


def _validated(items: tuple[SeedItem, ...]) -> None:
    """Abort before the first insert if any row is unfit. Raises `SystemExit`,
    which is what turns this into a non-zero exit rather than a traceback."""
    failures = {item.source: _problems(item) for item in items}
    failures = {source: problems for source, problems in failures.items() if problems}
    if not failures:
        return
    for source, problems in failures.items():
        for problem in problems:
            logger.error(
                "Seed row rejected — %s: %s",
                source,
                problem,
                extra={"source": source, "problem": problem},
            )
    raise SystemExit(f"{len(failures)} seed row(s) rejected; nothing was written.")


def _guarded_url() -> str:
    """The database this run will touch, or a refusal.

    `conftest.py` refuses to run the suite against `DATABASE_URL`; this is the
    same guard from the other side. Seeding the test database would leave rows
    the suite's own leak assertion is written to notice."""
    url = settings.DATABASE_URL
    test_url = _TestDatabaseUrl().TEST_DATABASE_URL
    if test_url and url == test_url:
        raise SystemExit(
            "refusing: DATABASE_URL is TEST_DATABASE_URL. The suite owns that "
            "database and asserts it is left as it was found."
        )
    return url


def _describe(db: Session, url: str) -> None:
    """What this run is pointed at, in the *message* rather than in `extra`.

    Found by running it: `configure_logging` installs a human formatter outside
    production whose format string is `%(message)s`, so anything passed as
    `extra` is dropped. A guard that exists to show the operator which database
    is about to be written to printed the words "Target database" and nothing
    else. The values stay in `extra` as well, because the JSON formatter reads
    them and a deployed run is the case that wants them structured."""
    parsed = make_url(url)
    users = db.scalar(select(func.count()).select_from(User)) or 0
    items = db.scalar(select(func.count()).select_from(Item)) or 0
    logger.info(
        "Target database %s/%s — %d user(s), %d item(s) before this run",
        parsed.host,
        parsed.database,
        users,
        items,
        extra={"host": parsed.host, "database": parsed.database, "users": users, "items": items},
    )


def _demo_user(db: Session) -> User | None:
    return db.scalar(select(User).where(User.email == DEMO_EMAIL))


def _reset(db: Session) -> int:
    """Delete the demo user and, through the database's own cascade, its items.

    Scoped to one row by email. `fk_items_user_id_users` carries
    `ON DELETE CASCADE` in migration `0001`, and no `relationship()` is declared
    between the two models, so nothing in the ORM tries to null the children
    first. The committed `public_id`s are reused on the next seed, so a reset
    orphans no Cloudinary asset."""
    user = _demo_user(db)
    if user is None:
        return 0
    count = db.scalar(select(func.count()).select_from(Item).where(Item.user_id == user.id)) or 0
    db.delete(user)
    db.commit()
    return count


def _insert(db: Session, items: tuple[SeedItem, ...]) -> None:
    seeded_at = datetime.now(UTC).isoformat(timespec="seconds")
    db.add(
        User(
            id=DEMO_USER_ID,
            email=DEMO_EMAIL,
            password_hash=hash_password(DEMO_PASSWORD),
            display_name=DEMO_DISPLAY_NAME,
        )
    )
    # Found by running it. No `relationship()` is declared between the two
    # models — `02-DATA-MODEL.md` never asks for one and nothing else needs it —
    # so the unit of work has no dependency edge to order these inserts by, and
    # it batched the items first and hit `fk_items_user_id_users`. The flush is
    # the ordering; it is not a second transaction, so a bad row still rolls the
    # user back with it. `DECISIONS.md` 133.
    db.flush()

    for item in items:
        db.add(
            Item(
                user_id=DEMO_USER_ID,
                short_id=generate_short_id(),
                image_public_id=item.public_id,
                status=item.status,
                error_message=item.error_message,
                # A second guest key beside `tagging`, on the terms
                # `02-DATA-MODEL.md` already sets for that column. It survives a
                # `PATCH`, which never touches `attributes`, and a retag, which
                # merges rather than replaces — so a retagged seed row carries
                # both keys, and that is correct: this one says where the row
                # came from, not where its current tags came from.
                # `DECISIONS.md` 134.
                attributes={
                    "seed": {
                        "script": "seed_demo",
                        "version": SEED_VERSION,
                        "seeded_at": seeded_at,
                        "source": item.source,
                    }
                },
                **item.tags,
            )
        )
    db.commit()


def _seed(db: Session, items: tuple[SeedItem, ...]) -> None:
    for attempt in range(SHORT_ID_ATTEMPTS):
        try:
            _insert(db, items)
            return
        except IntegrityError as exc:
            db.rollback()
            if attempt == SHORT_ID_ATTEMPTS - 1 or "uq_items_short_id" not in str(exc.orig):
                raise
            logger.warning(
                "short_id collision on attempt %d, regenerating the batch",
                attempt,
                extra={"attempt": attempt},
            )


def _uploaded(directory: Path) -> list[tuple[str, str]]:
    """Every file validated before any file is sent.

    `04-API-SPEC.md` makes the upload route reject a whole batch on one bad
    file for this reason: validating as it goes would leave the assets of a
    failed run orphaned in Cloudinary with no row to find them by."""
    paths = sorted(p for p in directory.iterdir() if p.is_file() and not p.name.startswith("."))
    if not paths:
        raise SystemExit(f"no files in {directory}")

    blobs: list[tuple[str, bytes]] = []
    for path in paths:
        data = path.read_bytes()
        validate_image(data)
        blobs.append((path.name, data))

    uploaded: list[tuple[str, str]] = []
    for name, data in blobs:
        uploaded.append((name, upload_image(data, DEMO_USER_ID)))
        logger.info("Uploaded %s", name, extra={"source": name})
    return uploaded


def _table(uploaded: list[tuple[str, str]]) -> str:
    rows = "\n".join(
        f'    SeedItem(source="{name}", public_id="{public_id}", tags={{}}),'
        for name, public_id in uploaded
    )
    return f"SEED_ITEMS: tuple[SeedItem, ...] = (\n{rows}\n)"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.seed_demo",
        description="Seed, reset or photograph the demo wardrobe.",
    )
    parser.add_argument("--yes", action="store_true", help="required before anything is written")
    parser.add_argument("--reset", action="store_true", help="delete demo@bijoux.app and its items")
    parser.add_argument(
        "--with-failures",
        action="store_true",
        help="also seed the two failed rows the ready ones cannot stand in for",
    )
    parser.add_argument(
        "--upload",
        metavar="DIR",
        type=Path,
        help="upload a folder to Cloudinary and log the table; writes no rows",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    # `configure_logging` sets the root logger to DEBUG outside production, and
    # SQLAlchemy emits every statement once its logger is enabled at INFO. That
    # is the right default for a request log and the wrong one for a command
    # whose output is a table to paste.
    logging.getLogger("sqlalchemy").setLevel(logging.WARNING)

    args = _parser().parse_args(argv)

    if args.upload is not None:
        if args.reset or args.with_failures:
            raise SystemExit("--upload writes no rows; use it on its own.")
        logger.info("Paste this into scripts/seed_demo.py:\n%s", _table(_uploaded(args.upload)))
        return 0

    items = SEED_ITEMS + (FAILURE_ITEMS if args.with_failures else ())
    _validated(items)

    url = _guarded_url()
    db = SessionLocal()
    try:
        _describe(db, url)
        if not args.yes:
            raise SystemExit("refusing: pass --yes once the target above is the one you meant.")

        existing = _demo_user(db)
        if existing is not None and not args.reset:
            count = (
                db.scalar(select(func.count()).select_from(Item).where(Item.user_id == existing.id))
                or 0
            )
            raise SystemExit(
                f"refusing: {DEMO_EMAIL} already exists as {existing.id} with {count} item(s). "
                "Pass --reset to replace it."
            )

        if args.reset:
            deleted = _reset(db)
            logger.info(
                "Reset the demo wardrobe, %d item(s) deleted",
                deleted,
                extra={"items_deleted": deleted},
            )

        _seed(db, items)
        ready = sum(1 for item in items if item.status == ItemStatus.READY)
        failed = sum(1 for item in items if item.status == ItemStatus.FAILED)
        logger.info(
            "Seeded %s with %d item(s): %d ready, %d failed",
            DEMO_EMAIL,
            len(items),
            ready,
            failed,
            extra={
                "user_id": str(DEMO_USER_ID),
                "items": len(items),
                "ready": ready,
                "failed": failed,
            },
        )
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
