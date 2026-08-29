"""Automatic tagging.

Auto-tags are ordinary Tag rows — indistinguishable from ones the user typed, so
the existing tag editor and DELETE endpoint remove them normally. They are only
applied when an item completes, so a deletion sticks until an explicit retry.
"""

import logging
from collections.abc import Iterable

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.video import Tag, Video
from app.services.ingest.sniff import url_extension
from app.services.ingest.tagmap import tags_for

logger = logging.getLogger(__name__)


async def apply_auto_tags(item_id: str, names: Iterable[str]) -> None:
    """Add any of `names` that aren't already on the item.

    SELECT-then-insert rather than catching IntegrityError: the worker is the only
    writer on this path, so there's no race to lose.
    """
    wanted = {n.strip().lower() for n in names if n and n.strip()}
    if not wanted:
        return

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Tag.name).where(Tag.video_id == item_id))
        existing = {row[0] for row in result.all()}

        missing = wanted - existing
        if not missing:
            return

        for name in sorted(missing):
            db.add(Tag(video_id=item_id, name=name))
        try:
            await db.commit()
        except Exception:
            await db.rollback()
            logger.exception("Failed to auto-tag %s", item_id)


def tags_for_item(video: Video) -> list[str]:
    """The auto-tags an existing row should carry, derived from what's on disk.

    The extension has to come from the artifact, not the source URL: a yt-dlp
    row's `url` is a YouTube watch page with no extension at all, and for
    audio-only rows the only artifact path is `audio_mp3_path`.
    """
    ext = None
    if video.file_name and "." in video.file_name:
        ext = "." + video.file_name.rsplit(".", 1)[-1]

    if not ext:
        for candidate in (
            video.file_path,
            video.video_path,
            video.audio_mp3_path,
            video.audio_ogg_path,
            video.url,
        ):
            ext = url_extension(candidate or "") or None
            if ext:
                break

    kind = video.kind or ("audio" if video.audio_only else "video")
    return tags_for(kind, video.mime_type, ext)
