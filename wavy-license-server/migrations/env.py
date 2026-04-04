"""Alembic environment — reads DATABASE_URL from config so migrations
use the same database as the application."""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Import the app's metadata and settings
from config import settings
from models import Base

# Alembic Config object (gives access to alembic.ini values)
config = context.config

# Override sqlalchemy.url with the value from the app's config
# Escape % for configparser interpolation (e.g. URL-encoded passwords like %21)
config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))

# Set up Python logging from alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# MetaData for autogenerate support
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run in 'offline' mode — no DB connection, generates SQL script."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run in 'online' mode — connects to the database directly."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
