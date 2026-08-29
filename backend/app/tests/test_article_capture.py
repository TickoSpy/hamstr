import httpx
import pytest
import respx

from app.services.ingest.article import capture_article, extract_article
from app.services.ingest.types import IngestError

GIF = b"GIF89a" + b"\x00" * 256
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 256


# Varied prose on purpose: extraction quality is scored partly on repeated
# sentences, so a fixture built from one repeated line would look duplicated.
def _paragraph(start: int) -> str:
    return " ".join(
        f"Observation number {i} records that the fox moved {i * 3} metres closer "
        f"to the treeline before pausing to survey the open ground ahead of it."
        for i in range(start, start + 12)
    )


BODY_1, BODY_2, BODY_3 = _paragraph(1), _paragraph(20), _paragraph(40)

ARTICLE_PAGE = f"""<!DOCTYPE html>
<html><head>
  <title>Fox Report | Daily Example</title>
  <meta property="og:title" content="Fox Report">
  <meta property="og:description" content="A thorough report about a fox.">
  <meta property="og:site_name" content="Daily Example">
  <meta property="og:image" content="https://news.example/lead.jpg">
  <script>window.ads = true;</script>
  <style>.ad {{ display: block }}</style>
</head><body>
  <nav><a href="/">Home</a><a href="/subscribe">Subscribe</a></nav>
  <div class="ad-slot"><img src="https://ads.example/tracker.gif"></div>
  <article>
    <h1>Fox Report</h1>
    <p>{BODY_1}</p>
    <p>{BODY_2}</p>
    <figure><img src="/img/fox.jpg" alt="A fox"><figcaption>A fox.</figcaption></figure>
    <p>{BODY_3}</p>
    <p>Read more at <a href="/related">the related story</a>.</p>
  </article>
  <footer>Copyright</footer>
</body></html>
"""


@pytest.fixture(autouse=True)
def _allow_dns(monkeypatch):
    async def _fake(host: str, port: int) -> list:
        return [(2, 1, 6, "", ("93.184.216.34", port))]

    monkeypatch.setattr("app.services.urlsafety._getaddrinfo", _fake)


# --- extraction --------------------------------------------------------------


def test_extract_article_finds_the_body_and_metadata():
    got = extract_article(ARTICLE_PAGE, "https://news.example/fox")
    assert got is not None
    assert got.word_count > 100
    assert "Observation number 1 records" in got.text
    # Chrome, ads and navigation are not part of the article.
    assert "Subscribe" not in got.text
    assert "Copyright" not in got.text
    assert got.title
    assert got.lead_image_url == "https://news.example/lead.jpg"


def test_extract_article_returns_none_for_a_stub_page():
    stub = "<html><body><p>Subscribe to continue reading.</p></body></html>"
    assert extract_article(stub, "https://news.example/x") is None


def test_extract_article_survives_broken_markup():
    """Must not raise — a malformed page should degrade to raw.html, not crash."""
    extract_article("<html><body><p>unclosed", "https://news.example/x")
    extract_article("", "https://news.example/x")


# --- capture -----------------------------------------------------------------


@respx.mock
async def test_capture_stores_a_clean_reader_copy(storage_root):
    respx.get("https://news.example/fox").mock(
        return_value=httpx.Response(
            200, text=ARTICLE_PAGE, headers={"content-type": "text/html; charset=utf-8"}
        )
    )
    respx.get("https://news.example/img/fox.jpg").mock(
        return_value=httpx.Response(
            200, content=JPEG, headers={"content-type": "image/jpeg"}
        )
    )
    respx.get("https://news.example/lead.jpg").mock(
        return_value=httpx.Response(
            200, content=JPEG, headers={"content-type": "image/jpeg"}
        )
    )

    result = await capture_article("web_fox1", "https://news.example/fox")

    assert result.capture_source == "direct"
    assert result.article_rel and result.raw_rel
    assert result.word_count > 100
    assert result.thumb_rel, "og:image should become the item thumbnail"

    article = (storage_root / result.article_rel).read_text()
    assert "<script" not in article.lower()
    assert "window.ads" not in article
    # Every image points at our own asset endpoint, nothing at the origin.
    assert "/stream/web_fox1/asset/" in article
    assert "news.example/img" not in article
    assert "ads.example" not in article

    assert len(result.asset_names) == 1
    assert (
        storage_root / "articles" / "web_fox1" / "assets" / result.asset_names[0]
    ).exists()

    # The raw page is kept verbatim as a fallback.
    assert "window.ads" in (storage_root / result.raw_rel).read_text()


