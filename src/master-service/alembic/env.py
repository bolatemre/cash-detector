import logging
from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# Import Base and models
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from database.connection import Base
from models.camera import Camera  # Import all models
from config.settings import settings

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Override the sqlalchemy.url from environment variable
if config.config_file_name is not None:
    # Use the DATABASE_URL from environment/settings
    config.set_main_option('sqlalchemy.url', settings.database_url)

# Interpret the config file for Python logging.
# This line sets up loggers basically.
# Skip fileConfig if logging is already configured (to avoid conflicts)
if config.config_file_name is not None and not logging.getLogger().hasHandlers():
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
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
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    # Configure engine with NullPool to avoid connection pooling issues
    configuration = config.get_section(config.config_ini_section, {})
    configuration["poolclass"] = pool.NullPool
    # Add connection timeout to prevent hanging
    configuration["connect_args"] = {"connect_timeout": 10}
    
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
    )

    try:
        with connectable.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                compare_type=True,
            )

            with context.begin_transaction():
                context.run_migrations()
    finally:
        # Always dispose the engine to close connections
        connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

