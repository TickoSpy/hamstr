"""Reader-view capture of a web page.

Fetch -> extract the article -> download its images -> rewrite -> sanitize ->
store. The sanitized file on disk is literally the sanitizer's output, so nothing
downstream has to trust the origin's markup.
"""

import asyncio
import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from urllib.parse import urlsplit

import httpx

from app.config import settings
from app.services.ingest.archive import (
    archive_today_urls,
    fetch_archive_snapshot,
    strip_wayback_chrome,
    wayback_snapshot_url,
)
from app.services.ingest.paywall import (
    HARD_STATUS_CODES,
    STUB_WORD_COUNT,
    detect_paywall,
)
from app.services.ingest.dispatch import needs_redirect_resolution, readable_url
from app.services.ingest.http import (
    IngestHttpError,
    build_client,
    describe_http_error,
    resolve_final_url,
    safe_get,
)
from app.services.images import ASSET_MAX_WIDTH, make_thumbnail, shrink_if_oversized
from app.services.ingest.sniff import image_size
from app.services.ingest.structured import (
    extract_declared_metadata,
    extract_structured,
)
from app.services.ingest.sanitize import (
    asset_filename,
    collect_image_urls,
    normalize_media_tags,
    rewrite_urls,
    sanitize_article_html,
)
from app.services.ingest.types import IngestError, PaywalledError
from app.services.paths import storage_dir
from app.services.urlsafety import assert_safe_url

logger = logging.getLogger(__name__)

# Below this, extraction is treated as having failed rather than succeeded with a
# short article — real articles clear it comfortably, stubs don't.
MIN_ARTICLE_CHARS = 200

_WORD_RE = re.compile(r"\b[\w'’-]+\b", re.UNICODE)
_TAG_RE = re.compile(r"<[^>]+>")


@dataclass
class ExtractedArticle:
    html: str
    text: str
    word_count: int
    title: str | None = None
    byline: str | None = None
    site_name: str | None = None
    published: str | None = None
    excerpt: str | None = None
    lead_image_url: str | None = None


@dataclass
class ArticleResult:
    raw_rel: str
    capture_source: str
    capture_url: str
    article_rel: str | None = None
    thumb_rel: str | None = None
    title: str | None = None
    byline: str | None = None
    site_name: str | None = None
    published: str | None = None
    excerpt: str | None = None
    word_count: int = 0
    paywalled: bool = False
    asset_names: list[str] = field(default_factory=list)
    bytes_total: int = 0


def _count_words(text: str) -> int:
    return len(_WORD_RE.findall(text or ""))


def _text_of(html: str) -> str:
    return _TAG_RE.sub(" ", html or "")


def _meta_fallbacks(raw_html: str) -> dict[str, str | None]:
    """og:*/meta values, used when the extractor doesn't supply them itself."""
    out: dict[str, str | None] = {
        "title": None,
        "description": None,
        "site_name": None,
        "image": None,
    }
    try:
        from lxml import html as lxml_html

        doc = lxml_html.fromstring(raw_html)
    except Exception:
        return out

    def _meta(*keys: str) -> str | None:
        for key in keys:
            for attr in ("property", "name"):
                nodes = doc.xpath(f"//meta[@{attr}=$k]/@content", k=key)
                if nodes and nodes[0].strip():
                    return nodes[0].strip()
        return None

    out["title"] = _meta("og:title", "twitter:title")
    out["description"] = _meta("og:description", "twitter:description", "description")
    out["site_name"] = _meta("og:site_name", "application-name")
    out["image"] = _meta("og:image", "og:image:url", "twitter:image")

    if not out["title"]:
        titles = doc.xpath("//title/text()")
        if titles:
            out["title"] = titles[0].strip() or None

    return out


_SENTENCE_END = re.compile(r"[.!?…»\"'\u201d\u2019)\]]\s*$")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")

