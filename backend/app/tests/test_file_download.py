import httpx
import pytest
import respx

from app.config import settings
from app.services.ingest.file import download_file
from app.services.ingest.http import (
    ContentTooLarge,
    TooManyRedirects,
    describe_http_error,
)
from app.services.ingest.types import IngestError
from app.services.ingest.sniff import resolve_media, safe_filename, sniff_magic
from app.services.urlsafety import UnsafeUrlError

PDF_BYTES = b"%PDF-1.7\n" + b"x" * 4096
GIF_BYTES = b"GIF89a" + b"\x00" * 512
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 512


@pytest.fixture(autouse=True)
def _allow_dns(monkeypatch):
    """Every test URL here is fictional; pretend it resolves publicly."""

    async def _fake(host: str, port: int) -> list:
        return [(2, 1, 6, "", ("93.184.216.34", port))]

    monkeypatch.setattr("app.services.urlsafety._getaddrinfo", _fake)


# --- magic bytes -------------------------------------------------------------


@pytest.mark.parametrize(
    "head,expected",
    [
        (PDF_BYTES, "application/pdf"),
        (GIF_BYTES, "image/gif"),
        (PNG_BYTES, "image/png"),
        (b"\xff\xd8\xff\xe0", "image/jpeg"),
        (b"RIFF\x00\x00\x00\x00WEBPVP8 ", "image/webp"),
        (b"ID3\x03\x00", "audio/mpeg"),
        (b"OggS\x00\x02", "audio/ogg"),
        (b"fLaC\x00", "audio/flac"),
        (b"\x00\x00\x00\x20ftypisom", "video/mp4"),
        (b"\x00\x00\x00\x20ftypavif", "image/avif"),
        (b"<!DOCTYPE html><html>", "text/html"),
        (b"", None),
        (b"nothing recognisable", None),
    ],
)
def test_sniff_magic(head, expected):
    assert sniff_magic(head) == expected


def test_magic_bytes_beat_a_lying_content_type():
    mime, ext, kind = resolve_media(
        "https://example.com/thing", "application/octet-stream", PDF_BYTES
    )
    assert (mime, kind) == ("application/pdf", "document")
    assert ext == ".pdf"


def test_content_type_is_used_when_there_are_no_magic_bytes():
    mime, _, kind = resolve_media("https://example.com/x", "image/gif", None)
    assert (mime, kind) == ("image/gif", "image")


def test_url_extension_is_the_last_resort():
    mime, _, kind = resolve_media("https://example.com/a.mp3", None, None)
    assert (mime, kind) == ("audio/mpeg", "audio")


# --- filenames ---------------------------------------------------------------


@pytest.mark.parametrize(
    "url,disposition,expected",
    [
        ("https://x.example/a/report.pdf", None, "report.pdf"),
        # No extension on the name: one is added from the Content-Type.
        ("https://x.example/../../etc/passwd", None, "passwd.pdf"),
        ("https://x.example/a%20b.pdf", None, "a_b.pdf"),
        ("https://x.example/d", 'attachment; filename="my file.pdf"', "my_file.pdf"),
        (
            "https://x.example/d",
            "attachment; filename*=UTF-8''r%C3%A9sum%C3%A9.pdf",
            "resume.pdf",
        ),
        ("https://x.example/", None, "download.pdf"),
    ],
)
def test_safe_filename(url, disposition, expected):
    assert safe_filename(url, disposition, "application/pdf") == expected


def test_safe_filename_never_escapes_its_directory():
    for hostile in [
        'attachment; filename="../../../etc/shadow"',
        'attachment; filename="/etc/shadow"',
        'attachment; filename="..\\..\\win.ini"',
    ]:
        name = safe_filename("https://x.example/d", hostile, "application/pdf")
        assert "/" not in name and "\\" not in name
        assert not name.startswith(".")


def test_safe_filename_truncates_absurd_names():
    long = "a" * 300 + ".pdf"
    name = safe_filename(f"https://x.example/{long}", None, "application/pdf")
    assert len(name) <= 121
    assert name.endswith(".pdf")


def test_safe_filename_adds_a_missing_extension():
    assert safe_filename("https://x.example/report", None, "application/pdf") == (
        "report.pdf"
    )


# --- downloads ---------------------------------------------------------------


