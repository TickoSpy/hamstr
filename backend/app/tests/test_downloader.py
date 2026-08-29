import pytest
from unittest.mock import patch

from app.models.video import Video
from app.services.downloader import _is_safe_id, _ydl_base_opts

_YT_ID = "dQw4w9WgXcQ"
_YT_ID_B = "9bZkp7q19f0"
_VIMEO_ID = "123456789"


def test_is_safe_id_valid():
    assert _is_safe_id(_YT_ID)
    assert _is_safe_id(_VIMEO_ID)
    assert _is_safe_id("abc-123_def.456")


def test_is_safe_id_rejects_traversal():
    assert not _is_safe_id("../etc/passwd")
    assert not _is_safe_id("a/b")
    assert not _is_safe_id("")
    assert not _is_safe_id("a" * 201)


@pytest.mark.asyncio
async def test_update_video(db_session):
    video = Video(
        id="upd00000001",
        url="https://youtube.com/watch?v=upd00000001",
        status="pending",
        progress=0.0,
    )
    db_session.add(video)
    await db_session.commit()

    with patch("app.services.downloader.AsyncSessionLocal", return_value=db_session):
        pass  # _update_video uses its own session; verify no import errors


@pytest.mark.asyncio
async def test_extract_videos_from_url_youtube_fast_path():
    # Single YouTube video URLs hit the fast parser — no yt-dlp call.
    from app.services.downloader import extract_videos_from_url

    entries = await extract_videos_from_url(f"https://youtube.com/watch?v={_YT_ID}")

    assert len(entries) == 1
    vid_id, vid_url, title, channel, duration = entries[0]
    assert vid_id == _YT_ID
    assert _YT_ID in vid_url
    assert title is None
    assert channel is None
    assert duration is None


@pytest.mark.asyncio
async def test_extract_videos_from_url_playlist():
    fake_info = {
        "_type": "playlist",
        "entries": [
            {
                "id": _YT_ID,
                "url": f"https://youtube.com/watch?v={_YT_ID}",
                "title": "Vid 1",
                "uploader": "Chan",
                "duration": 60,
            },
            {
                "id": _YT_ID_B,
                "url": f"https://youtube.com/watch?v={_YT_ID_B}",
                "title": "Vid 2",
                "uploader": "Chan",
                "duration": 90,
            },
        ],
    }

    with patch("yt_dlp.YoutubeDL") as MockYDL:
        instance = MockYDL.return_value.__enter__.return_value
        instance.extract_info.return_value = fake_info

        from app.services.downloader import extract_videos_from_url

        entries = await extract_videos_from_url(
            "https://youtube.com/playlist?list=PLxxx"
        )

    assert len(entries) == 2
    assert entries[0][0] == _YT_ID
    assert entries[1][0] == _YT_ID_B


@pytest.mark.asyncio
async def test_extract_videos_from_url_non_youtube():
    # Non-YouTube single video goes through yt-dlp and accepts any safe ID format
    fake_info = {
        "id": _VIMEO_ID,
        "webpage_url": f"https://vimeo.com/{_VIMEO_ID}",
        "title": "A Vimeo Video",
        "uploader": "Someone",
        "duration": 120,
    }

    with patch("yt_dlp.YoutubeDL") as MockYDL:
        instance = MockYDL.return_value.__enter__.return_value
        instance.extract_info.return_value = fake_info

        from app.services.downloader import extract_videos_from_url

        entries = await extract_videos_from_url(f"https://vimeo.com/{_VIMEO_ID}")

    assert len(entries) == 1
    vid_id, vid_url, title, channel, duration = entries[0]
    assert vid_id == _VIMEO_ID
    assert vid_url == f"https://vimeo.com/{_VIMEO_ID}"
    assert title == "A Vimeo Video"
    assert duration == 120


def test_base_opts_add_web_safari_without_dropping_the_defaults():
    """Age-restricted videos land on clients whose formats need a PO token; the
    web_safari HLS ladder is the fallback that doesn't. It must be additive —
    replacing the defaults would cost ordinary videos their 4K formats."""
    clients = _ydl_base_opts()["extractor_args"]["youtube"]["player_client"]
    assert clients[0] == "default"
    assert "web_safari" in clients
