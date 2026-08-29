from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

engine = create_async_engine(str(settings.database_url), echo=False)


@event.listens_for(engine.sync_engine, "connect")
def _enforce_foreign_keys(dbapi_connection, _record) -> None:
    """SQLite ignores ON DELETE CASCADE unless this is set, per connection.

    Without it, deleting an item left its playlist_items rows behind pointing at
    a row that no longer existed, and the playlist endpoint then 500'd on a null
    video — the playlist just said "Loading…" forever.
    """
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
