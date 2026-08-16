from logging.config import fileConfig

import sqlalchemy as sa
from sqlalchemy import pool

# Imported for the side effect: each model registers itself on Base.metadata,
# and target_metadata is empty without it.
import app.models  # noqa: F401
from alembic import context
from app.core.config import settings
from app.db.base import Base

config = context.config

# fileConfig defaults to disable_existing_loggers=True, and conftest.py runs
# `command.upgrade` in-process, so the first test that touches the database
# would otherwise set disabled=True on every logger that already exists and is
# not named in alembic.ini — app.main, app.api.v1.routes.items,
# app.services.storage. Nothing noticed because no test had asserted a log
# line. This file configures logging for the CLI; in-process it is
# reconfiguring somebody else's process, so the caller gets to decline.
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=settings.DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # One short-lived process per migration run: a pool is overhead, and it
    # leaves Neon holding sockets after the CLI has already exited.
    connectable = sa.create_engine(settings.DATABASE_URL, poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
