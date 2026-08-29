import asyncio
import hashlib
import logging
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.database import get_db, AsyncSessionLocal
from app.models.video import PlaylistItem, Tag, Video
from app.schemas.video import (
    CaptureRequest,
    SubmitRequest,
    SubmitResponse,
    SubmittedItem,
    TagRequest,
    VideoListResponse,
    VideoSchema,
)
from app.services.downloader import detect_codec, _ensure_h264
from app.services.broadcaster import manager
from app.services.downloader import (
    _pending_capture_path,
    _pending_capture_source_path,
)
from app.services.ingest.dispatch import expand_url
from app.services.ingest.ids import ARTICLE_ID_PREFIX, make_item_id
from app.services.paths import purge_item_dirs
from app.services.tagging import apply_auto_tags, tags_for_item

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/videos", tags=["videos"])


@router.post("", status_code=202, response_model=SubmitResponse)
async def submit_videos(
    body: SubmitRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    submitted: list[SubmittedItem] = []
    skipped: list[SubmittedItem] = []

    # Expand all URLs concurrently. Media URLs resolve instantly or via yt-dlp;
    # everything else costs at most one HEAD probe.
    async def _expand(raw_url: str) -> tuple[list, str | None]:
        raw_url = raw_url.strip()
        if not raw_url:
            return [], None
        try:
            async with asyncio.timeout(30):
                return await expand_url(
                    raw_url, audio_only=body.audio_only, mode=body.mode
                ), None
        except Exception as exc:
            logger.warning("Failed to expand URL %s: %s", raw_url, exc)
            return [], str(exc) or exc.__class__.__name__

    all_results = await asyncio.gather(*[_expand(u.strip()) for u in body.urls])

    for raw_url, (entries, error) in zip(body.urls, all_results):
        raw_url = raw_url.strip()

        if error:
            # Expansion failed — create an error record so it's visible in the queue
            error_id = "err_" + hashlib.sha256(raw_url.encode()).hexdigest()[:12]
            existing = await db.get(Video, error_id)
            if existing:
                skipped.append(
                    SubmittedItem(id=error_id, url=raw_url, status=existing.status)
                )
            else:
                video = Video(
                    id=error_id,
                    url=raw_url,
                    status="error",
                    progress=0.0,
                    error_message=error,
                )
                db.add(video)
                try:
                    await db.commit()
                    submitted.append(
                        SubmittedItem(id=error_id, url=raw_url, status="error")
                    )
                except IntegrityError:
                    await db.rollback()
            continue

        for entry in entries:
            video_id, video_url = entry.id, entry.url
            existing = await db.get(Video, video_id)
            if existing:
                skipped.append(
                    SubmittedItem(id=video_id, url=video_url, status=existing.status)
                )
                continue

            video = Video(
                id=video_id,
                url=video_url,
                title=entry.title,
                channel=entry.channel,
                duration_seconds=entry.duration,
                status="pending",
                progress=0.0,
                audio_only=entry.audio_only,
                kind=entry.kind,
                handler=entry.handler,
                mime_type=entry.mime_type,
            )
            db.add(video)
            try:
                await db.commit()
            except IntegrityError:
                await db.rollback()
                existing = await db.get(Video, video_id)
                skipped.append(
                    SubmittedItem(
                        id=video_id,
                        url=video_url,
                        status=existing.status if existing else "unknown",
                    )
                )
                continue

            request.app.state.download_queue.put_nowait(video_id)
            submitted.append(
                SubmittedItem(id=video_id, url=video_url, status="pending")
            )

    return SubmitResponse(submitted=submitted, skipped=skipped)


@router.get("", response_model=VideoListResponse)
async def list_videos(
    status: str | None = Query(None),
    kind: str | None = Query(None),
    tag: str | None = Query(None),
    q: str | None = Query(None),
    sort: Literal[
        "created_at", "title", "duration_seconds", "updated_at"
    ] = "created_at",
    order: Literal["asc", "desc"] = "desc",
    limit: int = Query(50, ge=1, le=2000),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Video)

    if status:
        statuses = [s.strip() for s in status.split(",")]
        stmt = stmt.where(Video.status.in_(statuses))

    if kind:
        kinds = [k.strip() for k in kind.split(",") if k.strip()]
        if kinds:
            stmt = stmt.where(Video.kind.in_(kinds))

    if tag:
        stmt = stmt.where(Video.tags.any(Tag.name == tag))

    if q:
        stmt = stmt.where(Video.title.ilike(f"%{q}%"))

    col = getattr(Video, sort)
    stmt = stmt.order_by(col.desc() if order == "desc" else col.asc())

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    result = await db.execute(
        stmt.options(selectinload(Video.tags)).offset(offset).limit(limit)
    )
    items = result.scalars().all()

    return VideoListResponse(items=items, total=total)


# Queue statuses = everything that isn't a finished Library video.
QUEUE_STATUSES = ("pending", "downloading", "processing", "error")


@router.delete("/queue", status_code=200)
async def clear_queue(db: AsyncSession = Depends(get_db)):
    """Bulk-delete the whole download queue (pending / downloading / processing /
    error) and their on-disk files. Completed Library videos are kept.

    Safe to call while a download is in flight: the worker's DB writes no-op once
    the row is gone (see downloader._update_video)."""
    result = await db.execute(select(Video.id).where(Video.status.in_(QUEUE_STATUSES)))
    ids = [row[0] for row in result.all()]
    if not ids:
        return {"deleted": 0}

    for vid in ids:
        purge_item_dirs(vid)

    # Delete children explicitly — a bulk DELETE bypasses the ORM cascade. The
    # FK cascade now runs too (PRAGMA foreign_keys, see database.py); this keeps
    # working if that ever goes away again.
    await db.execute(delete(Tag).where(Tag.video_id.in_(ids)))
    await db.execute(delete(PlaylistItem).where(PlaylistItem.video_id.in_(ids)))
    await db.execute(delete(Video).where(Video.id.in_(ids)))
    await db.commit()
    return {"deleted": len(ids)}


async def _get_video_with_tags(video_id: str, db: AsyncSession) -> Video:
    result = await db.execute(
        select(Video).options(selectinload(Video.tags)).where(Video.id == video_id)
    )
    video = result.scalar_one_or_none()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    return video


# In-memory transcode job registry, insertion-ordered: video_id -> "queued" | "running".
# "queued" = fix-all knows this video needs transcoding and will get to it;
# "running" = ffmpeg is working on it right now.
_transcode_jobs: dict[str, str] = {}


@router.post("/fix-all-codecs", status_code=202)
async def fix_all_codecs(db: AsyncSession = Depends(get_db)):
    """Detect codec + repair missing thumbnail paths for all completed videos.
    Transcodes any non-H.264 video to H.264."""
    result = await db.execute(select(Video).where(Video.status == "completed"))
    all_videos = result.scalars().all()

    from app.config import settings
    from pathlib import Path

    # (video_id, video_file_or_None) — None means audio-only, only thumbnail fix needed
    items: list[tuple[str, Path | None]] = []
    for v in all_videos:
        if v.audio_only:
            items.append((v.id, None))
        else:
            if v.id in _transcode_jobs or not v.video_path:
                continue
            vf = (settings.storage_root / v.video_path).resolve()
            if vf.exists():
                items.append((v.id, vf))
                # Codec already known to be wrong → this one will definitely be
                # transcoded, so show it queued right away. Videos with an
                # unknown codec join the queue once detection runs.
                if v.codec and v.codec != "h264":
                    _transcode_jobs[v.id] = "queued"
                    await manager.broadcast(
                        {"type": "transcode_queued", "video_id": v.id}
                    )

    asyncio.create_task(_fix_all_task(items))
    return {"status": "started", "count": len(items)}


async def _fix_all_task(videos: list[tuple[str, "Path | None"]]) -> None:
    from pathlib import Path
    from app.config import settings

    for video_id, video_file in videos:
        # Skip only if something else (single-transcode endpoint) is already
        # running it — "queued" entries are this task's own and must proceed.
        if video_file and _transcode_jobs.get(video_id) == "running":
            continue
        try:
            codec: str | None = None
            if video_file:
                codec = await detect_codec(Path(video_file))

            async with AsyncSessionLocal() as db:
                result = await db.execute(select(Video).where(Video.id == video_id))
                v = result.scalar_one_or_none()
                if not v:
                    continue

                changed = False
                if codec is not None and v.codec != codec:
                    v.codec = codec
                    changed = True

                # Repair missing thumbnail path — scan known on-disk locations
                if not v.thumbnail_path:
                    root = settings.storage_root
                    for d in [
                        root / "thumbnails" / video_id,
                        root / "videos" / video_id,
                        root / "audio" / video_id,
                    ]:
                        if d.exists():
                            thumb = next(d.glob("*.jpg"), None) or next(
                                d.glob("*.webp"), None
                            )
                            if thumb:
                                v.thumbnail_path = str(thumb.relative_to(root))
                                changed = True
                                break

                if changed:
                    await db.commit()

            if codec and codec != "h264" and video_file:
                _transcode_jobs[video_id] = "running"
                await manager.broadcast(
                    {
                        "type": "transcoding",
                        "video_id": video_id,
                        "codec": "transcoding",
                    }
                )
                await _run_transcode(video_id, Path(video_file))
            elif video_file and _transcode_jobs.pop(video_id, None):
                # Pre-queued on a stale DB codec, but the file is fine after all.
                await manager.broadcast(
                    {"type": "transcode_dequeued", "video_id": video_id}
                )
        except Exception:
            _transcode_jobs.pop(video_id, None)
            logger.exception("fix_all_task failed for %s", video_id)


@router.post("/capture", status_code=202, response_model=SubmittedItem)
async def capture_page(
    body: CaptureRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Archive a page whose HTML the browser extension already captured.

    The browser ran the page's JavaScript, cleared whatever bot check it has and
    used the reader's own session, so this is content the server could not fetch
    for itself. The HTML is parked next to the item and the normal article
    pipeline picks it up — same extraction, sanitising and asset handling.
    """
    item_id = make_item_id(ARTICLE_ID_PREFIX, body.url)

    existing = await db.get(Video, item_id)
    if existing and existing.status == "completed":
        # Re-capturing is how you refresh a page, so replace rather than skip.
        purge_item_dirs(item_id)
        await db.delete(existing)
        await db.commit()
        existing = None

    _pending_capture_path(item_id).write_text(body.html, encoding="utf-8")
    if body.archive_url:
        _pending_capture_source_path(item_id).write_text(
            body.archive_url, encoding="utf-8"
        )

    if existing is None:
        db.add(
            Video(
                id=item_id,
                url=body.url,
                title=body.title,
                status="pending",
                progress=0.0,
                kind="article",
                handler="article",
                mime_type="text/html",
                source_domain=urlsplit(body.url).hostname,
            )
        )
    else:
        existing.status = "pending"
        existing.progress = 0.0
        existing.error_message = None
    await db.commit()

    request.app.state.download_queue.put_nowait(item_id)
    return SubmittedItem(id=item_id, url=body.url, status="pending")


@router.post("/rebuild-thumbnails", status_code=202)
async def rebuild_thumbnails(db: AsyncSession = Depends(get_db)):
    """Re-generate grid thumbnails at a sane size.

    Items archived before thumbnails were downscaled point at the original file
    — sometimes a megabyte of animated GIF for a 300px tile.
    """
    result = await db.execute(select(Video).where(Video.status == "completed"))
    # Judged on actual width, not on the filename: the previous code wrote the
    # untouched original to a file called thumb.jpg, so the name says nothing.
    targets = [
        (v.id, v.thumbnail_path)
        for v in result.scalars().all()
        if v.thumbnail_path and _needs_smaller_thumbnail(v.thumbnail_path)
    ]
    asyncio.create_task(_rebuild_thumbnails_task(targets))
    return {"status": "started", "count": len(targets)}


def _needs_smaller_thumbnail(rel: str) -> bool:
    from app.config import settings
    from app.services.images import THUMBNAIL_MAX_WIDTH
    from app.services.ingest.sniff import image_size

    try:
        path = (settings.storage_root / rel).resolve()
        if not path.exists():
            return False
        with path.open("rb") as fh:
            size = image_size(fh.read(65536))
    except OSError:
        return False
    # Unknown dimensions: rebuild only if the file is plainly too heavy for a tile.
    if size is None:
        try:
            return path.stat().st_size > 120_000
        except OSError:
            return False
    return size[0] > THUMBNAIL_MAX_WIDTH


async def _rebuild_thumbnails_task(targets: list[tuple[str, str]]) -> None:
    from app.config import settings
    from app.services.images import make_thumbnail

    for item_id, rel in targets:
        try:
            source = (settings.storage_root / rel).resolve()
            if not source.exists():
                continue
            dest_dir = settings.storage_root / "thumbnails" / item_id
            thumb = await make_thumbnail(source, dest_dir)
            if thumb is None:
                continue
            new_rel = str(thumb.relative_to(settings.storage_root.resolve()))
            async with AsyncSessionLocal() as session:
                row = await session.get(Video, item_id)
                if row:
                    row.thumbnail_path = new_rel
                    await session.commit()
        except Exception:
            logger.exception("Thumbnail rebuild failed for %s", item_id)


@router.get("/kinds")
async def kind_counts(db: AsyncSession = Depends(get_db)):
    """Facet counts per kind, for the library filter row."""
    result = await db.execute(
        select(Video.kind, func.count())
        .where(Video.status == "completed")
        .group_by(Video.kind)
    )
    return {kind or "video": count for kind, count in result.all()}


@router.post("/retag-all", status_code=202)
async def retag_all(db: AsyncSession = Depends(get_db)):
    """Backfill category/format tags onto every completed item.

    Safe to re-run: apply_auto_tags only inserts names that are missing.
    """
    result = await db.execute(select(Video).where(Video.status == "completed"))
    plans = [(v.id, tags_for_item(v)) for v in result.scalars().all()]
    asyncio.create_task(_retag_all_task(plans))
    return {"status": "started", "count": len(plans)}


async def _retag_all_task(plans: list[tuple[str, list[str]]]) -> None:
    for item_id, names in plans:
        try:
            await apply_auto_tags(item_id, names)
        except Exception:
            logger.exception("retag_all failed for %s", item_id)


@router.get("/transcodes")
async def list_transcodes(db: AsyncSession = Depends(get_db)):
    """Current transcode jobs (running + queued), oldest first, for the Queue page."""
    jobs = list(_transcode_jobs.items())
    if not jobs:
        return []
    result = await db.execute(
        select(Video).where(Video.id.in_([vid for vid, _ in jobs]))
    )
    by_id = {v.id: v for v in result.scalars().all()}
    out = [
        {
            "id": vid,
            "state": state,
            "title": by_id[vid].title if vid in by_id else None,
            "channel": by_id[vid].channel if vid in by_id else None,
            "thumbnail_path": by_id[vid].thumbnail_path if vid in by_id else None,
            "kind": by_id[vid].kind if vid in by_id else None,
        }
        for vid, state in jobs
    ]
    # Running job(s) first; sort is stable so queue order is kept within groups.
    out.sort(key=lambda j: 0 if j["state"] == "running" else 1)
    return out


@router.get("/{video_id}", response_model=VideoSchema)
async def get_video(video_id: str, db: AsyncSession = Depends(get_db)):
    return await _get_video_with_tags(video_id, db)


@router.post("/{video_id}/retry", status_code=202, response_model=VideoSchema)
async def retry_video(
    video_id: str, request: Request, db: AsyncSession = Depends(get_db)
):
    video = await _get_video_with_tags(video_id, db)
    if video.status != "error":
        raise HTTPException(
            status_code=409, detail="Only failed downloads can be retried"
        )
    video.status = "pending"
    video.progress = 0.0
    video.error_message = None
    await db.commit()
    await db.refresh(video)
    request.app.state.download_queue.put_nowait(video_id)
    return video


@router.post("/{video_id}/transcode", status_code=202)
async def transcode_video(video_id: str, db: AsyncSession = Depends(get_db)):
    video = await _get_video_with_tags(video_id, db)
    if video.status != "completed":
        raise HTTPException(status_code=409, detail=f"Video status is '{video.status}'")
    if video_id in _transcode_jobs:
        raise HTTPException(status_code=409, detail="Transcode already in progress")
    if not video.video_path:
        raise HTTPException(status_code=404, detail="No video file available")

    from app.config import settings

    video_file = (settings.storage_root / video.video_path).resolve()
    if not video_file.exists():
        raise HTTPException(status_code=404, detail="Video file not found on disk")

    _transcode_jobs[video_id] = "running"
    asyncio.create_task(_run_transcode(video_id, video_file))
    await manager.broadcast(
        {"type": "transcoding", "video_id": video_id, "codec": "transcoding"}
    )
    return {"status": "transcoding"}


async def _run_transcode(video_id: str, video_file) -> None:
    from pathlib import Path

    try:
        await _ensure_h264(Path(video_file))
        codec = await detect_codec(Path(video_file))
        file_size = Path(video_file).stat().st_size

        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Video).where(Video.id == video_id))
            video = result.scalar_one_or_none()
            if video:
                video.codec = codec
                video.file_size_bytes = file_size
                await db.commit()

        await manager.broadcast(
            {
                "type": "transcoded",
                "video_id": video_id,
                "codec": codec,
                "file_size_bytes": file_size,
            }
        )
        logger.info("Transcode completed for %s: %s", video_id, codec)
    except Exception:
        logger.exception("Transcode failed for %s", video_id)
        await manager.broadcast({"type": "transcode_error", "video_id": video_id})
    finally:
        _transcode_jobs.pop(video_id, None)


@router.delete("/{video_id}", status_code=204)
async def delete_video(video_id: str, db: AsyncSession = Depends(get_db)):
    video = await _get_video_with_tags(video_id, db)
    purge_item_dirs(video_id)
    # Drop the item from every playlist it sits in; Video has no ORM
    # relationship to PlaylistItem to cascade through.
    await db.execute(delete(PlaylistItem).where(PlaylistItem.video_id == video_id))
    await db.delete(video)
    await db.commit()


async def _tag_names(video_id: str, db: AsyncSession) -> list[str]:
    result = await db.execute(
        select(Tag.name).where(Tag.video_id == video_id).order_by(Tag.name)
    )
    return [row[0] for row in result.all()]


async def _video_exists(video_id: str, db: AsyncSession) -> bool:
    result = await db.execute(select(Video.id).where(Video.id == video_id))
    return result.scalar_one_or_none() is not None


@router.get("/{video_id}/tags")
async def get_tags(video_id: str, db: AsyncSession = Depends(get_db)):
    if not await _video_exists(video_id, db):
        raise HTTPException(status_code=404, detail="Video not found")
    return await _tag_names(video_id, db)


@router.post("/{video_id}/tags", status_code=201)
async def add_tag(video_id: str, body: TagRequest, db: AsyncSession = Depends(get_db)):
    if not await _video_exists(video_id, db):
        raise HTTPException(status_code=404, detail="Video not found")
    name = body.name.strip().lower()
    existing = await db.execute(
        select(Tag).where(Tag.video_id == video_id, Tag.name == name)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Tag already exists")
    db.add(Tag(video_id=video_id, name=name))
    await db.commit()
    return await _tag_names(video_id, db)


@router.delete("/{video_id}/tags/{tag_name}", status_code=204)
async def remove_tag(video_id: str, tag_name: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Tag).where(Tag.video_id == video_id, Tag.name == tag_name.lower())
    )
    tag = result.scalar_one_or_none()
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")
    await db.delete(tag)
    await db.commit()
