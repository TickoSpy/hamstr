"""MIME resolution and filename safety for direct downloads.

Magic bytes are hand-rolled rather than pulled from python-magic, which needs the
libmagic system package in the Docker image for a table this short.
"""

import mimetypes
import re
import struct
import unicodedata
from pathlib import PurePosixPath
from urllib.parse import unquote, urlsplit

from app.services.ingest.tagmap import kind_for_mime

# (offset, signature, mime). Checked in order; first match wins.
_MAGIC: tuple[tuple[int, bytes, str], ...] = (
    (0, b"%PDF-", "application/pdf"),
    (0, b"\xff\xd8\xff", "image/jpeg"),
    (0, b"\x89PNG\r\n\x1a\n", "image/png"),
    (0, b"GIF87a", "image/gif"),
    (0, b"GIF89a", "image/gif"),
    (0, b"BM", "image/bmp"),
    (0, b"\x00\x00\x01\x00", "image/x-icon"),
    (0, b"\x1a\x45\xdf\xa3", "video/webm"),  # also matroska; webm is the safe guess
    (0, b"OggS", "audio/ogg"),
    (0, b"fLaC", "audio/flac"),
    (0, b"ID3", "audio/mpeg"),
    (0, b"\xff\xfb", "audio/mpeg"),
    (0, b"\xff\xf3", "audio/mpeg"),
    (0, b"\xff\xf2", "audio/mpeg"),
    (4, b"ftypavif", "image/avif"),
    (4, b"ftypavis", "image/avif"),
    (4, b"ftypheic", "image/heic"),
    (4, b"ftypheix", "image/heic"),
    (4, b"ftypM4A ", "audio/mp4"),
    (4, b"ftypisom", "video/mp4"),
    (4, b"ftypmp42", "video/mp4"),
    (4, b"ftypMSNV", "video/mp4"),
    (4, b"ftypM4V ", "video/mp4"),
    (4, b"ftypqt  ", "video/quicktime"),
)

_GENERIC_TYPES = frozenset(
    {"application/octet-stream", "binary/octet-stream", "application/binary", ""}
)

_UNSAFE_CHARS = re.compile(r"[^A-Za-z0-9._-]")
_REPEATED_UNDERSCORE = re.compile(r"_{2,}")
# RFC 5987: filename*=UTF-8''percent%20encoded
_EXT_FILENAME = re.compile(
    r"filename\*\s*=\s*(?P<charset>[\w-]*)'(?P<lang>[\w-]*)'(?P<value>[^;]+)",
    re.IGNORECASE,
)
_PLAIN_FILENAME = re.compile(
    r"filename\s*=\s*(?:\"(?P<quoted>[^\"]*)\"|(?P<bare>[^;]+))", re.IGNORECASE
)


def sniff_magic(head: bytes) -> str | None:
    """Identify a MIME type from the first bytes of a file, or None."""
    if not head:
        return None
    for offset, signature, mime in _MAGIC:
        if head[offset : offset + len(signature)] == signature:
            return mime
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    if head[:4] == b"PK\x03\x04":
        # An epub is a zip whose first entry is the mimetype file.
        if b"application/epub+zip" in head[:200]:
            return "application/epub+zip"
        return "application/zip"
    lowered = head[:512].lstrip().lower()
    if lowered.startswith(b"<!doctype html") or lowered.startswith(b"<html"):
        return "text/html"
    if lowered.startswith(b"<?xml") or lowered.startswith(b"<svg"):
        return "image/svg+xml" if b"<svg" in lowered else "application/xml"
    return None


def _strip_params(content_type: str | None) -> str:
    if not content_type:
        return ""
    return content_type.split(";", 1)[0].strip().lower()


def url_extension(url: str) -> str:
    """Lowercase extension (with dot) from a URL path, or ''."""
    try:
        path = urlsplit(url).path
    except ValueError:
        return ""
    return PurePosixPath(unquote(path)).suffix.lower()


def resolve_media(
    url: str, content_type: str | None, head: bytes | None
) -> tuple[str, str, str]:
    """Decide (mime, extension, kind) for a downloadable resource.

    Precedence: magic bytes, then Content-Type, then the URL extension. Magic wins
    because servers mislabel far more often than file headers lie.
    """
    mime = sniff_magic(head or b"")

    if not mime:
        declared = _strip_params(content_type)
        if declared and declared not in _GENERIC_TYPES:
            mime = declared

    ext = url_extension(url)

    if not mime and ext:
        guessed, _ = mimetypes.guess_type("f" + ext)
        mime = guessed

    if not mime:
        mime = "application/octet-stream"

    if not ext:
        ext = mimetypes.guess_extension(mime) or ""
        if ext == ".jpe":  # mimetypes' unhelpful first choice for image/jpeg
            ext = ".jpg"

    return mime, ext, kind_for_mime(mime, ext)


def _decode_ext_filename(match: re.Match) -> str | None:
    charset = (match.group("charset") or "utf-8").lower() or "utf-8"
    try:
        return unquote(match.group("value").strip(), encoding=charset, errors="strict")
    except (LookupError, UnicodeDecodeError):
        return None


