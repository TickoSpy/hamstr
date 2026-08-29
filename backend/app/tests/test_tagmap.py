import pytest

from app.services.ingest.tagmap import classify, tags_for

# (mime, ext) -> (kind, category, format). Covers every pairing the feature was
# specified against: mp3=audio, mp4=video, pdf=text, html=text, gif=images.
CASES = [
    ("audio/mpeg", ".mp3", ("audio", "audio", "mp3")),
    ("video/mp4", ".mp4", ("video", "video", "mp4")),
    ("application/pdf", ".pdf", ("document", "text", "pdf")),
    ("text/html", ".html", ("document", "text", "html")),
    ("image/gif", ".gif", ("image", "images", "gif")),
    ("image/jpeg", ".jpg", ("image", "images", "jpeg")),
    ("image/png", ".png", ("image", "images", "png")),
    ("audio/flac", ".flac", ("audio", "audio", "flac")),
    ("video/webm", ".webm", ("video", "video", "webm")),
    ("application/epub+zip", ".epub", ("document", "text", "epub")),
    ("text/plain", ".txt", ("document", "text", "txt")),
    ("application/zip", ".zip", ("file", "other", "zip")),
]


@pytest.mark.parametrize("mime,ext,expected", CASES)
def test_classify(mime, ext, expected):
    assert classify(mime, ext) == expected


@pytest.mark.parametrize("mime,ext,expected", CASES)
def test_classify_from_mime_alone(mime, ext, expected):
    assert classify(mime, None) == expected


@pytest.mark.parametrize("mime,ext,expected", CASES)
def test_classify_from_extension_alone(mime, ext, expected):
    assert classify(None, ext) == expected


def test_classify_unknown():
    assert classify(None, None) == ("file", "other", "unknown")
    assert classify("application/octet-stream", None) == ("file", "other", "unknown")


def test_classify_falls_back_to_the_mime_prefix():
    kind, category, fmt = classify("audio/x-weird-format", ".weird")
    assert (kind, category) == ("audio", "audio")
    assert fmt == "weird"


def test_classify_rejects_a_junk_extension_as_a_format_tag():
    _, _, fmt = classify(None, ".this-is-not-an-extension")
    assert fmt == "unknown"


@pytest.mark.parametrize(
    "kind,mime,ext,expected",
    [
        ("audio", "audio/mpeg", ".mp3", ["audio", "mp3"]),
        ("video", "video/mp4", ".mp4", ["video", "mp4"]),
        ("document", "application/pdf", ".pdf", ["text", "pdf"]),
        ("image", "image/gif", ".gif", ["images", "gif"]),
        ("article", "text/html", None, ["text", "article"]),
        ("file", "application/zip", ".zip", ["other", "zip"]),
    ],
)
def test_tags_for(kind, mime, ext, expected):
    assert tags_for(kind, mime, ext) == expected


def test_tags_for_never_duplicates_category_and_format():
    """An unrecognised video type with a ".video" extension would otherwise
    produce ["video", "video"]."""
    assert classify("video/x-unknown-codec", ".video") == ("video", "video", "video")
    assert tags_for("video", "video/x-unknown-codec", ".video") == ["video"]


def test_kind_wins_over_the_sniffed_type():
    """The worker knows what it actually produced; the sniffer only guesses."""
    assert tags_for("article", "application/pdf", ".pdf") == ["text", "article"]


def test_an_undeterminable_format_yields_only_the_category():
    """ "unknown" as a tag is noise in the filter row."""
    assert tags_for("file", None, None) == ["other"]
    assert tags_for("audio", None, None) == ["audio"]
