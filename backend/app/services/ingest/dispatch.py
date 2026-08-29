"""Decide which handler a submitted URL belongs to.

Ordered cheapest-first: an explicit mode, then zero-network URL heuristics, then
a single HEAD/ranged-GET probe. yt-dlp is only ever invoked on the video route.
"""

import logging
from urllib.parse import urlsplit, urlunsplit

from app.config import settings
from app.services.ingest.http import build_client, probe_head
from app.services.ingest.ids import ARTICLE_ID_PREFIX, FILE_ID_PREFIX, make_item_id
from app.services.ingest.sniff import resolve_media, url_extension
from app.services.ingest.types import IngestEntry, Route

logger = logging.getLogger(__name__)

# Hosts yt-dlp is unambiguously the right tool for. Saves a probe round-trip and
# stops a YouTube watch page from being archived as an article.
MEDIA_HOSTS: frozenset[str] = frozenset(
    {
        "youtube.com",
        "youtu.be",
        "youtube-nocookie.com",
        "vimeo.com",
        "tiktok.com",
        "twitter.com",
        "x.com",
        "instagram.com",
        "v.redd.it",
        "i.redd.it",
        "soundcloud.com",
        "bandcamp.com",
        "twitch.tv",
        "dailymotion.com",
        "odysee.com",
        "rumble.com",
        "bilibili.com",
        "nebula.tv",
        "facebook.com",
        "streamable.com",
    }
)

# Hosts whose pages are genuinely bimodal: the same URL shape is sometimes a
# video and sometimes a text or link post. Try yt-dlp first, then fall back to
# archiving the page — routing them straight to yt-dlp made every non-video
# Reddit post fail outright.
BIMODAL_HOSTS: frozenset[str] = frozenset({"reddit.com", "redd.it"})

# Short/share links that 30x to a canonical URL elsewhere. These must be
# resolved on their *original* host before the rewrite below is applied —
# old.reddit.com doesn't understand Reddit's /s/ share links and bounces them to
# a login page.
REDIRECTING_HOSTS: frozenset[str] = frozenset({"redd.it", "reddit.com"})

# Sites that serve a JS bot-check to plain HTTP clients but keep a
# server-rendered version on another hostname.
READER_HOST_REWRITES: dict[str, str] = {
    "reddit.com": "old.reddit.com",
    "www.reddit.com": "old.reddit.com",
    "new.reddit.com": "old.reddit.com",
    "np.reddit.com": "old.reddit.com",
}

# Already an archive snapshot — capture it as an article and skip the paywall chain.
ARCHIVE_HOSTS: frozenset[str] = frozenset(
    {
        "archive.ph",
        "archive.is",
        "archive.today",
        "archive.md",
        "archive.li",
        "archive.vn",
        "web.archive.org",
        "archive.org",
    }
)

# Extensions that are unambiguously a file to fetch, not a page to render.
FILE_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".pdf",
        ".epub",
        ".txt",
        ".md",
        ".markdown",
        ".csv",
        ".json",
        ".rtf",
        ".doc",
        ".docx",
        ".zip",
        ".jpg",
        ".jpeg",
        ".png",
        ".gif",
        ".webp",
        ".avif",
        ".svg",
        ".bmp",
        ".heic",
        ".heif",
        ".mp3",
        ".m4a",
        ".aac",
        ".flac",
        ".ogg",
        ".oga",
        ".opus",
        ".wav",
        ".mp4",
        ".m4v",
        ".webm",
        ".mkv",
        ".mov",
        ".avi",
    }
)

HTML_TYPES = frozenset(
    {"text/html", "application/xhtml+xml", "application/xml", "text/xml"}
)


