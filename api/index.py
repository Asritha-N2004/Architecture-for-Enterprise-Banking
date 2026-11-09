"""Vercel ASGI entrypoint. Uses external PostgreSQL, never an ephemeral SQLite DB."""
import sys
from pathlib import Path
from contextlib import asynccontextmanager
import anyio

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))

from app.main import app
from app.database import engine
from sqlalchemy import text
from alembic import command
from alembic.config import Config


def migrate_database():
    if engine.dialect.name != 'postgresql':
        raise RuntimeError('Vercel deployment requires persistent PostgreSQL')
    config = Config(str(ROOT / 'backend/alembic.ini'))
    config.set_main_option('script_location', str(ROOT / 'backend/alembic'))
    config.set_main_option('prepend_sys_path', str(ROOT / 'backend'))
    # Serialize cold-start migrations across function instances. This does not seed users.
    # Transaction-scoped locks work with Neon's transaction-pooled connection URL.
    # Alembic must reuse this connection so the lock covers the actual DDL.
    with engine.begin() as connection:
        connection.execute(text('SELECT pg_advisory_xact_lock(721590231)'))
        config.attributes['connection'] = connection
        command.upgrade(config, 'head')


@asynccontextmanager
async def lifespan(application):
    await anyio.to_thread.run_sync(migrate_database)
    yield


app.router.lifespan_context = lifespan