@respx.mock
async def test_capture_reports_progress(storage_root):
    respx.get("https://news.example/fox").mock(
        return_value=httpx.Response(200, text=ARTICLE_PAGE)
    )
    respx.get(url__regex=r"https://news\.example/.*\.jpg").mock(
        return_value=httpx.Response(
            200, content=JPEG, headers={"content-type": "image/jpeg"}
        )
    )

    seen: list[float] = []

    async def _record(pct: float) -> None:
        seen.append(pct)

    await capture_article("web_prog", "https://news.example/fox", on_progress=_record)
    assert seen == sorted(seen), "progress must be monotonic"
    assert seen[-1] == 100.0


@respx.mock
async def test_a_failed_image_does_not_fail_the_capture(storage_root):
    respx.get("https://news.example/fox").mock(
        return_value=httpx.Response(200, text=ARTICLE_PAGE)
    )
    respx.get("https://news.example/img/fox.jpg").mock(return_value=httpx.Response(404))
    respx.get("https://news.example/lead.jpg").mock(return_value=httpx.Response(500))

    result = await capture_article("web_noimg", "https://news.example/fox")

    assert result.article_rel
    assert result.asset_names == []
    assert result.thumb_rel is None
    article = (storage_root / result.article_rel).read_text()
    assert "<img" not in article
    # The prose around the dropped image is still there.
    assert "Observation number 1 records" in article


@respx.mock
async def test_unextractable_page_still_completes_with_raw_html(storage_root):
    """A page we can't parse is worth keeping — it must not become an error row."""
    respx.get("https://spa.example/app").mock(
        return_value=httpx.Response(
            200,
            text="<html><head><title>App</title></head><body><div id='root'></div></body></html>",
        )
    )

    result = await capture_article("web_spa", "https://spa.example/app")

    assert result.article_rel is None
    assert result.raw_rel
    assert (storage_root / result.raw_rel).exists()
    assert result.title == "App"


@respx.mock
async def test_a_fetch_failure_raises_a_readable_error(storage_root):
    respx.get("https://news.example/gone").mock(return_value=httpx.Response(404))

    with pytest.raises(IngestError, match="404"):
        await capture_article("web_gone", "https://news.example/gone")


@respx.mock
async def test_assets_hosted_on_a_private_address_are_skipped(
    storage_root, monkeypatch
):
    """An article whose images resolve internally must not be used to probe the LAN."""

    async def _resolve(host: str, port: int) -> list:
        addr = "10.0.0.5" if host == "internal.example" else "93.184.216.34"
        return [(2, 1, 6, "", (addr, port))]

    monkeypatch.setattr("app.services.urlsafety._getaddrinfo", _resolve)

    page = ARTICLE_PAGE.replace(
        '<img src="/img/fox.jpg" alt="A fox">',
        '<img src="http://internal.example/secret.png" alt="A fox">',
    )
    respx.get("https://news.example/fox").mock(
        return_value=httpx.Response(200, text=page)
    )
    respx.get("https://news.example/lead.jpg").mock(
        return_value=httpx.Response(
            200, content=JPEG, headers={"content-type": "image/jpeg"}
        )
    )
    internal = respx.get("http://internal.example/secret.png").mock(
        return_value=httpx.Response(200, content=GIF)
    )

    result = await capture_article("web_ssrf", "https://news.example/fox")

    assert not internal.called, "the internal host must never be contacted"
    assert result.asset_names == []


