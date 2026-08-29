import asyncio
import logging
import re
from pathlib import Path

from sqlalchemy import select

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.video import Video
from app.services.broadcaster import manager
from app.services.cookies import active_cookie_file, explain_auth_error
from app.services.paths import purge_item_dirs, storage_dir
from app.services.tagging import apply_auto_tags, tags_for_item

logger = logging.getLogger(__name__)

VideoEntry = tuple[
    str, str, str | None, str | None, int | None
]  # id, url, title, channel, duration

# YouTube video IDs are exactly 11 characters from this alphabet (used by the fast path)
_YT_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{11}$")

# Safe ID for any yt-dlp extractor: no path separators, no traversal, reasonable length
_SAFE_ID_RE = re.compile(r"^[a-zA-Z0-9_.:\-]{1,200}$")


def _is_valid_video_id(vid_id: str) -> bool:
    return bool(_YT_ID_RE.match(vid_id))


def _is_safe_id(vid_id: str) -> bool:
    return bool(_SAFE_ID_RE.match(vid_id)) and ".." not in vid_id


def _ydl_base_opts() -> dict:
    """Base yt-dlp options, injecting the cookie jar when one is stored.

    Resolved per call, so a login added through the UI takes effect on the next
    download without a restart.
    """
    opts: dict = {
        "quiet": True,
        "no_warnings": True,
        # web_safari in addition to the defaults, not instead of them. An
        # age-restricted video is pushed onto clients whose adaptive formats
        # need a PO token we don't have, leaving only 360p; web_safari answers
        # with an HLS ladder that doesn't. Ordinary videos keep ranking the tv
        # client's formats first, so nothing is given up to gain it.
        "extractor_args": {"youtube": {"player_client": ["default", "web_safari"]}},
    }
    cf = active_cookie_file()
    if cf:
        opts["cookiefile"] = str(cf)
    return opts


# Kept as an alias so existing call sites (and tests) keep working.
_storage = storage_dir


async def _update_video(video_id: str, **kwargs) -> None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Video).where(Video.id == video_id))
        video = result.scalar_one_or_none()
        if video:
            for k, v in kwargs.items():
                setattr(video, k, v)
            await db.commit()


def _fast_parse_single(url: str) -> VideoEntry | None:
    """Parse a single-video URL without calling yt-dlp. Returns None for playlists/unknown."""
    from urllib.parse import urlparse, parse_qs

    try:
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        parts = [p for p in parsed.path.split("/") if p]
        seg0 = parts[0] if parts else ""
        seg1 = parts[1] if len(parts) > 1 else ""

        v_ids = qs.get("v")
        if v_ids and seg0 == "watch":
            vid_id = v_ids[0]
            if not _is_valid_video_id(vid_id):
                return None
            return (
                vid_id,
                f"https://www.youtube.com/watch?v={vid_id}",
                None,
                None,
                None,
            )
        if seg0 == "shorts" and seg1:
            if not _is_valid_video_id(seg1):
                return None
            return (seg1, f"https://www.youtube.com/shorts/{seg1}", None, None, None)
        if parsed.hostname == "youtu.be" and seg0:
            if not _is_valid_video_id(seg0):
                return None
            return (seg0, f"https://www.youtube.com/watch?v={seg0}", None, None, None)
    except Exception:
        pass
    return None


async def extract_videos_from_url(url: str) -> list[VideoEntry]:
    """Expand a URL into one or more (id, url, title, channel, duration) tuples.

    Single-video URLs are parsed directly without calling yt-dlp.
    Playlist URLs use extract_flat for fast expansion.
    """
    fast = _fast_parse_single(url)
    if fast is not None:
        return [fast]

    loop = asyncio.get_event_loop()

    def _extract() -> list[VideoEntry]:
        import yt_dlp

        opts = {
            **_ydl_base_opts(),
            "extract_flat": "in_playlist",
            "skip_download": True,
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)

        if not info:
            return []

        if info.get("_type") == "playlist":
            results: list[VideoEntry] = []
            for entry in info.get("entries") or []:
                if not entry:
                    continue
                vid_id = entry.get("id")
                if not vid_id or not _is_safe_id(vid_id):
                    continue
                vid_url = entry.get("webpage_url") or entry.get("url") or url
                results.append(
                    (
                        vid_id,
                        vid_url,
                        entry.get("title"),
                        entry.get("uploader") or entry.get("channel"),
                        entry.get("duration"),
                    )
                )
            return results

        vid_id = info["id"]
        if not _is_safe_id(vid_id):
            return []
        vid_url = info.get("webpage_url") or url
        return [
            (
                vid_id,
                vid_url,
                info.get("title"),
                info.get("uploader") or info.get("channel"),
                info.get("duration"),
            )
        ]

    return await loop.run_in_executor(None, _extract)


