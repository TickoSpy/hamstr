"""Image downscaling, via the ffmpeg binary the image already ships.

Thumbnails used to be the original file — a 1 MB GIF served into a 300px grid
tile. ffmpeg is already a hard dependency for video, so resizing needs no new
Python package and no libjpeg/zlib headers in the build.
"""

import asyncio
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Grid tiles render around 300px wide; 480 covers a 1.5x display.
THUMBNAIL_MAX_WIDTH = 480
# Article images render at roughly 680px; 1600 keeps the lightbox sharp.
ASSET_MAX_WIDTH = 1600

_TIMEOUT_SECONDS = 30


async def _run_ffmpeg(args: list[str]) -> bool:
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            *args,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=_TIMEOUT_SECONDS)
    except (TimeoutError, asyncio.TimeoutError):
        logger.warning("ffmpeg timed out: %s", " ".join(args[:4]))
        return False
    except Exception as exc:
        logger.warning("ffmpeg failed to start: %s", exc)
        return False

    if proc.returncode != 0:
        logger.debug("ffmpeg error: %s", (stderr or b"").decode(errors="replace")[:300])
        return False
    return True


async def downscale(src: Path, dest: Path, max_width: int, quality: int = 4) -> bool:
    """Write a width-capped JPEG copy of `src`. Returns False if it couldn't.

    Only the first frame of an animated source is taken — a thumbnail doesn't
    need to animate, and an animated GIF is exactly the case that was costing a
    megabyte per grid tile.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    ok = await _run_ffmpeg(
        [
            "-i",
            str(src),
            "-frames:v",
            "1",
            # Never upscale: min() keeps a small original at its own size.
            "-vf",
            f"scale='min({max_width},iw)':-2:flags=lanczos",
            "-q:v",
            str(quality),
            str(dest),
        ]
    )
    if not ok:
        dest.unlink(missing_ok=True)
    return ok and dest.exists() and dest.stat().st_size > 0


async def make_thumbnail(src: Path, dest_dir: Path) -> Path | None:
    """Build a grid-sized thumbnail for an image file."""
    dest = dest_dir / "thumb.jpg"
    if await downscale(src, dest, THUMBNAIL_MAX_WIDTH):
        return dest
    return None


async def shrink_if_oversized(path: Path, max_width: int = ASSET_MAX_WIDTH) -> None:
    """Replace an image in place with a width-capped copy, when it's worth it.

    Left alone if ffmpeg fails or the result isn't actually smaller, so a
    failure here can never lose the original.
    """
    temp = path.with_name(path.stem + ".scaled.jpg")
    if not await downscale(path, temp, max_width):
        temp.unlink(missing_ok=True)
        return

    try:
        if temp.stat().st_size < path.stat().st_size:
            temp.replace(path)
        else:
            temp.unlink(missing_ok=True)
    except OSError:
        temp.unlink(missing_ok=True)
