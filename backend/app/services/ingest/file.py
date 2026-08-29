"""Direct download of a plain file: PDF, image, loose media, text, archive."""

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

import httpx

from app.config import settings
from app.services.ingest.http import (
    IngestHttpError,
    build_client,
    describe_http_error,
    safe_stream_to_file,
)
from app.services.ingest.sniff import resolve_media, safe_filename
from app.services.ingest.types import IngestError
from app.services.paths import storage_dir

logger = logging.getLogger(__name__)

# Don't hammer SQLite/the WebSocket on every chunk.
_PROGRESS_STEP_BYTES = 1024 * 1024


@dataclass
class FileResult:
    rel_path: str
    file_name: str
    mime_type: str
    size: int
    kind: str


async def download_file(
    item_id: str,
    url: str,
    on_progress: Callable[[float], Awaitable[None]] | None = None,
) -> FileResult:
    """Stream `url` into ``files/<item_id>/`` and report what landed there.

    The name and MIME type on disk come from the response, not the submitted URL,
    so a redirect to a differently-named file is recorded honestly.
    """
    dest_dir = storage_dir("files", item_id)
    tmp = dest_dir / ".download"

    last_reported = 0

    async def _progress(written: int, expected: int | None) -> None:
        nonlocal last_reported
        if on_progress is None or not expected:
            return
        if written - last_reported < _PROGRESS_STEP_BYTES and written < expected:
            return
        last_reported = written
        await on_progress(min(99.0, written / expected * 100.0))

    async with build_client() as client:
        try:
            written, response = await safe_stream_to_file(
                client,
                url,
                tmp,
                max_bytes=settings.max_file_bytes,
                on_progress=_progress,
            )
        except (httpx.HTTPError, IngestHttpError) as exc:
            # The raw httpx message spans three lines and links to MDN; the queue
            # row needs one readable sentence.
            raise IngestError(describe_http_error(exc)) from exc

    head = b""
    try:
        with tmp.open("rb") as fh:
            head = fh.read(2048)
    except OSError:
        pass

    content_type = response.headers.get("content-type")
    final_url = str(response.url)
    mime, ext, kind = resolve_media(final_url, content_type, head)
    name = safe_filename(final_url, response.headers.get("content-disposition"), mime)

    if ext and not name.lower().endswith(ext):
        name = f"{name}{ext}"

    dest = (dest_dir / name).resolve()
    if not dest.is_relative_to(dest_dir.resolve()):
        # sanitize_filename already strips separators; this is belt and braces.
        raise ValueError(f"Unsafe filename derived for {item_id}: {name!r}")

    tmp.replace(dest)

    return FileResult(
        rel_path=str(dest.relative_to(settings.storage_root.resolve())),
        file_name=name,
        mime_type=mime,
        size=written,
        kind=kind,
    )


def find_downloaded_file(item_id: str) -> Path | None:
    """The single artifact in ``files/<item_id>/``, if it exists."""
    d = settings.storage_root / "files" / item_id
    if not d.is_dir():
        return None
    return next((p for p in sorted(d.iterdir()) if p.is_file()), None)