def _registrable_host(url: str) -> str:
    try:
        host = (urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host


def _host_matches(host: str, candidates: frozenset[str]) -> bool:
    if not host:
        return False
    if host in candidates:
        return True
    return any(host.endswith("." + c) for c in candidates)


def is_known_media_host(url: str) -> bool:
    return _host_matches(_registrable_host(url), MEDIA_HOSTS)


def is_archive_host(url: str) -> bool:
    return _host_matches(_registrable_host(url), ARCHIVE_HOSTS)


def is_bimodal_host(url: str) -> bool:
    return _host_matches(_registrable_host(url), BIMODAL_HOSTS)


def needs_redirect_resolution(url: str) -> bool:
    """Whether the URL should be followed to its canonical form before fetching."""
    host = (urlsplit(url).hostname or "").lower() if url else ""
    if not host:
        return False
    if _host_matches(host, REDIRECTING_HOSTS):
        # Only share/short links actually redirect; a normal permalink doesn't.
        path = urlsplit(url).path
        return "/s/" in path or host.endswith("redd.it")
    return False


def readable_url(url: str) -> str:
    """The URL to actually fetch when archiving a page.

    Some sites answer a plain HTTP client with a JS verification wall on their
    primary hostname while serving full HTML on an older one (www.reddit.com vs
    old.reddit.com). The original URL is still what gets stored and linked.
    """
    try:
        parts = urlsplit(url)
    except ValueError:
        return url
    host = (parts.hostname or "").lower()
    replacement = READER_HOST_REWRITES.get(host)
    if not replacement:
        return url
    netloc = replacement + (f":{parts.port}" if parts.port else "")
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


def ext_route(url: str) -> Route | None:
    """Route implied by the URL's file extension, if any."""
    return "file" if url_extension(url) in FILE_EXTENSIONS else None


async def probe_route(url: str, *, timeout: float = 5.0) -> tuple[Route, str | None]:
    """One network round-trip to classify a URL. Returns (route, content_type).

    Anything HTML-ish is an article; everything else is a file. On failure we
    default to the article route, which is retryable and still saves raw.html.
    """
    async with build_client(timeout=timeout) as client:
        status, content_type, head = await probe_head(client, url, timeout=timeout)

    declared = (content_type or "").split(";", 1)[0].strip().lower()

    if declared in HTML_TYPES or not declared:
        return "article", content_type

    mime, _, _ = resolve_media(url, content_type, head)
    if mime in HTML_TYPES:
        return "article", content_type

    logger.debug("Probe of %s -> %s (%s)", url, mime, status)
    return "file", content_type


async def _route_for(
    url: str, *, mode: str, audio_only: bool
) -> tuple[Route, str | None]:
    if audio_only:
        return "audio", None
    if mode == "video":
        return "video", None
    if mode == "audio":
        return "audio", None
    if mode == "article":
        return "article", None
    if mode == "file":
        return "file", None

    if is_known_media_host(url):
        return "video", None
    if is_bimodal_host(url):
        return "media_or_page", None
    if is_archive_host(url):
        return "article", None

    by_ext = ext_route(url)
    if by_ext:
        return by_ext, None

    try:
        return await probe_route(url)
    except Exception as exc:
        logger.info("Probe failed for %s (%s) — treating as an article", url, exc)
        return "article", None


async def expand_url(
    url: str, *, audio_only: bool = False, mode: str = "auto"
) -> list[IngestEntry]:
    """Expand a submitted URL into the items it should produce.

    Video/audio routes fan a playlist out into many entries; the file and article
    routes always produce exactly one.
    """
    url = url.strip()
    if not url:
        return []

    # Imported lazily: downloader -> tagging -> ingest.sniff would otherwise close
    # an import loop back to this module.
    from app.services.downloader import extract_videos_from_url

    route, content_type = await _route_for(url, mode=mode, audio_only=audio_only)

    if route == "media_or_page":
        # Bimodal host: a video post goes to yt-dlp, anything else is archived.
        try:
            entries = await extract_videos_from_url(url)
        except Exception as exc:
            logger.info(
                "yt-dlp found no media at %s (%s) — archiving the page", url, exc
            )
            entries = []
        if entries:
            return [
                IngestEntry(
                    id=vid,
                    url=vurl,
                    kind="video",
                    handler="ytdlp",
                    title=title,
                    channel=channel,
                    duration=duration,
                )
                for vid, vurl, title, channel, duration in entries
            ]
        route = "article"

    if route in ("video", "audio"):
        want_audio = route == "audio"
        entries = await extract_videos_from_url(url)
        return [
            IngestEntry(
                id=vid,
                url=vurl,
                kind="audio" if want_audio else "video",
                handler="ytdlp",
                title=title,
                channel=channel,
                duration=duration,
                audio_only=want_audio,
            )
            for vid, vurl, title, channel, duration in entries
        ]

    if route == "file":
        mime, ext, kind = resolve_media(url, content_type, None)
        return [
            IngestEntry(
                id=make_item_id(FILE_ID_PREFIX, url),
                url=url,
                kind=kind,
                handler="file",
                mime_type=mime,
            )
        ]

    # Article route. An HTML page can still be handed to yt-dlp first when the
    # operator prefers extracting an embedded video over archiving the page.
    if settings.ingest_try_ytdlp_on_html:
        try:
            entries = await extract_videos_from_url(url)
            if entries:
                return [
                    IngestEntry(
                        id=vid,
                        url=vurl,
                        kind="video",
                        handler="ytdlp",
                        title=title,
                        channel=channel,
                        duration=duration,
                    )
                    for vid, vurl, title, channel, duration in entries
                ]
        except Exception as exc:
            logger.debug("yt-dlp declined %s (%s) — archiving the page", url, exc)

    return [
        IngestEntry(
            id=make_item_id(ARTICLE_ID_PREFIX, url),
            url=url,
            kind="article",
            handler="article",
            channel=_registrable_host(url) or None,
            mime_type="text/html",
        )
    ]
