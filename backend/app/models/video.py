from datetime import datetime, timezone

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Tag(Base):
    __tablename__ = "tags"
    __table_args__ = (UniqueConstraint("video_id", "name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    video_id: Mapped[str] = mapped_column(
        Text, ForeignKey("videos.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)

    video: Mapped["Video"] = relationship("Video", back_populates="tags")


class Video(Base):
    __tablename__ = "videos"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    channel: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    file_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    thumbnail_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    video_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    audio_mp3_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    audio_ogg_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    progress: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    codec: Mapped[str | None] = mapped_column(Text, nullable=True)
    audio_only: Mapped[bool] = mapped_column(
        Integer, nullable=False, default=False, server_default=text("0")
    )

    # --- Archive fields -------------------------------------------------
    # kind is the discriminator: video | audio | article | document | image | file
    # server_default keeps a freshly create_all()'d table identical to one built
    # up by the ALTER statements in main.MIGRATIONS.
    kind: Mapped[str] = mapped_column(
        Text, nullable=False, default="video", server_default=text("'video'")
    )
    # Which pipeline produced (or will produce) this item: ytdlp | file | article.
    # Distinct from `kind` on purpose — a bare .mp4 URL is kind="video" but is
    # fetched by the file downloader, not by yt-dlp.
    handler: Mapped[str] = mapped_column(
        Text, nullable=False, default="ytdlp", server_default=text("'ytdlp'")
    )
    # Generic primary artifact (relative to storage_root) for non-video kinds.
    file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    mime_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_domain: Mapped[str | None] = mapped_column(Text, nullable=True)
    byline: Mapped[str | None] = mapped_column(Text, nullable=True)
    # ISO-8601 string, not DateTime: extracted dates are frequently partial ("2019-04").
    published_at: Mapped[str | None] = mapped_column(Text, nullable=True)
    word_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    article_html_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_html_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    # direct | archive.today | wayback
    capture_source: Mapped[str | None] = mapped_column(Text, nullable=True)
    capture_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    paywalled: Mapped[bool] = mapped_column(
        Integer, nullable=False, default=False, server_default=text("0")
    )
    # JSON blob: {"assets": [...], "mirrors_tried": [...]}
    extra: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, onupdate=_now
    )

    tags: Mapped[list[Tag]] = relationship(
        "Tag",
        back_populates="video",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class Playlist(Base):
    __tablename__ = "playlists"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )

    items: Mapped[list["PlaylistItem"]] = relationship(
        "PlaylistItem",
        back_populates="playlist",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="PlaylistItem.position",
    )


class PlaylistItem(Base):
    __tablename__ = "playlist_items"
    __table_args__ = (UniqueConstraint("playlist_id", "video_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    playlist_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("playlists.id", ondelete="CASCADE"), nullable=False
    )
    video_id: Mapped[str] = mapped_column(
        Text, ForeignKey("videos.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    playlist: Mapped["Playlist"] = relationship("Playlist", back_populates="items")
    video: Mapped[Video] = relationship("Video", lazy="selectin")


# The table is still called `videos` (SQLite can't rename cheaply), but it now
# holds every archived kind. Prefer this alias in new code.
Item = Video
