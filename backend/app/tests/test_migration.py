"""The boot-time migration list is applied on every start and swallows its own
exceptions, so the only thing standing between a typo and a silently missing
column is this test."""

import sqlite3

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.database import Base
from app.main import MIGRATIONS

EXPECTED_COLUMNS = {
    "codec",
    "audio_only",
    "kind",
    "handler",
    "file_path",
    "mime_type",
    "file_name",
    "source_domain",
    "byline",
    "published_at",
    "word_count",
    "excerpt",
    "article_html_path",
    "raw_html_path",
    "capture_source",
    "capture_url",
    "paywalled",
    "extra",
}


async def _apply(db_path, times: int = 1) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        for _ in range(times):
            async with engine.begin() as conn:
                for stmt in MIGRATIONS:
                    try:
                        await conn.execute(text(stmt))
                    except Exception:
                        pass
    finally:
        await engine.dispose()


def _columns(db_path) -> list[str]:
    con = sqlite3.connect(db_path)
    try:
        return [row[1] for row in con.execute("PRAGMA table_info(videos)")]
    finally:
        con.close()


async def test_migrations_are_idempotent(tmp_path):
    db = tmp_path / "hamstr.db"
    await _apply(db, times=3)

    cols = _columns(db)
    assert len(cols) == len(set(cols)), "a column was added more than once"
    assert EXPECTED_COLUMNS <= set(cols)


async def test_migrations_apply_to_a_legacy_table(tmp_path):
    """Simulate a pre-existing DB that predates every archive column."""
    db = tmp_path / "legacy.db"
    con = sqlite3.connect(db)
    con.execute(
        "CREATE TABLE videos ("
        "id TEXT PRIMARY KEY, url TEXT NOT NULL, title TEXT, channel TEXT,"
        "duration_seconds INTEGER, file_size_bytes INTEGER, thumbnail_path TEXT,"
        "video_path TEXT, audio_mp3_path TEXT, audio_ogg_path TEXT,"
        "status TEXT NOT NULL, progress REAL NOT NULL, error_message TEXT,"
        "created_at TIMESTAMP NOT NULL, updated_at TIMESTAMP NOT NULL)"
    )
    con.commit()
    con.close()

    await _apply(db, times=2)
    assert EXPECTED_COLUMNS <= set(_columns(db))


async def test_audio_only_backfill_is_idempotent(tmp_path):
    db = tmp_path / "backfill.db"
    await _apply(db, times=1)

    con = sqlite3.connect(db)
    con.execute(
        "INSERT INTO videos (id, url, status, progress, audio_only, kind,"
        " created_at, updated_at) VALUES"
        " ('a', 'https://x/1', 'completed', 100, 1, 'video', '2024-01-01', '2024-01-01'),"
        " ('v', 'https://x/2', 'completed', 100, 0, 'video', '2024-01-01', '2024-01-01')"
    )
    con.commit()
    con.close()

    await _apply(db, times=2)

    con = sqlite3.connect(db)
    kinds = dict(con.execute("SELECT id, kind FROM videos"))
    con.close()
    assert kinds == {"a": "audio", "v": "video"}
