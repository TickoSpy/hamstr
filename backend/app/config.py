from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    storage_root: Path = Path("storage")
    database_url: str = "sqlite+aiosqlite:///storage/hamstr.db"
    download_workers: int = 1
    max_concurrent_ffmpeg: int = 2
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]
    # Matches any origin, so the browser extension can post a capture from the
    # page being read. Set to None to restrict the API to `cors_origins`.
    cors_origin_regex: str | None = ".*"
    # Manual override for the cookie jar handed to yt-dlp. Normally unset: the
    # app maintains <storage_root>/cookies/merged.txt from the logins added
    # through the UI. Set this only to keep a hand-exported file in charge.
    yt_cookies_file: Path | None = None
    # Gates the site-login routes (/api/cookies/*), which hold live sessions.
    # Unset disables them entirely — they never fall back to being open.
    admin_token: str | None = None
    log_level: str = "info"

    # --- Archive ingest --------------------------------------------------
    max_article_bytes: int = 10 * 1024 * 1024
    max_article_images: int = 40
    max_article_image_bytes: int = 4 * 1024 * 1024
    max_article_assets_bytes: int = 40 * 1024 * 1024
    max_file_bytes: int = 2 * 1024 * 1024 * 1024
    fetch_timeout_seconds: float = 20.0
    article_capture_timeout: int = 120
    archive_enabled: bool = True
    archive_today_hosts: list[str] = [
        "archive.ph",
        "archive.is",
        "archive.today",
        "archive.md",
    ]
    ingest_user_agent: str = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    )
    # When True, HTML pages are handed to yt-dlp (generic extractor) before
    # falling back to article capture. Slow; off by default.
    ingest_try_ytdlp_on_html: bool = False

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