def sanitize_filename(name: str, *, fallback: str = "download") -> str:
    """Reduce an arbitrary string to a safe single path segment."""
    # Windows-style separators aren't separators to PurePosixPath, so normalize
    # them first — otherwise "..\..\win.ini" survives as a single "name".
    name = name.strip().replace("\\", "/")
    name = PurePosixPath(name).name  # drop any directory component

    # NFKD decomposes accents into base + combining mark; dropping the marks is
    # what turns "résumé" into "resume" instead of "re_sume_".
    name = unicodedata.normalize("NFKD", name)
    name = "".join(c for c in name if not unicodedata.combining(c))

    name = _UNSAFE_CHARS.sub("_", name)
    name = _REPEATED_UNDERSCORE.sub("_", name)
    # Strip leading dots and underscores together: doing it in two passes lets
    # ".._.._win.ini" end up back at "..win.ini".
    name = name.lstrip("._").rstrip("_")
    if not name:
        return fallback

    stem, dot, suffix = name.rpartition(".")
    if not dot:
        return name[:120]
    return f"{stem[:100]}.{suffix[:20]}" if stem else fallback


def safe_filename(
    url: str, content_disposition: str | None, content_type: str | None
) -> str:
    """Best available filename for a download, reduced to a safe path segment.

    Order: RFC 5987 ``filename*``, plain ``filename``, the URL's last path
    segment, then ``download``. The extension is corrected against the MIME type
    when the name has none.
    """
    candidate: str | None = None

    if content_disposition:
        ext_match = _EXT_FILENAME.search(content_disposition)
        if ext_match:
            candidate = _decode_ext_filename(ext_match)
        if not candidate:
            plain = _PLAIN_FILENAME.search(content_disposition)
            if plain:
                candidate = (plain.group("quoted") or plain.group("bare") or "").strip()

    if not candidate:
        try:
            candidate = PurePosixPath(unquote(urlsplit(url).path)).name
        except ValueError:
            candidate = ""

    name = sanitize_filename(candidate or "download")

    if "." not in name:
        mime = _strip_params(content_type)
        ext = mimetypes.guess_extension(mime) if mime else None
        if ext == ".jpe":
            ext = ".jpg"
        if ext:
            name += ext

    return name


def image_size(data: bytes) -> tuple[int, int] | None:
    """Intrinsic (width, height) read from an image's header, or None.

    Emitting width/height on archived <img> elements is what stops the reader
    reflowing as each image loads — without them the browser reserves no space
    and the text jumps around during scrolling. Header parsing keeps this free
    of a Pillow dependency.
    """
    if len(data) < 24:
        return None

    # PNG: IHDR is always the first chunk.
    if data[:8] == b"\x89PNG\r\n\x1a\n" and data[12:16] == b"IHDR":
        w, h = struct.unpack(">II", data[16:24])
        return (w, h) if w and h else None

    # GIF: logical screen descriptor, little-endian.
    if data[:6] in (b"GIF87a", b"GIF89a"):
        w, h = struct.unpack("<HH", data[6:10])
        return (w, h) if w and h else None

    # BMP
    if data[:2] == b"BM" and len(data) >= 26:
        w, h = struct.unpack("<ii", data[18:26])
        return (abs(w), abs(h)) if w and h else None

    # WebP: VP8 (lossy), VP8L (lossless) and VP8X (extended) each differ.
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        chunk = data[12:16]
        try:
            if chunk == b"VP8 " and len(data) >= 30:
                w = struct.unpack("<H", data[26:28])[0] & 0x3FFF
                h = struct.unpack("<H", data[28:30])[0] & 0x3FFF
                return (w, h) if w and h else None
            if chunk == b"VP8L" and len(data) >= 25:
                bits = struct.unpack("<I", data[21:25])[0]
                w = (bits & 0x3FFF) + 1
                h = ((bits >> 14) & 0x3FFF) + 1
                return (w, h)
            if chunk == b"VP8X" and len(data) >= 30:
                w = int.from_bytes(data[24:27], "little") + 1
                h = int.from_bytes(data[27:30], "little") + 1
                return (w, h)
        except struct.error:
            return None
        return None

    # JPEG: walk the segment chain to the SOFn frame header.
    if data[:2] == b"\xff\xd8":
        i = 2
        end = len(data)
        while i + 9 < end:
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            # Standalone markers carry no length payload.
            if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7 or marker == 0x01:
                i += 2
                continue
            try:
                seg_len = struct.unpack(">H", data[i + 2 : i + 4])[0]
            except struct.error:
                return None
            # SOF0..SOF15, excluding the DHT/JPG/DAC markers interleaved in that range.
            if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
                if i + 9 > end:
                    return None
                h, w = struct.unpack(">HH", data[i + 5 : i + 9])
                return (w, h) if w and h else None
            i += 2 + seg_len
        return None

    return None
