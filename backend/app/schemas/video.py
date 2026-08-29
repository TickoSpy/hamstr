import json
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.services.urlsafety import is_safe_url as _is_safe_url


class TagSchema(BaseModel):
    id: int
    name: str

    model_config = {"from_attributes": True}


class VideoSchema(BaseModel):
    id: str
    url: str
    title: str | None
    channel: str | None
    duration_seconds: float | None
    file_size_bytes: int | None
    thumbnail_path: str | None
    video_path: str | None
    audio_mp3_path: str | None
    audio_ogg_path: str | None
    status: str
    progress: float
    error_message: str | None
    codec: str | None
    audio_only: bool
    created_at: datetime
    updated_at: datetime
    tags: list[TagSchema] = []

    # Archive fields — present on every row, only meaningful for some kinds.
    kind: str = "video"
    handler: str = "ytdlp"
    file_path: str | None = None
    mime_type: str | None = None
    file_name: str | None = None
    source_domain: str | None = None
    byline: str | None = None
    published_at: str | None = None
    word_count: int | None = None
    excerpt: str | None = None
    article_html_path: str | None = None
    raw_html_path: str | None = None
    capture_source: str | None = None
    capture_url: str | None = None
    paywalled: bool = False
    extra: dict | None = None

    @field_validator("extra", mode="before")
    @classmethod
    def _parse_extra(cls, v: object) -> object:
        if isinstance(v, str):
            try:
                return json.loads(v)
            except ValueError:
                return None
        return v

    model_config = {"from_attributes": True}


IngestMode = Literal["auto", "video", "audio", "article", "file"]


class SubmitRequest(BaseModel):
    urls: list[str] | str = Field(max_length=500)
    audio_only: bool = False
    mode: IngestMode = "auto"

    @field_validator("urls", mode="before")
    @classmethod
    def coerce_and_validate_urls(cls, v: object) -> list[str]:
        # Accept a bare string so iOS Shortcuts (which has no Array field type)
        # can send {"urls": "https://..."} instead of {"urls": ["https://..."]}
        if isinstance(v, str):
            v = [v]
        urls = list(v)  # type: ignore[arg-type]
        for url in urls:
            url = url.strip()
            if len(url) > 2000:
                raise ValueError("URL exceeds maximum length")
            if not _is_safe_url(url):
                raise ValueError("Only public HTTP/HTTPS URLs are accepted")
        return urls


class CaptureRequest(BaseModel):
    """A page captured by the browser extension, HTML included.

    The browser has already run the page's JavaScript, passed whatever bot check
    it has, and is using the reader's own logged-in session — so this arrives as
    content we could never fetch server-side.
    """

    url: str = Field(max_length=2000)
    html: str = Field(max_length=20_000_000)
    title: str | None = Field(default=None, max_length=500)
    # Set when the browser fetched this from an archive mirror on our behalf,
    # because archive.today CAPTCHAs the server but answers a real browser.
    archive_url: str | None = Field(default=None, max_length=2000)

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        v = v.strip()
        if not _is_safe_url(v):
            raise ValueError("Only public HTTP/HTTPS URLs are accepted")
        return v


class SubmittedItem(BaseModel):
    id: str
    url: str
    status: str


class SubmitResponse(BaseModel):
    submitted: list[SubmittedItem]
    skipped: list[SubmittedItem]


class TagRequest(BaseModel):
    name: str = Field(min_length=1, max_length=50)


class VideoListResponse(BaseModel):
    items: list[VideoSchema]
    total: int


class PlaylistItemSchema(BaseModel):
    id: int
    video_id: str
    position: int
    video: VideoSchema

    model_config = {"from_attributes": True}


class PlaylistSchema(BaseModel):
    id: int
    name: str
    created_at: datetime
    items: list[PlaylistItemSchema] = []

    model_config = {"from_attributes": True}


class PlaylistSummary(BaseModel):
    id: int
    name: str
    created_at: datetime
    item_count: int

    model_config = {"from_attributes": True}


class PlaylistCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class PlaylistAddItemRequest(BaseModel):
    video_id: str