@respx.mock
async def test_oversize_page_is_refused(storage_root, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "max_article_bytes", 512)
    respx.get("https://news.example/huge").mock(
        return_value=httpx.Response(200, text="<html>" + "x" * 4096 + "</html>")
    )

    with pytest.raises(Exception):
        await capture_article("web_huge", "https://news.example/huge")


@respx.mock
async def test_gzipped_pages_are_decoded_exactly_once(storage_root):
    """Regression: safe_get rebuilt the response from already-decompressed bytes
    while keeping Content-Encoding, so httpx tried to gunzip them again and every
    real-world page failed with "incorrect header check"."""
    import gzip

    body = ARTICLE_PAGE.encode("utf-8")
    respx.get("https://news.example/gz").mock(
        return_value=httpx.Response(
            200,
            content=gzip.compress(body),
            headers={
                "content-type": "text/html; charset=utf-8",
                "content-encoding": "gzip",
            },
        )
    )
    respx.get(url__regex=r"https://news\.example/.*\.jpg").mock(
        return_value=httpx.Response(
            200, content=JPEG, headers={"content-type": "image/jpeg"}
        )
    )

    result = await capture_article("web_gz", "https://news.example/gz")

    assert result.article_rel
    assert result.word_count > 100
    assert "Observation number 1 records" in (storage_root / result.raw_rel).read_text()


# --- paywall + archive chain --------------------------------------------------

PAYWALLED_PAGE = """<!DOCTYPE html>
<html><head>
  <title>Gated Report</title>
  <meta property="og:description" content="An in-depth investigation into municipal
  water infrastructure across the country, based on two years of records requests.">
</head><body>
  <article>
    <h1>Gated Report</h1>
    <p>The first paragraph is free, and then the wall comes down…</p>
    <div class="paywall-overlay">Subscribe to continue reading.</div>
  </article>
</body></html>
"""

FULL_SNAPSHOT = ARTICLE_PAGE.replace("Fox Report", "Gated Report")

CAPTCHA_PAGE = (
    "<html><head><title>archive.ph</title></head><body><h1>One more step</h1>"
    "<p>Please complete the security check to access</p></body></html>"
)

TARGET = "https://news.example/gated"


def _mock_all_archive_mirrors(response_factory):
    import respx as _respx

    return _respx.get(url__regex=r"https://archive\.(ph|is|today|md)/newest/.*").mock(
        side_effect=response_factory
    )


