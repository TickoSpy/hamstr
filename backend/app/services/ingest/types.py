from dataclasses import dataclass
from typing import Literal

Kind = Literal["video", "audio", "article", "document", "image", "file"]

# Route names used internally by dispatch. "video"/"audio" both mean yt-dlp;
# "media_or_page" means try yt-dlp and archive the page if it finds nothing.
Route = Literal["video", "audio", "article", "file", "media_or_page"]

# Which pipeline runs the item. Distinct from Kind: a bare .mp4 URL is
# kind="video" but handler="file".
Handler = Literal["ytdlp", "file", "article"]


@dataclass(frozen=True)
class IngestEntry:
    """One archivable item, produced at submit time before anything is downloaded."""

    id: str
    url: str
    kind: Kind
    handler: Handler
    title: str | None = None
    channel: str | None = None  # uploader, or site name for articles
    duration: int | None = None
    mime_type: str | None = None
    audio_only: bool = False


class IngestError(RuntimeError):
    """A capture failed in a way worth showing the user verbatim."""


class PaywalledError(IngestError):
    """The page was gated and no archive had a readable copy.

    Distinct from a generic failure so the row can still be flagged `paywalled`
    — otherwise it reads as "paywalled" in the error text while the field says
    False, and the library can't tell the two cases apart.
    """
