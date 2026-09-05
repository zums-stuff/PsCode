from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context
from pseint_api import (
    config,
    models,  # noqa: F401  (registers all tables on Base.metadata)
)
from pseint_api.db import Base

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config_ = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config_.config_file_name is not None:
    fileConfig(config_.config_file_name)

# URL always comes from config.database_url() (env DATABASE_URL with a
# sensible local default) — never commit credentials in alembic.ini.
config_.set_main_option("sqlalchemy.url", config.database_url())

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config_.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = engine_from_config(
        config_.get_section(config_.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
