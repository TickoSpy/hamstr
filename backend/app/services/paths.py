"""Storage layout helpers.

Every on-disk artifact lives under ``<storage_root>/<subdir>/<item_id>/``. The list
of subdirs used to be duplicated across main.py, downloader.py and videos.py —
forgetting one leaked files forever, so it lives here now.
"""

import re
import shutil
from pathlib import Path

from app.config import settings

# Every storage subdirectory an item can own. Used for mkdir at startup and for
# purging an item's files on delete/error.
STORAGE_SUBDIRS: tuple[str, ...] = (
    "videos",
    "audio",
    "thumbnails",
    "files",
    "articles",
)

# Safe ID for any item: no path separators, no traversal, reasonable length.
_SAFE_ID_RE = re.compile(r"^[a-zA-Z0-9_.:\-]{1,200}$")


def is_safe_id(item_id: str) -> bool:
    return bool(_SAFE_ID_RE.match(item_id)) and ".." not in item_id


def storage_dir(sub: str, item_id: str) -> Path:
    """Resolve (and create) ``<storage_root>/<sub>/<item_id>``, refusing traversal."""
    if not is_safe_id(item_id):
        raise ValueError(f"Invalid item ID: {item_id!r}")
    root = settings.storage_root.resolve()
    p = (root / sub / item_id).resolve()
    if not p.is_relative_to(root):
        raise ValueError(f"Path traversal detected for item ID: {item_id!r}")
    p.mkdir(parents=True, exist_ok=True)
    return p


def purge_item_dirs(item_id: str) -> None:
    """Remove every on-disk directory belonging to an item. Never raises."""
    if not is_safe_id(item_id):
        return
    root = settings.storage_root.resolve()
    for sub in STORAGE_SUBDIRS:
        d = (root / sub / item_id).resolve()
        if d.is_relative_to(root) and d.exists():
            shutil.rmtree(d, ignore_errors=True)
