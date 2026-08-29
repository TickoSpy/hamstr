from unittest.mock import AsyncMock, patch

import pytest

from app.services.downloader import _is_safe_id
from app.services.ingest import dispatch
from app.services.ingest.ids import (
    ARTICLE_ID_PREFIX,
    FILE_ID_PREFIX,
    canonical_url,
    make_item_id,
)
from app.services.ingest.dispatch import expand_url

YT = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


def _ytdlp(entries):
    return patch(
        "app.services.downloader.extract_videos_from_url",
        new=AsyncMock(return_value=entries),
    )


def _probe(route, content_type=None):
    return patch.object(
        dispatch, "probe_route", new=AsyncMock(return_value=(route, content_type))
    )


# --- canonical_url / make_item_id -------------------------------------------


def test_canonical_url_strips_tracking_and_fragment():
    assert (
        canonical_url(
            "HTTPS://Example.COM/a/b/?utm_source=twitter&id=7&fbclid=xyz#section"
        )
        == "https://example.com/a/b?id=7"
    )


def test_canonical_url_is_idempotent():
    once = canonical_url("https://example.com/a/?utm_campaign=x#y")
    assert canonical_url(once) == once


def test_canonical_url_keeps_the_root_slash():
    assert canonical_url("https://example.com/") == "https://example.com/"


def test_canonical_url_drops_default_ports():
    assert canonical_url("https://example.com:443/a") == "https://example.com/a"
    assert canonical_url("http://example.com:80/a") == "http://example.com/a"


def test_make_item_id_is_deterministic_and_dedupes_tracking_params():
    a = make_item_id(ARTICLE_ID_PREFIX, "https://example.com/post?utm_source=rss")
    b = make_item_id(ARTICLE_ID_PREFIX, "https://example.com/post")
    assert a == b


def test_make_item_id_is_a_safe_storage_id():
    for url in ["https://example.com/a b/c?d=é", "https://x.example/../../etc/passwd"]:
        for prefix in (ARTICLE_ID_PREFIX, FILE_ID_PREFIX):
            assert _is_safe_id(make_item_id(prefix, url))


# --- routing ------------------------------------------------------------------


async def test_known_media_host_never_probes():
    entries = [("dQw4w9WgXcQ", YT, "T", "C", 213)]
    with _ytdlp(entries), _probe("article") as probe:
        result = await expand_url(YT)
    probe.assert_not_awaited()
    assert [e.kind for e in result] == ["video"]
    assert result[0].id == "dQw4w9WgXcQ"


async def test_file_extension_routes_without_any_network():
    with _probe("article") as probe:
        result = await expand_url("https://example.com/docs/paper.pdf")
    probe.assert_not_awaited()
    assert len(result) == 1
    assert result[0].kind == "document"
    assert result[0].mime_type == "application/pdf"
    assert result[0].id.startswith(FILE_ID_PREFIX)


async def test_html_content_type_routes_to_article():
    with _probe("article", "text/html; charset=utf-8"):
        result = await expand_url("https://news.example/story")
    assert result[0].kind == "article"
    assert result[0].id.startswith(ARTICLE_ID_PREFIX)
    assert result[0].channel == "news.example"


async def test_probe_result_of_file_routes_to_file():
    with _probe("file", "application/pdf"):
        result = await expand_url("https://example.com/download")
    assert result[0].kind == "document"


async def test_probe_failure_falls_back_to_article():
    with patch.object(
        dispatch, "probe_route", new=AsyncMock(side_effect=TimeoutError("slow"))
    ):
        result = await expand_url("https://unreachable.example/x")
    assert result[0].kind == "article"


async def test_audio_only_always_uses_ytdlp():
    """Even for a URL that would otherwise route to a direct file download."""
    entries = [("s1", "https://example.com/track.mp3", "Track", None, 60)]
    with _ytdlp(entries), _probe("file") as probe:
        result = await expand_url("https://example.com/track.mp3", audio_only=True)
    probe.assert_not_awaited()
    assert result[0].kind == "audio"
    assert result[0].audio_only is True


async def test_explicit_article_mode_beats_the_media_host_heuristic():
    with _probe("file") as probe:
        result = await expand_url(YT, mode="article")
    probe.assert_not_awaited()
    assert result[0].kind == "article"


async def test_explicit_file_mode_beats_the_media_host_heuristic():
    with _probe("article") as probe:
        result = await expand_url(YT, mode="file")
    probe.assert_not_awaited()
    assert result[0].kind in ("file", "video", "document")
    assert result[0].id.startswith(FILE_ID_PREFIX)


async def test_explicit_video_mode_on_a_pdf_url_uses_ytdlp():
    entries = [("x1", "https://example.com/paper.pdf", None, None, None)]
    with _ytdlp(entries):
        result = await expand_url("https://example.com/paper.pdf", mode="video")
    assert result[0].kind == "video"


async def test_archive_host_routes_to_article_without_probing():
    with _probe("file") as probe:
        result = await expand_url("https://archive.ph/newest/https://nyt.com/x")
    probe.assert_not_awaited()
    assert result[0].kind == "article"