@respx.mock
async def test_download_file_writes_a_pdf(storage_root):
    respx.get("https://example.com/paper.pdf").mock(
        return_value=httpx.Response(
            200, content=PDF_BYTES, headers={"content-type": "application/pdf"}
        )
    )

    result = await download_file("dl_test01", "https://example.com/paper.pdf")

    assert result.kind == "document"
    assert result.mime_type == "application/pdf"
    assert result.file_name == "paper.pdf"
    assert result.size == len(PDF_BYTES)

    on_disk = storage_root / result.rel_path
    assert on_disk.read_bytes() == PDF_BYTES
    assert on_disk.parent == storage_root / "files" / "dl_test01"


@respx.mock
async def test_download_file_reports_progress(storage_root):
    respx.get("https://example.com/big.pdf").mock(
        return_value=httpx.Response(
            200,
            content=PDF_BYTES,
            headers={
                "content-type": "application/pdf",
                "content-length": str(len(PDF_BYTES)),
            },
        )
    )

    seen: list[float] = []

    async def _record(pct: float) -> None:
        seen.append(pct)

    await download_file("dl_prog", "https://example.com/big.pdf", on_progress=_record)
    assert seen, "expected at least one progress callback"
    assert all(0 <= p <= 100 for p in seen)


@respx.mock
async def test_download_file_trusts_the_response_over_the_url(storage_root):
    """A URL with no extension redirecting to a GIF still lands as an image."""
    respx.get("https://example.com/asset").mock(
        return_value=httpx.Response(
            302, headers={"location": "https://cdn.example.com/real.gif"}
        )
    )
    respx.get("https://cdn.example.com/real.gif").mock(
        return_value=httpx.Response(
            200, content=GIF_BYTES, headers={"content-type": "image/gif"}
        )
    )

    result = await download_file("dl_redir", "https://example.com/asset")
    assert result.kind == "image"
    assert result.file_name == "real.gif"


@respx.mock
async def test_oversize_stream_without_content_length_removes_the_partial_file(
    storage_root, monkeypatch
):
    """A chunked response can't be refused up front — the cap has to hold mid-stream."""
    monkeypatch.setattr(settings, "max_file_bytes", 1024)

    async def _chunks():
        yield b"%PDF-"
        for _ in range(8):
            yield b"x" * 1024

    respx.get("https://example.com/huge.pdf").mock(
        return_value=httpx.Response(
            200, content=_chunks(), headers={"content-type": "application/pdf"}
        )
    )

    with pytest.raises(IngestError, match="exceeds"):
        await download_file("dl_huge", "https://example.com/huge.pdf")

    files = list((storage_root / "files" / "dl_huge").iterdir())
    assert files == [], f"partial file left behind: {files}"


@respx.mock
async def test_oversize_content_length_is_refused_before_downloading(
    storage_root, monkeypatch
):
    monkeypatch.setattr(settings, "max_file_bytes", 1024)
    route = respx.get("https://example.com/declared.pdf").mock(
        return_value=httpx.Response(
            200,
            content=b"%PDF-" + b"x" * 8192,
            headers={"content-type": "application/pdf", "content-length": "8197"},
        )
    )

    with pytest.raises(IngestError, match="cap"):
        await download_file("dl_declared", "https://example.com/declared.pdf")
    assert route.called


@respx.mock
async def test_redirect_to_a_private_address_is_refused(storage_root):
    respx.get("https://example.com/evil").mock(
        return_value=httpx.Response(
            302, headers={"location": "http://127.0.0.1:8000/api/videos"}
        )
    )

    with pytest.raises(UnsafeUrlError):
        await download_file("dl_ssrf", "https://example.com/evil")


@respx.mock
async def test_redirect_to_a_non_http_scheme_is_refused(storage_root):
    respx.get("https://example.com/scheme").mock(
        return_value=httpx.Response(302, headers={"location": "file:///etc/passwd"})
    )

    with pytest.raises(UnsafeUrlError):
        await download_file("dl_scheme", "https://example.com/scheme")


@respx.mock
async def test_relative_redirects_are_resolved_and_rechecked(storage_root):
    respx.get("https://example.com/a/start").mock(
        return_value=httpx.Response(302, headers={"location": "../final.gif"})
    )
    respx.get("https://example.com/final.gif").mock(
        return_value=httpx.Response(
            200, content=GIF_BYTES, headers={"content-type": "image/gif"}
        )
    )

    result = await download_file("dl_rel", "https://example.com/a/start")
    assert result.file_name == "final.gif"