@respx.mock
async def test_paywalled_article_is_recovered_from_archive_today(storage_root):
    respx.get(TARGET).mock(return_value=httpx.Response(200, text=PAYWALLED_PAGE))
    respx.get(url__regex=r"https://news\.example/.*\.jpg").mock(
        return_value=httpx.Response(
            200, content=JPEG, headers={"content-type": "image/jpeg"}
        )
    )

    calls: list[str] = []

    def _mirror(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        # First mirror rate-limits, second serves the full snapshot.
        if len(calls) == 1:
            return httpx.Response(429, text=CAPTCHA_PAGE)
        return httpx.Response(200, text=FULL_SNAPSHOT)

    _mock_all_archive_mirrors(_mirror)

    result = await capture_article("web_gated", TARGET)

    assert result.paywalled is True
    assert result.capture_source == "archive.today"
    assert "archive." in result.capture_url
    assert result.word_count > 100
    assert len(calls) == 2, "the rate-limited mirror should be skipped, not retried"


@respx.mock
async def test_falls_back_to_wayback_when_every_mirror_is_blocked(storage_root):
    respx.get(TARGET).mock(return_value=httpx.Response(200, text=PAYWALLED_PAGE))
    respx.get(url__regex=r"https://news\.example/.*\.jpg").mock(
        return_value=httpx.Response(
            200, content=JPEG, headers={"content-type": "image/jpeg"}
        )
    )
    _mock_all_archive_mirrors(lambda request: httpx.Response(429, text=CAPTCHA_PAGE))

    snapshot = "https://web.archive.org/web/20240101/" + TARGET
    respx.get(url__startswith="https://archive.org/wayback/available").mock(
        return_value=httpx.Response(
            200,
            json={
                "archived_snapshots": {
                    "closest": {"available": True, "status": "200", "url": snapshot}
                }
            },
        )
    )
    respx.get(snapshot).mock(
        return_value=httpx.Response(
            200,
            text='<div id="wm-ipp-base">TOOLBAR</div>' + FULL_SNAPSHOT,
        )
    )

    result = await capture_article("web_wb", TARGET)

    assert result.paywalled is True
    assert result.capture_source == "wayback"
    article = (storage_root / result.article_rel).read_text()
    assert "TOOLBAR" not in article


@respx.mock
async def test_a_stub_is_kept_when_no_archive_has_anything_better(storage_root):
    """Losing the headline entirely is worse than keeping a teaser."""
    respx.get(TARGET).mock(return_value=httpx.Response(200, text=PAYWALLED_PAGE))
    _mock_all_archive_mirrors(lambda request: httpx.Response(429, text=CAPTCHA_PAGE))
    respx.get(url__startswith="https://archive.org/wayback/available").mock(
        return_value=httpx.Response(200, json={"archived_snapshots": {}})
    )

    result = await capture_article("web_stub", TARGET)

    assert result.paywalled is True
    assert result.capture_source == "direct"
    assert result.title


@respx.mock
async def test_a_hard_403_still_tries_the_archives(storage_root):
    """A 403 is a paywall signal, not a reason to give up before the fallback."""
    respx.get(TARGET).mock(return_value=httpx.Response(403))
    respx.get(url__regex=r"https://news\.example/.*\.jpg").mock(
        return_value=httpx.Response(
            200, content=JPEG, headers={"content-type": "image/jpeg"}
        )
    )
    _mock_all_archive_mirrors(lambda request: httpx.Response(200, text=FULL_SNAPSHOT))

    result = await capture_article("web_403", TARGET)

    assert result.paywalled is True
    assert result.capture_source == "archive.today"
    assert result.word_count > 100


@respx.mock
async def test_a_hard_403_with_no_snapshot_anywhere_reports_the_paywall(storage_root):
    respx.get(TARGET).mock(return_value=httpx.Response(403))
    _mock_all_archive_mirrors(lambda request: httpx.Response(429, text=CAPTCHA_PAGE))
    respx.get(url__startswith="https://archive.org/wayback/available").mock(
        return_value=httpx.Response(200, json={"archived_snapshots": {}})
    )

    with pytest.raises(IngestError, match="[Pp]aywalled"):
        await capture_article("web_403b", TARGET)


@respx.mock
async def test_a_clean_article_never_touches_the_archives(storage_root):
    respx.get("https://news.example/fox").mock(
        return_value=httpx.Response(200, text=ARTICLE_PAGE)
    )
    respx.get(url__regex=r"https://news\.example/.*\.jpg").mock(
        return_value=httpx.Response(
            200, content=JPEG, headers={"content-type": "image/jpeg"}
        )
    )
    mirrors = _mock_all_archive_mirrors(
        lambda request: httpx.Response(200, text=FULL_SNAPSHOT)
    )
    wayback = respx.get(url__startswith="https://archive.org/wayback/available").mock(
        return_value=httpx.Response(200, json={"archived_snapshots": {}})
    )

    result = await capture_article("web_clean", "https://news.example/fox")

    assert result.capture_source == "direct"
    assert result.paywalled is False
    assert not mirrors.called
    assert not wayback.called


@respx.mock
async def test_archives_are_skipped_when_disabled(storage_root, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "archive_enabled", False)
    respx.get(TARGET).mock(return_value=httpx.Response(200, text=PAYWALLED_PAGE))
    mirrors = _mock_all_archive_mirrors(
        lambda request: httpx.Response(200, text=FULL_SNAPSHOT)
    )

    result = await capture_article("web_off", TARGET)

    assert result.paywalled is True
    assert result.capture_source == "direct"
    assert not mirrors.called


# --- paywall handling for browser captures ------------------------------------


@respx.mock
async def test_a_paywalled_capture_still_tries_the_archives(storage_root):
    """Capturing while logged out yields the same teaser the server would get."""
    respx.get(url__regex=r"https://news\.example/.*\.jpg").mock(
        return_value=httpx.Response(
            200, content=JPEG, headers={"content-type": "image/jpeg"}
        )
    )
    _mock_all_archive_mirrors(lambda request: httpx.Response(200, text=FULL_SNAPSHOT))

    result = await capture_article("web_capgate", TARGET, supplied_html=PAYWALLED_PAGE)

    assert result.paywalled is True
    assert result.capture_source == "archive.today"
    assert result.word_count > 100


@respx.mock
async def test_a_full_capture_is_never_second_guessed(storage_root):
    """A logged-in capture is the best copy there is — don't go hunting."""
    respx.get(url__regex=r"https://news\.example/.*\.jpg").mock(
        return_value=httpx.Response(
            200, content=JPEG, headers={"content-type": "image/jpeg"}
        )
    )
    mirrors = _mock_all_archive_mirrors(
        lambda request: httpx.Response(200, text=FULL_SNAPSHOT)
    )

    result = await capture_article(
        "web_capfull", "https://news.example/fox", supplied_html=ARTICLE_PAGE
    )

    assert result.capture_source == "extension"
    assert result.paywalled is False
    assert not mirrors.called


@respx.mock
async def test_an_archive_copy_from_the_browser_is_recorded_as_such(storage_root):
    """The browser can reach archive.today; the server never can."""
    respx.get(url__regex=r"https://news\.example/.*\.jpg").mock(
        return_value=httpx.Response(
            200, content=JPEG, headers={"content-type": "image/jpeg"}
        )
    )
    mirrors = _mock_all_archive_mirrors(
        lambda request: httpx.Response(429, text=CAPTCHA_PAGE)
    )

    result = await capture_article(
        "web_caparch",
        TARGET,
        supplied_html=FULL_SNAPSHOT,
        supplied_from="https://archive.ph/newest/" + TARGET,
    )

    assert result.capture_source == "archive.today"
    assert result.paywalled is True
    assert result.capture_url.startswith("https://archive.ph/")
    assert result.word_count > 100
    # Already an archive copy — no point asking the mirrors again.
    assert not mirrors.called


@respx.mock
async def test_an_unresolvable_paywall_raises_a_paywalled_error(storage_root):
    from app.services.ingest.types import PaywalledError

    respx.get(TARGET).mock(return_value=httpx.Response(403))
    _mock_all_archive_mirrors(lambda request: httpx.Response(429, text=CAPTCHA_PAGE))
    respx.get(url__startswith="https://archive.org/wayback/available").mock(
        return_value=httpx.Response(200, json={"archived_snapshots": {}})
    )

    with pytest.raises(PaywalledError):
        await capture_article("web_hardgate", TARGET)


# --- articles split across containers -----------------------------------------


def _half(start: int, count: int = 14) -> str:
    return " ".join(
        f"Paragraph {i} of the report covers a distinct development and its "
        f"consequences for the parties involved."
        for i in range(start, start + count)
    )


SPLIT_PAGE = f"""<!DOCTYPE html>
<html><head><title>Split Report</title>
<meta property="og:description" content="A report published across two containers.">
</head><body>
  <nav><a href="/">Home</a></nav>
  <article class="body-first"><h1>Split Report</h1><p>{_half(1)}</p></article>
  <aside class="advert">Sponsored</aside>
  <div class="body-second"><p>{_half(40)}</p>
  <p>This story originally appeared elsewhere.</p></div>
  <footer>Copyright</footer>
</body></html>
"""


def test_an_article_split_across_containers_is_merged():
    """Each extractor confidently returns a different half; neither is truncated
    and neither is wrong, so choosing between them loses real text either way."""
    got = extract_article(SPLIT_PAGE, "https://news.example/split")
    assert got is not None
    assert "Paragraph 1 of the report" in got.text, "lost the opening"
    assert "Paragraph 40 of the report" in got.text, "lost the continuation"
    assert "originally appeared elsewhere" in got.text, "lost the ending"


def test_merging_keeps_document_order():
    got = extract_article(SPLIT_PAGE, "https://news.example/split")
    assert got is not None
    assert got.text.index("Paragraph 1 of") < got.text.index("Paragraph 40 of")


def test_a_normal_article_is_not_merged():
    """Both extractors covering the same text must not be concatenated."""
    body = "".join(f"<p>{s}.</p>" for s in _half(1, 20).split(". "))
    html = f"<html><head><title>Plain</title></head><body><article>{body}</article></body></html>"
    got = extract_article(html, "https://news.example/plain")
    assert got is not None
    # A merge would roughly double the count by repeating the same paragraphs.
    assert got.text.count("Paragraph 1 of the report") == 1


def test_merge_order_survives_typographic_punctuation():
    """Regression: the real page's opening half began "Romania’s …". Tokenising
    the needle but not the haystack lost the match, so the position lookup fell
    back to its default and the two halves were concatenated in reverse."""
    from app.services.ingest.article import ExtractedArticle, _merge_split_article

    def _part(text: str) -> ExtractedArticle:
        return ExtractedArticle(
            html=f"<p>{text}</p>", text=text, word_count=len(text.split())
        )

    # The page uses a curly apostrophe; the extraction carries a straight one.
    page = "In the final weeks before Romania’s vote, turnout rose. Later, the court ruled access should have been granted."
    opening = _part("In the final weeks before Romania's vote, turnout rose.")
    ending = _part("Later, the court ruled access should have been granted.")

    # Passed in the wrong order on purpose: the merge must reorder them.
    merged = _merge_split_article(page, ending, opening)
    assert merged.text.index("final weeks") < merged.text.index("the court ruled")


def test_position_lookup_matches_across_punctuation_styles():
    from app.services.ingest.article import _normalised_words, _position_in

    page = _normalised_words("Before that, Romania’s presidential vote was held.")
    # The extraction carries the same words with a different apostrophe.
    assert _position_in(page, "Romania's presidential vote was held") < (1 << 30)


def test_a_merged_article_survives_rewriting_and_sanitising():
    """Regression: the merge produced two root elements, and lxml — used by
    rewrite_urls — keeps only the first, so the second half was dropped again
    on its way to disk. Extraction alone looked correct."""
    from app.services.ingest.sanitize import rewrite_urls, sanitize_article_html

    got = extract_article(SPLIT_PAGE, "https://news.example/split")
    assert got is not None

    stored = sanitize_article_html(
        rewrite_urls(
            got.html,
            base_url="https://news.example/split",
            item_id="web_split",
            asset_map={},
        )
    )
    assert "Paragraph 1 of the report" in stored, "lost the opening on the way to disk"
    assert "Paragraph 40 of the report" in stored, "lost the continuation"
    assert "originally appeared elsewhere" in stored, "lost the ending"


@respx.mock
async def test_a_split_article_is_stored_whole(storage_root):
    """End to end: what lands in articles/<id>/article.html has both halves."""
    respx.get("https://news.example/split").mock(
        return_value=httpx.Response(200, text=SPLIT_PAGE)
    )
    result = await capture_article("web_splitcap", "https://news.example/split")
    stored = (storage_root / result.article_rel).read_text()
    assert "Paragraph 1 of the report" in stored
    assert "originally appeared elsewhere" in stored
    assert stored.index("Paragraph 1 of") < stored.index("originally appeared")
