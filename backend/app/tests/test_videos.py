import pytest
from unittest.mock import AsyncMock, patch

from app.models.video import Video
from app.services.ingest.types import IngestEntry


def _entry(
    vid, url, title=None, channel=None, duration=None, kind="video", handler="ytdlp"
):
    return IngestEntry(
        id=vid,
        url=url,
        kind=kind,
        handler=handler,
        title=title,
        channel=channel,
        duration=duration,
    )


@pytest.mark.asyncio
async def test_health(client):
    r = await client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_list_videos_empty(client):
    r = await client.get("/api/videos")
    assert r.status_code == 200
    data = r.json()
    assert data["items"] == []
    assert data["total"] == 0


@pytest.mark.asyncio
async def test_submit_video(client, db_session):
    fake_entries = [
        _entry(
            "abc123",
            "https://youtube.com/watch?v=abc123",
            "Test Title",
            "Test Channel",
            120,
        )
    ]
    with patch(
        "app.routers.videos.expand_url",
        new=AsyncMock(return_value=fake_entries),
    ):
        r = await client.post(
            "/api/videos", json={"urls": ["https://youtube.com/watch?v=abc123"]}
        )
    assert r.status_code == 202
    data = r.json()
    assert len(data["submitted"]) == 1
    assert data["submitted"][0]["id"] == "abc123"
    assert data["skipped"] == []


@pytest.mark.asyncio
async def test_submit_duplicate(client, db_session):
    video = Video(
        id="dup001",
        url="https://youtube.com/watch?v=dup001",
        status="completed",
        progress=100.0,
    )
    db_session.add(video)
    await db_session.commit()

    fake_entries = [
        _entry(
            "dup001", "https://youtube.com/watch?v=dup001", "Dup Title", "Channel", 60
        )
    ]
    with patch(
        "app.routers.videos.expand_url",
        new=AsyncMock(return_value=fake_entries),
    ):
        r = await client.post(
            "/api/videos", json={"urls": ["https://youtube.com/watch?v=dup001"]}
        )
    assert r.status_code == 202
    data = r.json()
    assert data["submitted"] == []
    assert len(data["skipped"]) == 1


@pytest.mark.asyncio
async def test_submit_playlist(client):
    fake_entries = [
        _entry(
            "vid001", "https://youtube.com/watch?v=vid001", "Track 1", "Artist", 200
        ),
        _entry(
            "vid002", "https://youtube.com/watch?v=vid002", "Track 2", "Artist", 180
        ),
    ]
    with patch(
        "app.routers.videos.expand_url",
        new=AsyncMock(return_value=fake_entries),
    ):
        r = await client.post(
            "/api/videos", json={"urls": ["https://youtube.com/playlist?list=PLxxx"]}
        )
    assert r.status_code == 202
    data = r.json()
    assert len(data["submitted"]) == 2
    assert {v["id"] for v in data["submitted"]} == {"vid001", "vid002"}


@pytest.mark.asyncio
async def test_clear_queue(client, db_session):
    # A finished Library video plus one of every queue status.
    db_session.add_all(
        [
            Video(id="keep01", url="u", status="completed", progress=100.0),
            Video(id="q_pending", url="u", status="pending", progress=0.0),
            Video(id="q_downloading", url="u", status="downloading", progress=42.0),
            Video(id="q_processing", url="u", status="processing", progress=100.0),
            Video(id="q_error", url="u", status="error", progress=0.0),
        ]
    )
    await db_session.commit()

    r = await client.delete("/api/videos/queue")
    assert r.status_code == 200
    assert r.json()["deleted"] == 4

    # Completed video survives; queue is empty.
    r = await client.get("/api/videos?status=completed")
    assert {v["id"] for v in r.json()["items"]} == {"keep01"}
    r = await client.get("/api/videos?status=pending,downloading,processing,error")
    assert r.json()["total"] == 0

    # Idempotent: nothing left to delete.
    r = await client.delete("/api/videos/queue")
    assert r.json()["deleted"] == 0