@respx.mock
async def test_a_redirect_loop_gives_up(storage_root):
    respx.get("https://example.com/loop").mock(
        return_value=httpx.Response(
            302, headers={"location": "https://example.com/loop"}
        )
    )

    with pytest.raises(IngestError, match="[Tt]oo many redirects"):
        await download_file("dl_loop", "https://example.com/loop")


@respx.mock
async def test_http_error_propagates_without_leaving_a_file(storage_root):
    respx.get("https://example.com/gone.pdf").mock(return_value=httpx.Response(404))

    with pytest.raises(IngestError, match="404"):
        await download_file("dl_404", "https://example.com/gone.pdf")

    assert list((storage_root / "files" / "dl_404").iterdir()) == []


# --- error messages ----------------------------------------------------------


def _status_error(code: int) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", "https://example.com/x")
    response = httpx.Response(code, request=request)
    return httpx.HTTPStatusError("boom", request=request, response=response)


@pytest.mark.parametrize(
    "code,fragment",
    [
        (403, "blocks automated requests"),
        (404, "not found"),
        (429, "rate-limited"),
        (500, "500"),
    ],
)
def test_describe_http_error_is_one_readable_line(code, fragment):
    msg = describe_http_error(_status_error(code))
    assert fragment in msg
    assert "\n" not in msg
    assert "mozilla.org" not in msg


def test_describe_http_error_handles_our_own_exceptions():
    assert describe_http_error(TooManyRedirects("x")) == "Too many redirects"
    assert "cap" in describe_http_error(ContentTooLarge("over the cap"))


@respx.mock
async def test_a_403_is_retried_with_the_plain_user_agent(storage_root):
    """Some hosts block browser UAs from non-browser clients."""
    seen: list[str] = []

    def _handler(request: httpx.Request) -> httpx.Response:
        ua = request.headers.get("user-agent", "")
        seen.append(ua)
        if "Chrome" in ua:
            return httpx.Response(403)
        return httpx.Response(
            200, content=PDF_BYTES, headers={"content-type": "application/pdf"}
        )

    respx.get("https://picky.example/doc.pdf").mock(side_effect=_handler)

    result = await download_file("dl_ua", "https://picky.example/doc.pdf")
    assert result.mime_type == "application/pdf"
    assert len(seen) == 2
    assert "Chrome" in seen[0] and "Chrome" not in seen[1]


@respx.mock
async def test_the_ua_retry_happens_at_most_once(storage_root):
    route = respx.get("https://always403.example/doc.pdf").mock(
        return_value=httpx.Response(403)
    )

    with pytest.raises(IngestError, match="403"):
        await download_file("dl_ua2", "https://always403.example/doc.pdf")
    assert route.call_count == 2


# --- intrinsic image dimensions ----------------------------------------------


def _png(w: int, h: int) -> bytes:
    import struct
    import zlib

    ihdr = struct.pack(">II", w, h) + b"\x08\x02\x00\x00\x00"
    chunk = b"IHDR" + ihdr
    return (
        b"\x89PNG\r\n\x1a\n"
        + struct.pack(">I", len(ihdr))
        + chunk
        + struct.pack(">I", zlib.crc32(chunk))
    )


def _gif(w: int, h: int) -> bytes:
    import struct

    return b"GIF89a" + struct.pack("<HH", w, h) + b"\x00" * 16


def _jpeg(w: int, h: int) -> bytes:
    import struct

    # SOI, a COM segment to make sure the walker skips segments, then SOF0.
    sof = b"\xff\xc0" + struct.pack(">H", 17) + b"\x08" + struct.pack(">HH", h, w)
    return (
        b"\xff\xd8" + b"\xff\xfe" + struct.pack(">H", 6) + b"abcd" + sof + b"\x00" * 8
    )


def test_image_size_reads_png_gif_and_jpeg():
    from app.services.ingest.sniff import image_size

    assert image_size(_png(1200, 675)) == (1200, 675)
    assert image_size(_gif(64, 48)) == (64, 48)
    assert image_size(_jpeg(800, 600)) == (800, 600)


def test_image_size_returns_none_for_unknown_or_truncated_data():
    from app.services.ingest.sniff import image_size

    assert image_size(b"") is None
    assert image_size(b"not an image at all, really not") is None
    assert image_size(_png(10, 10)[:12]) is None