async def download_video(video_id: str, url: str) -> dict:
    """Download video with yt-dlp and return the extracted info dict."""
    loop = asyncio.get_event_loop()
    video_dir = _storage("videos", video_id)
    thumb_dir = _storage("thumbnails", video_id)

    def _progress_hook(d: dict) -> None:
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            downloaded = d.get("downloaded_bytes", 0)
            pct = (downloaded / total * 100) if total else 0
            asyncio.run_coroutine_threadsafe(
                _update_and_broadcast(video_id, pct, "downloading"), loop
            )

    def _run_ydl() -> dict:
        import yt_dlp

        opts = {
            **_ydl_base_opts(),
            "format": (
                "bestvideo[ext=mp4][vcodec^=avc]+bestaudio[ext=m4a]"
                "/bestvideo[vcodec^=avc]+bestaudio"
                "/bestvideo[ext=mp4]+bestaudio[ext=m4a]"
                "/best[ext=mp4]/best"
            ),
            "outtmpl": str(video_dir / "video.%(ext)s"),
            "writethumbnail": True,
            "postprocessors": [
                {"key": "FFmpegThumbnailsConvertor", "format": "jpg"},
            ],
            "progress_hooks": [_progress_hook],
            "paths": {"thumbnail": str(thumb_dir)},
            "noplaylist": True,  # single video only when downloading
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(url)

    return await loop.run_in_executor(None, _run_ydl)


async def download_audio_only(video_id: str, url: str) -> dict:
    """Download best audio stream and convert to MP3 with yt-dlp."""
    loop = asyncio.get_event_loop()
    audio_dir = _storage("audio", video_id)
    thumb_dir = _storage("thumbnails", video_id)

    def _progress_hook(d: dict) -> None:
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            downloaded = d.get("downloaded_bytes", 0)
            pct = (downloaded / total * 100) if total else 0
            asyncio.run_coroutine_threadsafe(
                _update_and_broadcast(video_id, pct, "downloading"), loop
            )

    def _run_ydl() -> dict:
        import yt_dlp

        opts = {
            **_ydl_base_opts(),
            "format": "bestaudio[ext=m4a]/bestaudio/best",
            "outtmpl": str(audio_dir / "audio.%(ext)s"),
            "writethumbnail": True,
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "0",
                },
                {"key": "FFmpegThumbnailsConvertor", "format": "jpg"},
            ],
            "progress_hooks": [_progress_hook],
            "paths": {"thumbnail": str(thumb_dir)},
            "noplaylist": True,
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(url)

    return await loop.run_in_executor(None, _run_ydl)


async def _update_and_broadcast(video_id: str, progress: float, status: str) -> None:
    # Guard: discard stale callbacks that arrive after download_worker has already
    # transitioned the video past "downloading". Without this check, the last progress
    # event queued via run_coroutine_threadsafe overwrites "processing"/"completed"
    # with "downloading" at the final hook percentage, leaving the UI stuck.
    # Also enforces monotonic progress: yt-dlp fires separate hooks for video and
    # audio streams, so progress can reset to 0 between them — skip any backward step.
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Video).where(Video.id == video_id))
        video = result.scalar_one_or_none()
        if not video or video.status not in ("pending", "downloading"):
            return
        if progress < video.progress:
            return
        video.progress = progress
        video.status = status
        await db.commit()
    await manager.broadcast(
        {
            "type": "progress",
            "video_id": video_id,
            "progress": progress,
            "status": status,
        }
    )