# How much a truncated extraction is discounted when scoring. Losing the end of
# an article is a real defect, but not worth trading a whole article for a stub.
_TRUNCATION_PENALTY = 0.6
# Repeated blocks shorter than this are ordinary phrasing, not duplication.
_DEDUPE_MIN_CHARS = 60


def _is_truncated(text: str) -> bool:
    """True when an extraction stops mid-sentence.

    Extractors sometimes drop the tail of the final block (trafilatura does this
    on Slashdot), which silently loses the end of the article.
    """
    stripped = (text or "").strip()
    if len(stripped) < 40:
        return False
    return not _SENTENCE_END.search(stripped)


def _deduplicated_word_count(text: str) -> int:
    """Word count ignoring repeated sentences.

    An extractor that emits the same passage twice would otherwise look like it
    found more content than one that got it right.
    """
    seen: set[str] = set()
    total = 0
    for sentence in _SENTENCE_SPLIT.split(text or ""):
        key = " ".join(sentence.split()).lower()
        if len(key) >= _DEDUPE_MIN_CHARS and key in seen:
            continue
        seen.add(key)
        total += len(_WORD_RE.findall(sentence))
    return total


def _score(article: "ExtractedArticle") -> float:
    """Rank two extractions of the same page against each other."""
    score = float(_deduplicated_word_count(article.text))
    if _is_truncated(article.text):
        score *= _TRUNCATION_PENALTY
    return score


def _extract_trafilatura(html: str, url: str, meta: dict) -> "ExtractedArticle | None":
    try:
        import trafilatura

        body = trafilatura.extract(
            html,
            output_format="html",
            include_images=True,
            include_links=True,
            include_tables=True,
            include_formatting=True,
            favor_precision=True,
            url=url,
        )
        if not body:
            return None

        meta_obj = None
        try:
            meta_obj = trafilatura.extract_metadata(html, default_url=url)
        except Exception:
            logger.debug("trafilatura metadata failed for %s", url, exc_info=True)

        body = normalize_media_tags(body)
        text = _text_of(body)
        return ExtractedArticle(
            html=body,
            text=text,
            word_count=_count_words(text),
            title=(getattr(meta_obj, "title", None) or meta["title"]),
            byline=getattr(meta_obj, "author", None),
            site_name=(getattr(meta_obj, "sitename", None) or meta["site_name"]),
            published=getattr(meta_obj, "date", None),
            excerpt=(getattr(meta_obj, "description", None) or meta["description"]),
            lead_image_url=(getattr(meta_obj, "image", None) or meta["image"]),
        )
    except Exception:
        logger.debug("trafilatura extraction failed for %s", url, exc_info=True)
        return None


def _extract_structured(html: str, url: str, meta: dict) -> "ExtractedArticle | None":
    """Article text the page shipped as JSON, for client-rendered pages."""
    found = extract_structured(html)
    if found is None:
        return None
    return ExtractedArticle(
        html=found.html,
        text=found.text,
        word_count=_count_words(found.text),
        title=found.title or meta["title"],
        byline=found.byline,
        site_name=meta["site_name"],
        published=found.published,
        excerpt=found.excerpt or meta["description"],
        lead_image_url=found.image or meta["image"],
    )


def _extract_readability(html: str, url: str, meta: dict) -> "ExtractedArticle | None":
    try:
        from readability import Document

        doc = Document(html)
        body = doc.summary(html_partial=True)
        if not body:
            return None
        text = _text_of(body)
        return ExtractedArticle(
            html=body,
            text=text,
            word_count=_count_words(text),
            title=(doc.short_title() or meta["title"]),
            byline=None,
            site_name=meta["site_name"],
            published=None,
            excerpt=meta["description"],
            lead_image_url=meta["image"],
        )
    except Exception:
        logger.debug("readability extraction failed for %s", url, exc_info=True)
        return None


