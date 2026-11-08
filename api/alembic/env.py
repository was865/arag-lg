from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context
from arag.db.engine import sqlalchemy_url
from arag.db.models import SCHEMA, Base
from arag.settings import Settings

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config
# スキーマ app を Python 側が所有する（specs/000-overview/data-model.md）。
# psycopg 3 ドライバを明示する。
config.set_main_option(
    "sqlalchemy.url",
    sqlalchemy_url(Settings().database_url),
)

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def _include_name(name: str | None, type_: str, parent_names: object) -> bool:
    # auth（Better Auth）と lg（LangGraph）は他者の所有なので比較対象から外す
    if type_ == "schema":
        return name == SCHEMA
    return True


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
        include_schemas=True,
        include_name=_include_name,
        version_table_schema=SCHEMA,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        connection.exec_driver_sql(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
        connection.commit()
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_schemas=True,
            include_name=_include_name,
            version_table_schema=SCHEMA,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
