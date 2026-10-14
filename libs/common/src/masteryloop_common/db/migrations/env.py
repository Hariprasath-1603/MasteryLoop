import asyncio
import sys
from logging.config import fileConfig
from pathlib import Path

# Ensure repository packages are resolvable regardless of invocation directory
_current_file = Path(__file__).resolve()
_common_src = _current_file.parents[3]  # .../libs/common/src
_repo_root = (
    _current_file.parents[6]
    if len(_current_file.parents) > 6
    else _common_src.parent.parent
)
_ml_src = _repo_root / "ml" / "src"

for _p in [_common_src, _ml_src, _repo_root]:
    _p_str = str(_p)
    if _p_str not in sys.path and _p.is_dir():
        sys.path.insert(0, _p_str)

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

try:
    import masteryloop_common.db.models as _models
    from masteryloop_common.config import get_settings
    from masteryloop_common.db.base import Base
except ImportError:
    # Relative fallback when loaded within package context
    from ...config import get_settings  # type: ignore[no-redef]
    from .. import models as _models  # type: ignore[no-redef]  # noqa: F401
    from ..base import Base  # type: ignore[no-redef]

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata
settings = get_settings()


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = settings.sync_database_url
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in 'online' mode with async engine."""
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = settings.async_database_url

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