_SHINGLE_WORD = re.compile(r"[a-z0-9]+")
# Straight and typographic apostrophes are dropped rather than treated as word
# characters, so "Romania's" and "Romania’s" tokenise identically. The same page
# routinely uses one in its markup and the other in an extractor's output.
_APOSTROPHES = str.maketrans("", "", "'\u2018\u2019\u02bc`\u00b4")
_SHINGLE_SIZE = 6
# Below this in both directions, the two extractions share nothing at all.
_DISJOINT_THRESHOLD = 0.15
# Each half has to be substantial before concatenating is better than choosing.
_SPLIT_MIN_WORDS = 120


def _tokens(text: str) -> list[str]:
    return _SHINGLE_WORD.findall((text or "").lower().translate(_APOSTROPHES))


def _shingles(text: str) -> set[tuple[str, ...]]:
    words = _tokens(text)
    n = _SHINGLE_SIZE
    return {tuple(words[i : i + n]) for i in range(max(0, len(words) - n + 1))}


def _containment(a: str, b: str) -> float:
    """Fraction of a's word shingles that also occur in b."""
    sa, sb = _shingles(a), _shingles(b)
    return (len(sa & sb) / len(sa)) if sa else 1.0


def _normalised_words(text: str) -> str:
    """Lowercased words joined by single spaces, punctuation dropped."""
    return " ".join(_tokens(text))


def _position_in(haystack_words: str, needle: str) -> int:
    """Where a snippet of extracted text falls in the original page.

    Both sides go through the same tokeniser on purpose: comparing raw text
    against tokenised text fails on any typographic character the tokeniser
    normalises away — a curly apostrophe in "Romania's" was enough to lose the
    match and silently invert the merge order.
    """
    words = _tokens(needle)[:8]
    if not words:
        return 1 << 30
    idx = haystack_words.find(" ".join(words))
    return idx if idx >= 0 else 1 << 30


def _inner_html(fragment: str) -> str:
    """The children of a fragment's outermost wrapper, serialised."""
    try:
        from lxml import html as lxml_html

        node = lxml_html.fromstring(fragment)
    except Exception:
        return fragment

    # Unwrap html/body wrappers so the pieces can be concatenated.
    while node.tag in ("html", "body") and len(node):
        if node.tag == "html":
            body = node.find("body")
            node = body if body is not None else node[0]
        else:
            break

    parts = [node.text or ""]
    parts += [
        lxml_html.tostring(child, encoding="unicode")
        for child in node
        if child.tag not in ("script", "style")
    ]
    return "".join(parts)


def _merge_split_article(
    page_text: str, a: "ExtractedArticle", b: "ExtractedArticle"
) -> "ExtractedArticle":
    """Concatenate two extractions that cover different parts of one article.

    Some layouts break the body across sibling containers (Ars Technica does),
    and each extractor then confidently returns a different half. Neither is
    truncated and neither is wrong — they are just incomplete, so choosing
    between them loses real text either way.
    """
    haystack = _normalised_words(page_text)
    pos_a, pos_b = _position_in(haystack, a.text), _position_in(haystack, b.text)
    # `a` is trafilatura, so an unresolved position keeps the usual order.
    first, second = (a, b) if pos_a <= pos_b else (b, a)

    # Must be a single root. Each extractor returns its own <html>/<body>
    # wrapper, and lxml — used by rewrite_urls further down — keeps only the
    # first element of a multi-root fragment, which silently dropped the second
    # half again after the merge had correctly found it.
    html = f"<div>{_inner_html(first.html)}\n{_inner_html(second.html)}</div>"
    text = _text_of(html)
    merged = ExtractedArticle(
        html=html,
        text=text,
        word_count=_count_words(text),
        title=a.title or b.title,
        byline=a.byline or b.byline,
        site_name=a.site_name or b.site_name,
        published=a.published or b.published,
        excerpt=a.excerpt or b.excerpt,
        lead_image_url=a.lead_image_url or b.lead_image_url,
    )
    return merged


def _is_defective(article: "ExtractedArticle") -> bool:
    """Whether an extraction shows a known failure mode.

    trafilatura is the more precise extractor — it excludes nav and boilerplate
    that readability keeps — so it stays the default. But on some layouts it
    duplicates a passage and drops the final sentence (Slashdot does both), and
    those are worth handing over to the other extractor for.
    """
    if _is_truncated(article.text):
        return True
    total = _count_words(article.text)
    return total > 0 and _deduplicated_word_count(article.text) < total * 0.9


