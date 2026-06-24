import os
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./faide_trader.db")

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with async_session() as session:
        yield session


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Add new columns to existing tables if they don't exist (no Alembic)
    async with engine.begin() as conn:
        await conn.run_sync(_migrate_columns)


def _migrate_columns(conn):
    """Add columns that may be missing from older DB schemas."""
    import sqlalchemy as sa

    migrations = [
        ("accounts", "is_pinned", "BOOLEAN DEFAULT 0"),
        ("accounts", "pinned_stats", "VARCHAR DEFAULT '[]'"),
        ("bots", "is_pinned", "BOOLEAN DEFAULT 0"),
        ("bots", "pinned_stats", "VARCHAR DEFAULT '[]'"),
        ("portfolios", "pinned_stats", "VARCHAR DEFAULT '[]'"),
    ]
    for table, column, col_type in migrations:
        try:
            conn.execute(sa.text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"))
        except Exception:
            pass  # Column already exists
