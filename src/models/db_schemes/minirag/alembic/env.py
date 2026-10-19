import os
from logging.config import fileConfig
from alembic import context
from sqlalchemy import engine_from_config, pool

from schemes import SQLAlchemyBase

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = SQLAlchemyBase.metadata


def get_database_url() -> str:
    url = os.getenv("ALEMBIC_DATABASE_URL")

    if not url:
        url = config.get_main_option("sqlalchemy.url")

    if not url:
        raise RuntimeError(
            "Database URL is missing. Set ALEMBIC_DATABASE_URL "
            "or sqlalchemy.url in alembic.ini."
        )

    return url


def run_migrations_offline() -> None:
    context.configure(
        url=get_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(
        config.config_ini_section
    ).copy()

    configuration["sqlalchemy.url"] = get_database_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()

    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