async def detect_codec(video_file: Path) -> str:
    """Return the video codec name (lower-case) or 'unknown' if ffprobe fails."""
    probe = await asyncio.create_subprocess_exec(
        "ffprobe",
        "-v",
        "quiet",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=codec_name",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(video_file),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    stdout, _ = await probe.communicate()
    return stdout.decode().strip().lower() or "unknown"


async def _ensure_h264(video_file: Path) -> None:
    """Re-encode to H.264/AAC in-place if the video uses a browser-incompatible codec (e.g. HEVC)."""
    codec = await detect_codec(video_file)
    if codec == "h264":
        return

    logger.info(
        "Re-encoding %s from %s to H.264 for browser compatibility",
        video_file.name,
        codec,
    )
    tmp = video_file.with_name("video_tmp.mp4")
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg",
        "-y",
        "-i",
        str(video_file),
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "23",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-movflags",
        "+faststart",
        str(tmp),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        tmp.unlink(missing_ok=True)
        logger.warning(
            "Re-encode failed for %s: %s",
            video_file,
            stderr.decode(errors="replace")[-500:],
        )
        return
    video_file.unlink()
    tmp.rename(video_file)


async def _extract_thumbnail(video_file: Path, dest: Path) -> Path | None:
    """Extract a frame from the middle of the video as a fallback thumbnail."""
    probe = await asyncio.create_subprocess_exec(
        "ffprobe",
        "-v",
        "quiet",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(video_file),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    stdout, _ = await probe.communicate()
    try:
        seek = float(stdout.decode().strip()) / 2
    except ValueError:
        seek = 5.0

    dest.parent.mkdir(parents=True, exist_ok=True)
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg",
        "-y",
        "-ss",
        str(seek),
        "-i",
        str(video_file),
        "-frames:v",
        "1",
        "-q:v",
        "2",
        str(dest),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        logger.warning(
            "Thumbnail extraction failed for %s: %s",
            video_file,
            stderr.decode(errors="replace")[-300:],
        )
        return None
    return dest


async def extract_audio(video_id: str) -> tuple[str | None, str | None]:
    """Convert downloaded video to mp3 and ogg. Returns (mp3_rel, ogg_rel), either may be None on failure."""
    video_dir = settings.storage_root / "videos" / video_id
    audio_dir = _storage("audio", video_id)

    # Prefer .mp4, fall back to any video file
    video_file = (
        (video_dir / "video.mp4")
        if (video_dir / "video.mp4").exists()
        else next(video_dir.glob("video.*"), None)
    )
    if not video_file:
        logger.warning(
            "No video file found for %s, skipping audio extraction", video_id
        )
        return None, None

    mp3_path = audio_dir / "audio.mp3"
    ogg_path = audio_dir / "audio.ogg"

    async def _run(output: Path, extra_args: list[str]) -> bool:
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg",
            "-y",
            "-i",
            str(video_file),
            "-vn",
            *extra_args,
            str(output),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            logger.warning(
                "ffmpeg failed for %s: %s",
                output,
                stderr.decode(errors="replace")[-500:],
            )
            return False
        return True

    mp3_ok, ogg_ok = await asyncio.gather(
        _run(mp3_path, ["-q:a", "0"]),
        _run(ogg_path, ["-c:a", "libvorbis", "-q:a", "4"]),
    )

    root = settings.storage_root.resolve()
    mp3_rel = str(mp3_path.relative_to(root)) if mp3_ok else None
    ogg_rel = str(ogg_path.relative_to(root)) if ogg_ok else None
    return mp3_rel, ogg_rel


async def _finish_ytdlp_job(video_id: str, video_url: str, audio_only: bool) -> None:
    """The original yt-dlp path: download, transcode, extract audio, thumbnail."""
    info = await (download_audio_only if audio_only else download_video)(
        video_id, video_url
    )

    await _update_video(
        video_id,
        title=info.get("title"),
        channel=info.get("uploader") or info.get("channel"),
        duration_seconds=info.get("duration"),
    )

    await _update_video(video_id, status="processing", progress=100.0)
    await manager.broadcast(
        {"type": "status_change", "video_id": video_id, "status": "processing"}
    )

    thumb_dir = settings.storage_root / "thumbnails" / video_id

    if audio_only:
        audio_dir = settings.storage_root / "audio" / video_id
        mp3_file = audio_dir / "audio.mp3"

        thumb_file = next(thumb_dir.glob("*.jpg"), None) or next(
            thumb_dir.glob("*.webp"), None
        )

        # Convert MP3 → OGG for broader browser compatibility
        ogg_file = audio_dir / "audio.ogg"
        if mp3_file.exists():
            proc = await asyncio.create_subprocess_exec(
                "ffmpeg",
                "-y",
                "-i",
                str(mp3_file),
                "-c:a",
                "libvorbis",
                "-q:a",
                "4",
                str(ogg_file),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.communicate()

        mp3_rel = (
            str(mp3_file.relative_to(settings.storage_root))
            if mp3_file.exists()
            else None
        )
        ogg_rel = (
            str(ogg_file.relative_to(settings.storage_root))
            if ogg_file.exists()
            else None
        )
        thumb_rel = (
            str(thumb_file.relative_to(settings.storage_root)) if thumb_file else None
        )
        file_size = mp3_file.stat().st_size if mp3_file.exists() else None

        await _update_video(
            video_id,
            status="completed",
            progress=100.0,
            video_path=None,
            audio_mp3_path=mp3_rel,
            audio_ogg_path=ogg_rel,
            thumbnail_path=thumb_rel,
            file_size_bytes=file_size,
            codec=None,
            file_path=mp3_rel,
            mime_type="audio/mpeg" if mp3_rel else None,
        )
    else:
        video_dir = settings.storage_root / "videos" / video_id
        video_file = (
            (video_dir / "video.mp4")
            if (video_dir / "video.mp4").exists()
            else next(video_dir.glob("video.*"), None)
        )

        thumb_file = (
            next(thumb_dir.glob("*.jpg"), None)
            or next(thumb_dir.glob("*.webp"), None)
            or next(video_dir.glob("*.jpg"), None)
        )

        final_codec: str | None = None
        if video_file:
            await _ensure_h264(video_file)
            final_codec = await detect_codec(video_file)

        if not thumb_file and video_file:
            thumb_file = await _extract_thumbnail(video_file, thumb_dir / "thumb.jpg")

        mp3_rel, ogg_rel = await extract_audio(video_id)

        video_rel = (
            str(video_file.relative_to(settings.storage_root)) if video_file else None
        )
        thumb_rel = (
            str(thumb_file.relative_to(settings.storage_root)) if thumb_file else None
        )
        file_size = video_file.stat().st_size if video_file else None

        await _update_video(
            video_id,
            status="completed",
            progress=100.0,
            video_path=video_rel,
            audio_mp3_path=mp3_rel,
            audio_ogg_path=ogg_rel,
            thumbnail_path=thumb_rel,
            file_size_bytes=file_size,
            codec=final_codec,
            file_path=video_rel,
            mime_type="video/mp4" if video_rel else None,
        )


async def _finish_file_job(item_id: str, url: str) -> None:
    """Direct download of a plain file (PDF, image, loose media, text, archive)."""
    from app.services.ingest.file import download_file

    async def _progress(pct: float) -> None:
        await _update_and_broadcast(item_id, pct, "downloading")

    result = await download_file(item_id, url, on_progress=_progress)

    await _update_video(item_id, status="processing", progress=100.0)
    await manager.broadcast(
        {"type": "status_change", "video_id": item_id, "status": "processing"}
    )

    file_abs = (settings.storage_root / result.rel_path).resolve()
    updates: dict = {
        "status": "completed",
        "progress": 100.0,
        "kind": result.kind,
        "file_path": result.rel_path,
        "file_name": result.file_name,
        "mime_type": result.mime_type,
        "file_size_bytes": result.size,
        "title": result.file_name,
    }

    if result.kind == "image":
        # Serving the original into a 300px grid tile cost a megabyte a time.
        from app.services.images import make_thumbnail

        thumb = await make_thumbnail(
            file_abs, settings.storage_root / "thumbnails" / item_id
        )
        updates["thumbnail_path"] = (
            str(thumb.relative_to(settings.storage_root.resolve()))
            if thumb
            else result.rel_path
        )
    elif result.kind == "video":
        # Reuse the existing pipeline so a bare .mp4 plays in the normal player.
        await _ensure_h264(file_abs)
        updates["codec"] = await detect_codec(file_abs)
        updates["video_path"] = result.rel_path
        updates["file_size_bytes"] = file_abs.stat().st_size
        thumb = await _extract_thumbnail(
            file_abs, settings.storage_root / "thumbnails" / item_id / "thumb.jpg"
        )
        if thumb:
            updates["thumbnail_path"] = str(
                thumb.relative_to(settings.storage_root.resolve())
            )
    elif result.kind == "audio" and result.mime_type == "audio/mpeg":
        # Make /stream/{id}/audio/mp3 honest for real MP3s.
        updates["audio_mp3_path"] = result.rel_path

    await _update_video(item_id, **updates)


def _pending_capture_path(item_id: str) -> Path:
    """Where the extension's uploaded HTML waits for the worker."""
    return storage_dir("articles", item_id) / "captured.html"


def _pending_capture_source_path(item_id: str) -> Path:
    """Records the mirror an uploaded capture came from, when it wasn't the page."""
    return storage_dir("articles", item_id) / "captured.source"


async def _finish_article_job(item_id: str, url: str) -> None:
    """Reader-view capture of a web page."""
    import json
    from urllib.parse import urlsplit

    from app.services.ingest.article import capture_article

    async def _progress(pct: float) -> None:
        await _update_and_broadcast(item_id, pct, "downloading")

    # A browser-extension capture arrives with the HTML already on disk; the
    # worker archives that instead of fetching the page itself.
    supplied: str | None = None
    supplied_from: str | None = None
    pending = _pending_capture_path(item_id)
    pending_source = _pending_capture_source_path(item_id)
    if pending.exists():
        supplied = pending.read_text(encoding="utf-8")
        if pending_source.exists():
            supplied_from = pending_source.read_text(encoding="utf-8").strip() or None

    async with asyncio.timeout(settings.article_capture_timeout):
        result = await capture_article(
            item_id,
            url,
            on_progress=_progress,
            supplied_html=supplied,
            supplied_from=supplied_from,
        )

    pending.unlink(missing_ok=True)
    pending_source.unlink(missing_ok=True)

    await _update_video(item_id, status="processing", progress=100.0)
    await manager.broadcast(
        {"type": "status_change", "video_id": item_id, "status": "processing"}
    )

    await _update_video(
        item_id,
        status="completed",
        progress=100.0,
        kind="article",
        title=result.title,
        # `channel` is what the cards already render under the title.
        channel=result.site_name,
        source_domain=urlsplit(result.capture_url).hostname,
        byline=result.byline,
        published_at=result.published,
        excerpt=result.excerpt,
        word_count=result.word_count,
        article_html_path=result.article_rel,
        raw_html_path=result.raw_rel,
        file_path=result.article_rel or result.raw_rel,
        mime_type="text/html",
        thumbnail_path=result.thumb_rel,
        file_size_bytes=result.bytes_total or None,
        capture_source=result.capture_source,
        capture_url=result.capture_url,
        paywalled=result.paywalled,
        extra=json.dumps({"assets": result.asset_names}),
    )


async def download_worker(queue: asyncio.Queue) -> None:
    logger.info("Download worker started")
    while True:
        video_id: str = await queue.get()
        # Bound before the try: the error path reads it, and the name would
        # otherwise survive from the previous iteration or be unset entirely.
        video_url = ""
        try:
            # Skip if the item was deleted while sitting in queue; fetch URL and kind
            async with AsyncSessionLocal() as db:
                video = await db.get(Video, video_id)
                if not video:
                    continue
                video_url = video.url
                audio_only = video.audio_only
                handler = video.handler or "ytdlp"

            await _update_video(video_id, status="downloading", progress=0.0)
            await manager.broadcast(
                {"type": "status_change", "video_id": video_id, "status": "downloading"}
            )

            if handler == "article":
                await _finish_article_job(video_id, video_url)
            elif handler == "file":
                await _finish_file_job(video_id, video_url)
            else:
                await _finish_ytdlp_job(video_id, video_url, audio_only)

            async with AsyncSessionLocal() as db:
                result = await db.execute(select(Video).where(Video.id == video_id))
                v = result.scalar_one_or_none()
                title = v.title if v else None
                auto_tags = tags_for_item(v) if v else []

            if auto_tags:
                await apply_auto_tags(video_id, auto_tags)

            await manager.broadcast(
                {
                    "type": "completed",
                    "video_id": video_id,
                    "title": title,
                    "status": "completed",
                }
            )
            logger.info("Completed download for %s", video_id)

        except Exception as exc:
            logger.exception("Download failed for %s", video_id)
            from app.services.ingest.types import PaywalledError

            message = explain_auth_error(str(exc), video_url) or str(exc)
            updates = {"status": "error", "error_message": message}
            if isinstance(exc, PaywalledError):
                # Otherwise the row reads "Paywalled" in its error text while the
                # field says False, and the library can't filter for it.
                updates["paywalled"] = True
            await _update_video(video_id, **updates)
            await manager.broadcast(
                {
                    "type": "error",
                    "video_id": video_id,
                    "error": message,
                    "status": "error",
                }
            )
            purge_item_dirs(video_id)
        finally:
            queue.task_done()
