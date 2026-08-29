import pytest

from app.models.video import Video


@pytest.fixture
async def pdf_item(db_session, storage_root):
    d = storage_root / "files" / "dl_stream1"
    d.mkdir(parents=True, exist_ok=True)
    (d / "paper.pdf").write_bytes(b"%PDF-1.7\n" + b"x" * 64)

    db_session.add(
        Video(
            id="dl_stream1",
            url="https://example.com/paper.pdf",
            status="completed",
            progress=100.0,
            kind="document",
            file_path="files/dl_stream1/paper.pdf",
            file_name="paper.pdf",
            mime_type="application/pdf",
        )
    )
    await db_session.commit()
    return "dl_stream1"


async def test_stream_file_serves_inline_with_the_right_type(client, pdf_item):
    r = await client.get(f"/stream/{pdf_item}/file")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["content-disposition"].startswith("inline")
    assert r.content.startswith(b"%PDF")


async def test_stream_file_download_flag_sets_attachment(client, pdf_item):
    r = await client.get(f"/stream/{pdf_item}/file?download=1")
    assert r.status_code == 200
    disposition = r.headers["content-disposition"]
    assert disposition.startswith("attachment")
    assert 'filename="paper.pdf"' in disposition
    assert "filename*=UTF-8''paper.pdf" in disposition


async def test_stream_file_404s_when_the_item_has_no_file(client, db_session):
    db_session.add(
        Video(id="nofile", url="u", status="completed", progress=100.0, kind="video")
    )
    await db_session.commit()

    r = await client.get("/stream/nofile/file")
    assert r.status_code == 404


async def test_stream_file_409s_while_still_downloading(client, db_session):
    db_session.add(
        Video(
            id="pending1",
            url="u",
            status="downloading",
            progress=10.0,
            kind="document",
            file_path="files/pending1/x.pdf",
        )
    )
    await db_session.commit()

    r = await client.get("/stream/pending1/file")
    assert r.status_code == 409


async def test_stream_file_refuses_a_path_outside_storage(
    client, db_session, storage_root
):
    """file_path is written by the backend, but a traversal must still not serve."""
    db_session.add(
        Video(
            id="escape1",
            url="u",
            status="completed",
            progress=100.0,
            kind="document",
            file_path="../../../etc/passwd",
            mime_type="text/plain",
        )
    )
    await db_session.commit()

    r = await client.get("/stream/escape1/file")
    assert r.status_code in (403, 404)


async def test_html_responses_carry_the_inert_csp(client, db_session, storage_root):
    d = storage_root / "files" / "dl_html"
    d.mkdir(parents=True, exist_ok=True)
    (d / "page.html").write_text("<p>hi</p>")

    db_session.add(
        Video(
            id="dl_html",
            url="https://example.com/page.html",
            status="completed",
            progress=100.0,
            kind="document",
            file_path="files/dl_html/page.html",
            file_name="page.html",
            mime_type="text/html",
        )
    )
    await db_session.commit()

    r = await client.get("/stream/dl_html/file")
    assert r.status_code == 200
    csp = r.headers["content-security-policy"]
    assert "default-src 'none'" in csp
    assert "sandbox" in csp
