"""Ingest handlers: routing a submitted URL to yt-dlp, a file download, or a
reader-view capture.

Deliberately does not re-export `dispatch` — dispatch depends on `downloader`,
which depends on `tagging`, which depends on `ingest.sniff`. Importing dispatch
here would close that loop at package-import time. Import it directly:

    from app.services.ingest.dispatch import expand_url
"""

from app.services.ingest.types import IngestEntry, IngestError, Kind

__all__ = ["IngestEntry", "IngestError", "Kind"]