@pytest.mark.asyncio
async def test_get_video_not_found(client):
    r = await client.get("/api/videos/nonexistent")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_add_and_remove_tag(client, db_session):
    video = Video(
        id="tag001",
        url="https://youtube.com/watch?v=tag001",
        status="completed",
        progress=100.0,
    )
    db_session.add(video)
    await db_session.commit()

    r = await client.post("/api/videos/tag001/tags", json={"name": "Music"})
    assert r.status_code == 201
    assert "music" in r.json()

    r = await client.post("/api/videos/tag001/tags", json={"name": "music"})
    assert r.status_code == 409

    r = await client.delete("/api/videos/tag001/tags/music")
    assert r.status_code == 204

    r = await client.get("/api/videos/tag001/tags")
    assert r.json() == []


@pytest.mark.asyncio
async def test_list_tags(client, db_session):
    video = Video(
        id="tags002",
        url="https://youtube.com/watch?v=tags002",
        status="completed",
        progress=100.0,
    )
    db_session.add(video)
    await db_session.commit()
    await client.post("/api/videos/tags002/tags", json={"name": "ai"})
    await client.post("/api/videos/tags002/tags", json={"name": "interesting"})

    r = await client.get("/api/tags")
    assert r.status_code == 200
    tags = r.json()
    assert "ai" in tags
    assert "interesting" in tags


@pytest.mark.asyncio
async def test_list_videos_filter_by_tag(client, db_session):
    video = Video(
        id="filter01",
        url="https://youtube.com/watch?v=filter01",
        status="completed",
        progress=100.0,
    )
    db_session.add(video)
    await db_session.commit()
    await client.post("/api/videos/filter01/tags", json={"name": "unique-tag-xyz"})

    r = await client.get("/api/videos?tag=unique-tag-xyz")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] >= 1
    assert any(v["id"] == "filter01" for v in data["items"])


@pytest.mark.asyncio
async def test_list_videos_filter_by_kind(client, db_session):
    db_session.add_all(
        [
            Video(
                id="k_vid", url="u", status="completed", progress=100.0, kind="video"
            ),
            Video(
                id="k_art", url="u", status="completed", progress=100.0, kind="article"
            ),
            Video(
                id="k_doc", url="u", status="completed", progress=100.0, kind="document"
            ),
        ]
    )
    await db_session.commit()

    r = await client.get("/api/videos?kind=article")
    assert {v["id"] for v in r.json()["items"]} == {"k_art"}

    # Comma-separated kinds are OR'd — this is how the "Text" facet works.
    r = await client.get("/api/videos?kind=article,document")
    assert {v["id"] for v in r.json()["items"]} == {"k_art", "k_doc"}

    r = await client.get("/api/videos")
    assert {v["id"] for v in r.json()["items"]} == {"k_vid", "k_art", "k_doc"}


@pytest.mark.asyncio
async def test_kind_counts(client, db_session):
    db_session.add_all(
        [
            Video(id="c1", url="u", status="completed", progress=100.0, kind="video"),
            Video(id="c2", url="u", status="completed", progress=100.0, kind="video"),
            Video(id="c3", url="u", status="completed", progress=100.0, kind="article"),
            # Not completed — excluded from the facet counts.
            Video(id="c4", url="u", status="pending", progress=0.0, kind="article"),
        ]
    )
    await db_session.commit()

    r = await client.get("/api/videos/kinds")
    assert r.status_code == 200
    assert r.json() == {"video": 2, "article": 1}


@pytest.mark.asyncio
async def test_new_fields_round_trip(client, db_session):
    db_session.add(
        Video(
            id="dl_abc",
            url="https://example.com/paper.pdf",
            status="completed",
            progress=100.0,
            kind="document",
            file_path="files/dl_abc/paper.pdf",
            file_name="paper.pdf",
            mime_type="application/pdf",
            source_domain="example.com",
            byline="A. Author",
            published_at="2024-03",
            word_count=1200,
            excerpt="A summary.",
            capture_source="direct",
            paywalled=True,
            extra='{"assets": ["a.jpg"]}',
        )
    )
    await db_session.commit()

    r = await client.get("/api/videos/dl_abc")
    assert r.status_code == 200
    v = r.json()
    assert v["kind"] == "document"
    assert v["file_name"] == "paper.pdf"
    assert v["published_at"] == "2024-03"
    assert v["paywalled"] is True
    # `extra` is stored as a JSON string and surfaced as an object.
    assert v["extra"] == {"assets": ["a.jpg"]}