def extract_article(html: str, url: str) -> ExtractedArticle | None:
    """Pull the readable article out of a page.

    trafilatura wins by default because it is stricter about page chrome.
    readability is consulted when trafilatura returns nothing, or returns
    something visibly damaged — previously it never got a chance, so a truncated
    or duplicated extraction was stored as-is.
    """
    meta = _meta_fallbacks(html)

    def _usable(c: "ExtractedArticle | None") -> "ExtractedArticle | None":
        return c if c and len(c.text.strip()) >= MIN_ARTICLE_CHARS else None

    # Publishers declare byline/date/description in JSON-LD; the DOM extractors
    # only guess at them. This is read whether or not the payload also carries
    # the article body, so a server-rendered page still gets a real byline.
    declared_meta = extract_declared_metadata(html)
    declared = (
        ExtractedArticle(
            html="",
            text="",
            word_count=0,
            title=declared_meta.title or meta["title"],
            byline=declared_meta.byline,
            site_name=meta["site_name"],
            published=declared_meta.published,
            excerpt=declared_meta.excerpt or meta["description"],
            lead_image_url=declared_meta.image or meta["image"],
        )
        if declared_meta is not None
        else None
    )

    primary = _usable(_extract_trafilatura(html, url, meta))
    readable = _usable(_extract_readability(html, url, meta))

    # A body split across sibling containers gives each extractor a different
    # half. Both look clean, so scoring would just pick one and drop the rest.
    if (
        primary is not None
        and readable is not None
        and primary.word_count >= _SPLIT_MIN_WORDS
        and readable.word_count >= _SPLIT_MIN_WORDS
        and _containment(primary.text, readable.text) < _DISJOINT_THRESHOLD
        and _containment(readable.text, primary.text) < _DISJOINT_THRESHOLD
    ):
        page_text = _text_of(html)
        logger.info("Article at %s is split across containers; merging", url)
        return _merge_metadata(
            _merge_split_article(page_text, primary, readable), declared
        )

    if primary is not None and not _is_defective(primary):
        return _merge_metadata(primary, declared)

    # Client-rendered pages leave the DOM extractors nothing to work with, but
    # the content is usually still in the page as JSON.
    others = [
        c
        for c in (
            readable,
            _usable(_extract_structured(html, url, meta)),
        )
        if c is not None
    ]
    if not others:
        return primary

    candidates = others if primary is None else [primary, *others]
    best = max(candidates, key=_score)

    # Only trafilatura reports metadata; let the winner borrow it.
    for other in candidates:
        if other is best:
            continue
        for field_name in (
            "title",
            "byline",
            "site_name",
            "published",
            "excerpt",
            "lead_image_url",
        ):
            if getattr(best, field_name) is None:
                setattr(best, field_name, getattr(other, field_name))

    return _merge_metadata(best, declared)


def _merge_metadata(
    article: "ExtractedArticle", source: "ExtractedArticle | None"
) -> "ExtractedArticle":
    """Fill in whatever the winning extraction couldn't determine itself."""
    if source is None:
        return article
    for field_name in ("title", "byline", "published", "excerpt", "lead_image_url"):
        if getattr(article, field_name) is None:
            setattr(article, field_name, getattr(source, field_name))
    return article


