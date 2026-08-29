import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, text

from app.config import settings
from app.database import Base, engine, AsyncSessionLocal
from app.models import video as _models  # noqa: F401 — registers ORM models
from app.models.video import Video
from app.routers import videos, stream, ws, tags, playlists, cookies
from app.services.downloader import download_worker
from app.services.cookies import cookies_dir
from app.services.paths import STORAGE_SUBDIRS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Poor-man's migrations, applied at every boot. SQLite ADD COLUMN requires a
# constant default and cannot add UNIQUE/PRIMARY KEY, so every statement below
# is either nullable or has a literal default.
MIGRATIONS: list[str] = [
    "ALTER TABLE videos ADD COLUMN codec TEXT",
    "ALTER TABLE videos ADD COLUMN audio_only INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE videos ADD COLUMN kind TEXT NOT NULL DEFAULT 'video'",
    "ALTER TABLE videos ADD COLUMN handler TEXT NOT NULL DEFAULT 'ytdlp'",
    "ALTER TABLE videos ADD COLUMN file_path TEXT",
    "ALTER TABLE videos ADD COLUMN mime_type TEXT",
    "ALTER TABLE videos ADD COLUMN file_name TEXT",
    "ALTER TABLE videos ADD COLUMN source_domain TEXT",
    "ALTER TABLE videos ADD COLUMN byline TEXT",
    "ALTER TABLE videos ADD COLUMN published_at TEXT",
    "ALTER TABLE videos ADD COLUMN word_count INTEGER",
    "ALTER TABLE videos ADD COLUMN excerpt TEXT",
    "ALTER TABLE videos ADD COLUMN article_html_path TEXT",
    "ALTER TABLE videos ADD COLUMN raw_html_path TEXT",
    "ALTER TABLE videos ADD COLUMN capture_source TEXT",
    "ALTER TABLE videos ADD COLUMN capture_url TEXT",
    "ALTER TABLE videos ADD COLUMN paywalled INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE videos ADD COLUMN extra TEXT",
    # Backfill rows that predate `kind`. Idempotent: after the first pass those
    # rows already read 'audio'.
    "UPDATE videos SET kind = 'audio' WHERE audio_only = 1 AND kind = 'video'",
    "CREATE INDEX IF NOT EXISTS ix_videos_kind ON videos (kind)",
    # Rows orphaned before SQLite FK enforcement was switched on (see
    # database.py): their item is long gone, but they still counted towards a
    # playlist's size and made the playlist endpoint fail to serialize.
    "DELETE FROM playlist_items WHERE video_id NOT IN (SELECT id FROM videos)",
    "DELETE FROM tags WHERE video_id NOT IN (SELECT id FROM videos)",
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create DB tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Add columns to existing DBs that predate these fields. Each statement is
        # idempotent-by-exception: re-running raises "duplicate column name", which
        # we swallow. Logged at DEBUG so a genuinely broken statement is findable.
        for stmt in MIGRATIONS:
            try:
                await conn.execute(text(stmt))
            except Exception as exc:
                logger.debug("Migration skipped (%s): %s", exc, stmt)

    # Ensure storage dirs exist
    for sub in STORAGE_SUBDIRS:
        (settings.storage_root / sub).mkdir(parents=True, exist_ok=True)
    # Stored site logins. Kept out of STORAGE_SUBDIRS: those are per-item dirs
    # that purge_item_dirs() walks, and this one is neither.
    cookies_dir()

    # Start download workers
    queue: asyncio.Queue = asyncio.Queue()
    app.state.download_queue = queue
    workers = [
        asyncio.create_task(download_worker(queue))
        for _ in range(settings.download_workers)
    ]
    logger.info("Started %d download worker(s)", settings.download_workers)

    # Re-queue any videos that were in-flight when the server last stopped
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Video)
            .where(Video.status.in_(["pending", "downloading", "processing"]))
            .order_by(Video.created_at)
        )
        stuck = result.scalars().all()
        for v in stuck:
            v.status = "pending"
            v.progress = 0.0
            queue.put_nowait(v.id)
        if stuck:
            await db.commit()
            logger.info("Re-queued %d interrupted download(s)", len(stuck))

    yield

    # Shutdown
    for w in workers:
        w.cancel()
    await asyncio.gather(*workers, return_exceptions=True)
    await engine.dispose()


app = FastAPI(title="hamstr", version="0.1.0", lifespan=lifespan)

# The browser extension posts captures from whatever page the user is reading,
# so its requests carry that site's origin. The API has no cookie auth and no
# credentials, so a permissive origin list grants nothing a direct POST wouldn't.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=settings.cors_origin_regex,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    # X-Admin-Token gates the site-login routes; the extension sends it
    # cross-origin from the page it was invoked on.
    allow_headers=["Content-Type", "X-Admin-Token"],
)

app.include_router(videos.router, prefix="/api")
app.include_router(tags.router, prefix="/api")
app.include_router(playlists.router, prefix="/api")
app.include_router(cookies.router, prefix="/api")
app.include_router(stream.router)
app.include_router(ws.router)


@app.get("/api/health")
async def health():
    return {"status": "ok"}