@pytest.mark.asyncio
async def test_tags_for_item_uses_the_artifact_not_the_source_url():
    """Regression: an audio-only yt-dlp row has no file_name, no video_path and a
    YouTube watch URL with no extension — it was tagged ['audio', 'unknown']."""
    from app.services.tagging import tags_for_item

    audio_row = Video(
        id="aud1",
        url="https://www.youtube.com/watch?v=abcdefghijk",
        status="completed",
        progress=100.0,
        kind="audio",
        audio_only=True,
        audio_mp3_path="audio/aud1/audio.mp3",
        audio_ogg_path="audio/aud1/audio.ogg",
    )
    assert tags_for_item(audio_row) == ["audio", "mp3"]

    video_row = Video(
        id="vid1",
        url="https://www.youtube.com/watch?v=abcdefghijk",
        status="completed",
        progress=100.0,
        kind="video",
        video_path="videos/vid1/video.mp4",
    )
    assert tags_for_item(video_row) == ["video", "mp4"]

    # Nothing on disk to go on: category only, never a junk "unknown" tag.
    bare_row = Video(
        id="bare1",
        url="https://www.youtube.com/watch?v=abcdefghijk",
        status="completed",
        progress=100.0,
        kind="video",
    )
    assert tags_for_item(bare_row) == ["video"]


# --- browser-extension captures ----------------------------------------------


def _captured_page(body_words: int = 200) -> str:
    prose = " ".join(
        f"Sentence {i} of a page that only exists after JavaScript has run."
        for i in range(1, body_words)
    )
    return f"<!DOCTYPE html><html><head><title>Captured</title></head><body><article><p>{prose}</p></article></body></html>"


@pytest.mark.asyncio
async def test_capture_creates_a_pending_article(client, db_session, storage_root):
    r = await client.post(
        "/api/videos/capture",
        json={
            "url": "https://paywalled.example/story",
            "title": "Captured",
            "html": _captured_page(),
        },
    )
    assert r.status_code == 202
    item_id = r.json()["id"]
    assert item_id.startswith("web_")

    row = await db_session.get(Video, item_id)
    assert row is not None
    assert (row.kind, row.handler, row.status) == ("article", "article", "pending")
    assert row.source_domain == "paywalled.example"

    # The HTML is parked for the worker rather than fetched later.
    parked = storage_root / "articles" / item_id / "captured.html"
    assert parked.exists()
    assert "only exists after JavaScript" in parked.read_text()


@pytest.mark.asyncio
async def test_recapturing_replaces_a_completed_item(client, db_session, storage_root):
    url = "https://paywalled.example/refresh-me"
    first = await client.post(
        "/api/videos/capture", json={"url": url, "html": _captured_page()}
    )
    item_id = first.json()["id"]

    row = await db_session.get(Video, item_id)
    row.status = "completed"
    row.word_count = 10
    await db_session.commit()

    second = await client.post(
        "/api/videos/capture", json={"url": url, "html": _captured_page(300)}
    )
    assert second.status_code == 202
    assert second.json()["id"] == item_id

    refreshed = await db_session.get(Video, item_id)
    assert refreshed.status == "pending"


@pytest.mark.asyncio
async def test_capture_rejects_a_non_public_url(client, storage_root):
    r = await client.post(
        "/api/videos/capture",
        json={"url": "http://127.0.0.1/admin", "html": _captured_page()},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_capture_id_matches_a_normal_submission_of_the_same_url(
    client, db_session, storage_root
):
    """So a captured page updates the existing item instead of duplicating it."""
    from app.services.ingest.ids import ARTICLE_ID_PREFIX, make_item_id

    url = "https://paywalled.example/same"
    r = await client.post(
        "/api/videos/capture", json={"url": url, "html": _captured_page()}
    )
    assert r.json()["id"] == make_item_id(ARTICLE_ID_PREFIX, url)


@pytest.mark.asyncio
async def test_capture_records_an_archive_mirror(client, db_session, storage_root):
    r = await client.post(
        "/api/videos/capture",
        json={
            "url": "https://paywalled.example/gated",
            "html": _captured_page(),
            "archive_url": "https://archive.ph/newest/https://paywalled.example/gated",
        },
    )
    assert r.status_code == 202
    item_id = r.json()["id"]
    sidecar = storage_root / "articles" / item_id / "captured.source"
    assert sidecar.exists()
    assert sidecar.read_text().startswith("https://archive.ph/")