async def _download_asset(
    client: httpx.AsyncClient,
    url: str,
    dest_dir,
    budget: dict,
    semaphore: asyncio.Semaphore,
) -> tuple[str, str] | None:
    """Fetch one image. Returns (source_url, local_name) or None on any failure."""
    async with semaphore:
        if budget["remaining"] <= 0:
            return None
        try:
            await assert_safe_url(url)
            response = await safe_get(
                client,
                url,
                max_bytes=min(settings.max_article_image_bytes, budget["remaining"]),
                timeout=10.0,
            )
            response.raise_for_status()
        except Exception as exc:
            logger.debug("Asset %s skipped: %s", url, exc)
            return None

        data = response.content
        if not data:
            return None

        name = asset_filename(url, response.headers.get("content-type"))
        try:
            (dest_dir / name).write_bytes(data)
        except OSError as exc:
            logger.debug("Could not write asset %s: %s", name, exc)
            return None

        # Publishers ship 3000px originals for a column that renders at ~680px.
        dimensions = image_size(data)
        if dimensions and dimensions[0] > ASSET_MAX_WIDTH:
            await shrink_if_oversized(dest_dir / name)
            try:
                dimensions = image_size((dest_dir / name).read_bytes()) or dimensions
            except OSError:
                pass

        try:
            stored = (dest_dir / name).stat().st_size
        except OSError:
            stored = len(data)
        budget["remaining"] -= stored
        budget["written"] += stored
        if dimensions:
            budget["sizes"][name] = dimensions
        return url, name


async def _download_assets(
    client: httpx.AsyncClient, urls: list[str], item_id: str
) -> tuple[dict[str, str], int, dict[str, tuple[int, int]]]:
    if not urls:
        return {}, 0, {}

    dest_dir = storage_dir("articles", item_id) / "assets"
    dest_dir.mkdir(parents=True, exist_ok=True)

    budget: dict = {
        "remaining": settings.max_article_assets_bytes,
        "written": 0,
        "sizes": {},
    }
    semaphore = asyncio.Semaphore(4)

    results = await asyncio.gather(
        *[_download_asset(client, u, dest_dir, budget, semaphore) for u in urls]
    )
    return (
        {src: name for src, name in filter(None, results)},
        budget["written"],
        budget["sizes"],
    )


async def _store_thumbnail(
    client: httpx.AsyncClient, image_url: str | None, item_id: str
) -> str | None:
    if not image_url:
        return None
    try:
        await assert_safe_url(image_url)
        response = await safe_get(
            client, image_url, max_bytes=settings.max_article_image_bytes, timeout=10.0
        )
        response.raise_for_status()
        if not response.content:
            return None
    except Exception as exc:
        logger.debug("Lead image %s skipped: %s", image_url, exc)
        return None

    thumb_dir = storage_dir("thumbnails", item_id)
    content_type = response.headers.get("content-type") or ""
    suffix = ".png" if "png" in content_type else ".jpg"
    original = thumb_dir / f"source{suffix}"
    original.write_bytes(response.content)

    # The lead image is often full-bleed hero art; the grid shows it at ~300px.
    thumb = await make_thumbnail(original, thumb_dir)
    if thumb is None:
        # Whatever ffmpeg couldn't read, keep as-is: a heavy thumbnail still
        # beats no thumbnail.
        logger.debug("Could not downscale the lead image for %s", item_id)
        return str(original.relative_to(settings.storage_root.resolve()))

    original.unlink(missing_ok=True)
    return str(thumb.relative_to(settings.storage_root.resolve()))


async def _fetch_page(client: httpx.AsyncClient, url: str) -> httpx.Response:
    try:
        response = await safe_get(client, url, max_bytes=settings.max_article_bytes)
        response.raise_for_status()
        return response
    except (httpx.HTTPError, IngestHttpError) as exc:
        raise IngestError(describe_http_error(exc)) from exc


# Interstitials that return HTTP 200 with no article on them. Archiving one as a
# "successful" 26-word page is worse than failing: the row looks fine and the
# content is gone.
_BOT_WALL_MARKERS = (
    "please wait for verification",
    "checking your browser before accessing",
    "enable javascript and cookies to continue",
    "just a moment...",
    "verifying you are human",
    "cf-browser-verification",
    "captcha-delivery.com",
    "px-captcha",
)


def looks_like_bot_wall(html: str, extracted: "ExtractedArticle | None") -> bool:
    """A JS bot-check served in place of the page."""
    if extracted is not None and extracted.word_count >= 120:
        return False  # real content came through; markers are incidental
    lowered = (html or "")[:6000].lower()
    return any(marker in lowered for marker in _BOT_WALL_MARKERS)


_STATUS_IN_MESSAGE = re.compile(r"Fetch failed: (\d{3})")


def _status_from_message(message: str) -> int:
    """Recover the HTTP status from a describe_http_error() string."""
    match = _STATUS_IN_MESSAGE.search(message)
    return int(match.group(1)) if match else 0


async def _try_archives(
    client: httpx.AsyncClient, url: str, *, direct_words: int
) -> tuple[ExtractedArticle, str, str, str] | None:
    """Look for a fuller copy of a gated article.

    Returns (extraction, capture_source, capture_url, snapshot_html), or None if
    no mirror produced anything better than what we already have.
    """
    if not settings.archive_enabled:
        return None

    # Accept a snapshot only if it beats both the stub threshold and whatever the
    # origin already gave us — otherwise we'd trade a partial article for a worse one.
    threshold = max(STUB_WORD_COUNT, direct_words + 1)

    # Mirrors are tried sequentially: they share a backend, so firing in parallel
    # just reaches the rate limit sooner.
    for mirror in archive_today_urls(url):
        html = await fetch_archive_snapshot(client, mirror)
        if not html:
            continue
        extracted = extract_article(html, mirror)
        if extracted and extracted.word_count >= threshold:
            logger.info("Recovered %s from %s", url, mirror)
            return extracted, "archive.today", mirror, html

    snapshot_url = await wayback_snapshot_url(client, url)
    if snapshot_url:
        html = await fetch_archive_snapshot(client, snapshot_url, timeout=20.0)
        if html:
            html = strip_wayback_chrome(html)
            extracted = extract_article(html, snapshot_url)
            if extracted and extracted.word_count >= threshold:
                logger.info("Recovered %s from the Wayback Machine", url)
                return extracted, "wayback", snapshot_url, html

    return None


async def capture_article(
    item_id: str,
    url: str,
    on_progress: Callable[[float], Awaitable[None]] | None = None,
    supplied_html: str | None = None,
    supplied_from: str | None = None,
) -> ArticleResult:
    """Store a reader-ready, ad-free copy of a page.

    `supplied_html` is a capture from the browser extension: markup the user's
    own browser already rendered and was authorised to see, so nothing is
    fetched. It is still checked for a paywall — capturing while logged out
    yields the same teaser the server would have got, and silently storing that
    as a success is the worst outcome.

    `supplied_from` marks the capture as coming from an archive mirror the
    browser fetched on our behalf. archive.today CAPTCHAs this server every
    time but answers a real browser, so that is the only way we ever get a copy
    from it.
    """

    async def _report(pct: float) -> None:
        if on_progress is not None:
            await on_progress(pct)

    article_dir = storage_dir("articles", item_id)

    async with build_client() as client:
        status_code = 200

        if supplied_html is not None:
            raw_html, final_url = supplied_html, url
        else:
            # Share/short links must be resolved on their own host first: the
            # reader host doesn't understand them and bounces them to a login
            # page. Resolve, then rewrite.
            canonical = url
            if needs_redirect_resolution(url):
                canonical = await resolve_final_url(client, url)
                if canonical != url:
                    logger.info("Resolved %s to %s", url, canonical)

            # Some hosts answer plain HTTP clients with a JS wall but keep a
            # server-rendered copy elsewhere (www.reddit.com -> old.reddit.com).
            fetch_url = readable_url(canonical)
            if fetch_url != url:
                logger.info("Fetching %s via %s", url, fetch_url)

            try:
                response = await _fetch_page(client, fetch_url)
                raw_html = response.text
                final_url = str(response.url)
            except IngestError as exc:
                # A 401/402/403/451 is itself a paywall signal — don't give up
                # before trying the archives.
                status_code = _status_from_message(str(exc))
                if status_code not in HARD_STATUS_CODES:
                    raise
                logger.info(
                    "Direct fetch of %s refused (%s); trying archives", url, exc
                )
                raw_html, final_url = "", url

        await _report(10.0)

        (article_dir / "raw.html").write_text(raw_html, encoding="utf-8")
        raw_rel = str(
            (article_dir / "raw.html").relative_to(settings.storage_root.resolve())
        )

        extracted = extract_article(raw_html, final_url) if raw_html else None
        await _report(30.0)

        if supplied_html is None and looks_like_bot_wall(raw_html, extracted):
            raise IngestError(
                "The site served a bot check instead of the page — "
                "no readable content to archive"
            )

        if supplied_from:
            source = "archive.today" if "archive." in supplied_from else "wayback"
        elif supplied_html is not None:
            source = "extension"
        else:
            source = "direct"

        result = ArticleResult(
            raw_rel=raw_rel,
            capture_source=source,
            capture_url=supplied_from or final_url,
            site_name=urlsplit(final_url).hostname or None,
            paywalled=bool(supplied_from),
        )

        # Run this for extension captures too: capturing while logged out yields
        # the same teaser the server would have got, and silently archiving that
        # as a success is the worst outcome.
        verdict = detect_paywall(
            status_code=status_code, html=raw_html, extracted=extracted
        )
        if verdict.paywalled and not supplied_from:
            logger.info("Paywall suspected for %s: %s", url, verdict.reason)
            result.paywalled = True
            replacement = await _try_archives(
                client, url, direct_words=getattr(extracted, "word_count", 0) or 0
            )
            if replacement is not None:
                extracted, source, capture_url, snapshot_html = replacement
                result.capture_source = source
                result.capture_url = capture_url
                final_url = capture_url
                (article_dir / "raw.html").write_text(snapshot_html, encoding="utf-8")
                raw_html = snapshot_html
            elif not raw_html:
                # The origin refused outright and no mirror had a copy, so there
                # is genuinely nothing to keep.
                raise PaywalledError(
                    "Paywalled — no readable copy on archive.today "
                    f"({len(settings.archive_today_hosts)} mirrors) "
                    "or the Wayback Machine"
                )
            else:
                # We at least have the teaser and the headline; keeping those
                # beats a red row the user has to go re-find the link for.
                logger.info("Archives had nothing better for %s; keeping the stub", url)

        await _report(50.0)

        if extracted is None:
            # A saved raw page beats a red error row — the reader falls back to a
            # sandboxed iframe of raw.html.
            logger.info("No article extracted from %s; keeping raw.html only", url)
            meta = _meta_fallbacks(raw_html)
            result.title = meta["title"]
            result.excerpt = meta["description"]
            await _report(100.0)
            return result

        result.title = extracted.title
        result.byline = extracted.byline
        result.site_name = extracted.site_name or result.site_name
        result.published = extracted.published
        result.excerpt = extracted.excerpt
        result.word_count = extracted.word_count

        image_urls = collect_image_urls(
            extracted.html, final_url, settings.max_article_images
        )
        asset_map, asset_bytes, asset_sizes = await _download_assets(
            client, image_urls, item_id
        )
        await _report(75.0)

        result.thumb_rel = await _store_thumbnail(
            client, extracted.lead_image_url, item_id
        )
        await _report(90.0)

    # Rewrite first, sanitize last: what lands on disk is exactly the sanitizer's
    # output, with every <img> already pointing at a local asset.
    rewritten = rewrite_urls(
        extracted.html,
        base_url=final_url,
        item_id=item_id,
        asset_map=asset_map,
        asset_sizes=asset_sizes,
    )
    clean = sanitize_article_html(rewritten)

    (article_dir / "article.html").write_text(clean, encoding="utf-8")
    result.article_rel = str(
        (article_dir / "article.html").relative_to(settings.storage_root.resolve())
    )
    result.asset_names = sorted(asset_map.values())
    result.bytes_total = (
        len(clean.encode("utf-8")) + len(raw_html.encode("utf-8")) + asset_bytes
    )

    await _report(100.0)
    return result