async def test_playlist_fans_out():
    entries = [
        ("v1", "https://youtube.com/watch?v=v1", "One", "A", 100),
        ("v2", "https://youtube.com/watch?v=v2", "Two", "A", 200),
    ]
    with _ytdlp(entries):
        result = await expand_url("https://www.youtube.com/playlist?list=PLxxx")
    assert [e.id for e in result] == ["v1", "v2"]


async def test_empty_url_expands_to_nothing():
    assert await expand_url("   ") == []


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://www.youtube.com/watch?v=x", True),
        ("https://youtu.be/x", True),
        ("https://m.youtube.com/watch?v=x", True),
        ("https://news.ycombinator.com/item?id=1", False),
        ("https://notyoutube.com/watch?v=x", False),
        ("https://youtube.com.evil.example/x", False),
    ],
)
def test_is_known_media_host(url, expected):
    assert dispatch.is_known_media_host(url) is expected


# --- handler is independent of kind ------------------------------------------


async def test_a_bare_media_url_is_kind_video_but_handled_as_a_file():
    """Regression: routing the worker on `kind` sent a plain .mp4 URL to yt-dlp,
    which produced a row with no file_name and an mp4 tag on an audio item."""
    with _probe("article") as probe:
        result = await expand_url("https://cdn.example.com/clip.mp4")
    probe.assert_not_awaited()
    assert result[0].kind == "video"
    assert result[0].handler == "file"


async def test_a_bare_mp3_url_is_kind_audio_but_handled_as_a_file():
    result = await expand_url("https://cdn.example.com/song.mp3")
    assert result[0].kind == "audio"
    assert result[0].handler == "file"
    assert result[0].mime_type == "audio/mpeg"


async def test_ytdlp_entries_are_handled_by_ytdlp():
    entries = [("dQw4w9WgXcQ", YT, "T", "C", 213)]
    with _ytdlp(entries):
        result = await expand_url(YT)
    assert result[0].handler == "ytdlp"


async def test_audio_only_is_handled_by_ytdlp_even_for_a_media_url():
    entries = [("s1", "https://example.com/track.mp3", "Track", None, 60)]
    with _ytdlp(entries):
        result = await expand_url("https://example.com/track.mp3", audio_only=True)
    assert result[0].handler == "ytdlp"


async def test_article_entries_are_handled_by_the_article_pipeline():
    with _probe("article", "text/html"):
        result = await expand_url("https://news.example/story")
    assert result[0].handler == "article"


# --- Reddit link shapes ------------------------------------------------------


@pytest.mark.parametrize(
    "url,expected",
    [
        (
            "https://www.reddit.com/r/x/comments/abc/title/",
            "https://old.reddit.com/r/x/comments/abc/title/",
        ),
        (
            "https://reddit.com/r/x/comments/abc/",
            "https://old.reddit.com/r/x/comments/abc/",
        ),
        ("https://new.reddit.com/r/x/", "https://old.reddit.com/r/x/"),
        # Already server-rendered, and unrelated hosts, are left alone.
        ("https://old.reddit.com/r/x/", "https://old.reddit.com/r/x/"),
        ("https://news.example/story", "https://news.example/story"),
    ],
)
def test_readable_url_prefers_the_server_rendered_host(url, expected):
    assert dispatch.readable_url(url) == expected


@pytest.mark.parametrize(
    "url,expected",
    [
        # Share links and short links 30x to a canonical URL.
        ("https://www.reddit.com/r/x/s/AbCdEf123", True),
        ("https://redd.it/abc123", True),
        # A plain permalink goes straight to the reader host.
        ("https://www.reddit.com/r/x/comments/abc/title/", False),
        ("https://www.reddit.com/r/x/", False),
        ("https://news.example/story", False),
    ],
)
def test_needs_redirect_resolution(url, expected):
    assert dispatch.needs_redirect_resolution(url) is expected


def test_share_links_are_resolved_before_the_host_is_rewritten():
    """old.reddit.com bounces /s/ share links to a login page, so the redirect
    has to be followed on www first and only then rewritten."""
    share = "https://www.reddit.com/r/x/s/AbCdEf123"
    assert dispatch.needs_redirect_resolution(share)
    canonical = "https://www.reddit.com/r/x/comments/abc/title/"
    assert dispatch.readable_url(canonical).startswith("https://old.reddit.com/")


async def test_reddit_posts_fall_back_to_archiving_when_ytdlp_finds_nothing():
    with _ytdlp([]):
        result = await expand_url("https://www.reddit.com/r/x/comments/abc/title/")
    assert result[0].kind == "article"
    assert result[0].handler == "article"


async def test_reddit_video_posts_still_go_to_ytdlp():
    entries = [("v1", "https://v.redd.it/xyz", "A clip", "u/someone", 30)]
    with _ytdlp(entries):
        result = await expand_url("https://www.reddit.com/r/videos/comments/abc/clip/")
    assert result[0].kind == "video"
    assert result[0].handler == "ytdlp"


async def test_v_redd_it_is_always_media():
    entries = [("v2", "https://v.redd.it/xyz", None, None, None)]
    with _ytdlp(entries), _probe("article") as probe:
        result = await expand_url("https://v.redd.it/xyz")
    probe.assert_not_awaited()
    assert result[0].handler == "ytdlp"
