from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    # Pinned so the names SQLAlchemy would generate match the ones migration
    # 0001 spells out as literals. It has no runtime effect: the live schema is
    # built by the migration, so the name PostgreSQL reports in an IntegrityError
    # — which is what register (040) and upload (052) match on — comes from
    # there and not from here. What this buys is that the model and the database
    # do not describe the same constraint under two different names.
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(table_name)s_%(column_0_N_name)s",
            "uq": "uq_%(table_name)s_%(column_0_N_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )
