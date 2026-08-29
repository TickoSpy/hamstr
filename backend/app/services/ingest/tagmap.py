"""File type -> (kind, category, format) mapping.

One table, one source of truth. `category` is the broad bucket the user asked for
(mp3=audio, mp4=video, pdf=text, html=text, gif=images); `format` is the specific
file type. Both are applied as ordinary, removable tags.
"""

from dataclasses import dataclass, field

# kind -> the broad category tag
CATEGORY_BY_KIND: dict[str, str] = {
    "video": "video",
    "audio": "audio",
    "article": "text",
    "document": "text",
    "image": "images",
    "file": "other",
}


@dataclass(frozen=True)
class FormatSpec:
    name: str  # the format tag, e.g. "pdf"
    kind: str  # video | audio | article | document | image | file
    mimes: frozenset[str] = field(default_factory=frozenset)
    exts: frozenset[str] = field(default_factory=frozenset)


def _spec(name: str, kind: str, mimes: list[str], exts: list[str]) -> FormatSpec:
    return FormatSpec(name, kind, frozenset(mimes), frozenset(exts))


FORMATS: tuple[FormatSpec, ...] = (
    # --- video ---
    _spec("mp4", "video", ["video/mp4", "video/x-m4v"], [".mp4", ".m4v"]),
    _spec("webm", "video", ["video/webm"], [".webm"]),
    _spec("mkv", "video", ["video/x-matroska"], [".mkv"]),
    _spec("mov", "video", ["video/quicktime"], [".mov"]),
    _spec("avi", "video", ["video/x-msvideo"], [".avi"]),
    # --- audio ---
    _spec("mp3", "audio", ["audio/mpeg", "audio/mp3"], [".mp3"]),
    _spec("m4a", "audio", ["audio/mp4", "audio/x-m4a"], [".m4a"]),
    _spec("aac", "audio", ["audio/aac"], [".aac"]),
    _spec("ogg", "audio", ["audio/ogg", "application/ogg"], [".ogg", ".oga"]),
    _spec("opus", "audio", ["audio/opus"], [".opus"]),
    _spec("flac", "audio", ["audio/flac", "audio/x-flac"], [".flac"]),
    _spec("wav", "audio", ["audio/wav", "audio/x-wav"], [".wav"]),
    # --- text / documents ---
    _spec("pdf", "document", ["application/pdf"], [".pdf"]),
    _spec("epub", "document", ["application/epub+zip"], [".epub"]),
    _spec("txt", "document", ["text/plain"], [".txt"]),
    _spec("markdown", "document", ["text/markdown"], [".md", ".markdown"]),
    _spec("doc", "document", ["application/msword"], [".doc"]),
    _spec(
        "docx",
        "document",
        ["application/vnd.openxmlformats-officedocument.wordprocessingml.document"],
        [".docx"],
    ),
    _spec("rtf", "document", ["application/rtf", "text/rtf"], [".rtf"]),
    _spec("csv", "document", ["text/csv"], [".csv"]),
    _spec("json", "document", ["application/json"], [".json"]),
    # A saved HTML file that never went through reader extraction.
    _spec(
        "html", "document", ["text/html", "application/xhtml+xml"], [".html", ".htm"]
    ),
    # --- images ---
    _spec("jpeg", "image", ["image/jpeg"], [".jpg", ".jpeg"]),
    _spec("png", "image", ["image/png"], [".png"]),
    _spec("gif", "image", ["image/gif"], [".gif"]),
    _spec("webp", "image", ["image/webp"], [".webp"]),
    _spec("avif", "image", ["image/avif"], [".avif"]),
    _spec("svg", "image", ["image/svg+xml"], [".svg"]),
    _spec("heic", "image", ["image/heic", "image/heif"], [".heic", ".heif"]),
    _spec("bmp", "image", ["image/bmp"], [".bmp"]),
    # --- other ---
    _spec("zip", "file", ["application/zip"], [".zip"]),
)

_BY_MIME: dict[str, FormatSpec] = {m: s for s in FORMATS for m in s.mimes}
_BY_EXT: dict[str, FormatSpec] = {e: s for s in FORMATS for e in s.exts}

# A captured web page: the reader-view article, not a saved .html file.
ARTICLE_FORMAT = "article"
UNKNOWN_FORMAT = "unknown"

# Every name this module can hand out. The library's tag filter uses it to tell
# the tags it generated itself — which only restate the kind facets the UI
# already offers — from the ones the user actually typed.
AUTO_TAG_NAMES: frozenset[str] = frozenset(
    set(CATEGORY_BY_KIND.values())
    | {spec.name for spec in FORMATS}
    | {ARTICLE_FORMAT, UNKNOWN_FORMAT}
)


def _lookup(mime: str | None, ext: str | None) -> FormatSpec | None:
    if mime:
        spec = _BY_MIME.get(mime.split(";", 1)[0].strip().lower())
        if spec:
            return spec
    if ext:
        return _BY_EXT.get(ext.lower())
    return None


def kind_for_mime(mime: str | None, ext: str | None = None) -> str:
    """The `kind` discriminator for a downloaded file. HTML files fetched as a
    direct download are `document`; reader-captured pages are `article` and never
    come through here."""
    spec = _lookup(mime, ext)
    if spec:
        return spec.kind
    prefix = (mime or "").split("/", 1)[0].lower()
    if prefix in ("video", "audio", "image"):
        return {"video": "video", "audio": "audio", "image": "image"}[prefix]
    if prefix == "text":
        return "document"
    return "file"


def classify(mime: str | None, ext: str | None) -> tuple[str, str, str]:
    """Return (kind, category, format) for a file type."""
    spec = _lookup(mime, ext)
    if spec:
        return spec.kind, CATEGORY_BY_KIND[spec.kind], spec.name

    kind = kind_for_mime(mime, ext)
    fmt = (ext or "").lstrip(".").lower() or UNKNOWN_FORMAT
    if not fmt.isalnum() or len(fmt) > 12:
        fmt = UNKNOWN_FORMAT
    return kind, CATEGORY_BY_KIND[kind], fmt


def tags_for(kind: str, mime: str | None = None, ext: str | None = None) -> list[str]:
    """The auto-tags for an item: [category, format].

    `kind` wins over the sniffed type — it is what the worker actually produced.
    """
    if kind == "article":
        return [CATEGORY_BY_KIND["article"], ARTICLE_FORMAT]

    _, category, fmt = classify(mime, ext)
    category = CATEGORY_BY_KIND.get(kind, category)

    names = [category]
    # An "unknown" tag is noise in the filter row — better to carry only the
    # category than to invent a format we couldn't determine.
    if fmt and fmt != category and fmt != UNKNOWN_FORMAT:
        names.append(fmt)
    return names
