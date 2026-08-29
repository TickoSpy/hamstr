"""Turn extracted article markup into something safe to render in our own origin.

nh3 (Rust/ammonia) is allowlist-based, so `<script>`, `on*` handlers,
`javascript:` URLs, `<iframe>`, `<object>` and `<form>` are impossible by
construction rather than removed by pattern-matching. That property is the whole
reason the reader can inject this HTML directly instead of sandboxing it.

`class`, `style` and `id` are deliberately stripped: the reader styles by tag
selector, so they buy nothing and cost CSS-injection and layout-hijack surface.
"""

import hashlib
import logging
import re
from urllib.parse import urljoin, urlsplit

import nh3
from lxml import html as lxml_html

logger = logging.getLogger(__name__)

ALLOWED_TAGS: set[str] = {
    "p",
    "br",
    "hr",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "strong",
    "em",
    "b",
    "i",
    "u",
    "s",
    "sup",
    "sub",
    "blockquote",
    "q",
    "cite",
    "pre",
    "code",
    "kbd",
    "samp",
    "ul",
    "ol",
    "li",
    "dl",
    "dt",
    "dd",
    "table",
    "thead",
    "tbody",
    "tfoot",
    "tr",
    "th",
    "td",
    "caption",
    "figure",
    "figcaption",
    "img",
    "a",
    "span",
    "div",
    "time",
    "mark",
    "abbr",
    "del",
    "ins",
}

ALLOWED_ATTRIBUTES: dict[str, set[str]] = {
    "a": {"href", "title", "target"},
    "img": {"src", "alt", "title", "width", "height"},
    "td": {"colspan", "rowspan"},
    "th": {"colspan", "rowspan", "scope"},
    "time": {"datetime"},
    "ol": {"start"},
    "abbr": {"title"},
}

IMAGE_EXTENSIONS = frozenset(
    {".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif", ".svg"}
)

_EXT_BY_MIME = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/avif": ".avif",
    "image/svg+xml": ".svg",
}

_SRCSET_ENTRY = re.compile(r"\s*(?P<url>\S+)(?:\s+(?P<w>[\d.]+)[wx])?\s*")


def sanitize_article_html(html: str) -> str:
    """Reduce arbitrary markup to the reader's allowlist."""
    return nh3.clean(
        html,
        tags=ALLOWED_TAGS,
        attributes={k: set(v) for k, v in ALLOWED_ATTRIBUTES.items()},
        url_schemes={"http", "https"},
        link_rel="noopener noreferrer nofollow",
        strip_comments=True,
    )


def asset_filename(url: str, mime: str | None = None) -> str:
    """Stable, collision-free local name for a downloaded image."""
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    ext = ""
    try:
        path = urlsplit(url).path
        candidate = "." + path.rsplit(".", 1)[-1].lower() if "." in path else ""
        if candidate in IMAGE_EXTENSIONS:
            ext = candidate
    except ValueError:
        pass
    if not ext and mime:
        ext = _EXT_BY_MIME.get(mime.split(";", 1)[0].strip().lower(), "")
    return digest + (ext or ".img")


def best_srcset_url(srcset: str, base_url: str) -> str | None:
    """The highest-resolution candidate in a srcset attribute."""
    best: tuple[float, str] | None = None
    for part in srcset.split(","):
        m = _SRCSET_ENTRY.fullmatch(part)
        if not m or not m.group("url"):
            continue
        try:
            width = float(m.group("w")) if m.group("w") else 1.0
        except ValueError:
            width = 1.0
        if best is None or width > best[0]:
            best = (width, m.group("url"))
    return urljoin(base_url, best[1]) if best else None


def normalize_media_tags(html: str) -> str:
    """Rename trafilatura's ``<graphic>`` elements to ``<img>``.

    trafilatura's HTML output uses its own ``<graphic src=… alt=…/>`` tag rather
    than ``<img>``; without this, no article image is ever collected or archived,
    and the sanitizer's allowlist drops them silently.
    """
    if "<graphic" not in html:
        return html
    try:
        doc = lxml_html.fromstring(html)
    except Exception:
        return html
    for node in doc.iter("graphic"):
        node.tag = "img"
    return lxml_html.tostring(doc, encoding="unicode")


def collect_image_urls(html: str, base_url: str, limit: int) -> list[str]:
    """Absolute URLs of every <img> worth downloading, in document order.

    Handles the lazy-loading attributes real sites use — a plain `src` is often
    a 1px placeholder with the real image in `data-src` or `srcset`.
    """
    try:
        doc = lxml_html.fromstring(html)
    except Exception:
        return []

    urls: list[str] = []
    seen: set[str] = set()

    for img in doc.iter("img"):
        candidate: str | None = None
        for attr in ("srcset", "data-srcset"):
            value = img.get(attr)
            if value:
                candidate = best_srcset_url(value, base_url)
                if candidate:
                    break
        if not candidate:
            for attr in ("data-src", "data-original", "data-lazy-src", "src"):
                value = img.get(attr)
                if value and not value.startswith("data:"):
                    candidate = urljoin(base_url, value)
                    break
        if not candidate:
            continue
        if urlsplit(candidate).scheme not in ("http", "https"):
            continue
        if candidate in seen:
            continue
        seen.add(candidate)
        urls.append(candidate)
        if len(urls) >= limit:
            break

    return urls


def _drop_keeping_text(element) -> None:
    """Remove an element without losing the prose that follows it.

    lxml stores text after a tag as that tag's `.tail`, so a plain `remove()`
    would silently delete the rest of the sentence along with the image.
    """
    parent = element.getparent()
    if parent is None:
        return
    tail = element.tail
    if tail:
        previous = element.getprevious()
        if previous is not None:
            previous.tail = (previous.tail or "") + tail
        else:
            parent.text = (parent.text or "") + tail
    parent.remove(element)


def rewrite_urls(
    html: str,
    *,
    base_url: str,
    item_id: str,
    asset_map: dict[str, str],
    asset_sizes: dict[str, tuple[int, int]] | None = None,
) -> str:
    """Absolutize links and point images at their downloaded local copies.

    An <img> whose asset failed to download is removed outright rather than left
    pointing at the origin — reading an archived page must make zero outbound
    requests, which is the entire point of storing it "without ads".
    """
    try:
        doc = lxml_html.fromstring(html)
    except Exception:
        return html

    for img in list(doc.iter("img")):
        local: str | None = None
        for attr in ("srcset", "data-srcset"):
            value = img.get(attr)
            if value:
                candidate = best_srcset_url(value, base_url)
                if candidate and candidate in asset_map:
                    local = asset_map[candidate]
                    break
        if not local:
            for attr in ("data-src", "data-original", "data-lazy-src", "src"):
                value = img.get(attr)
                if not value or value.startswith("data:"):
                    continue
                candidate = urljoin(base_url, value)
                if candidate in asset_map:
                    local = asset_map[candidate]
                    break

        if not local:
            _drop_keeping_text(img)
            continue

        # Drop every source attribute so nothing can reach the network, then set
        # the one we control.
        for attr in (
            "srcset",
            "data-srcset",
            "data-src",
            "data-original",
            "data-lazy-src",
        ):
            img.attrib.pop(attr, None)
        img.set("src", f"/stream/{item_id}/asset/{local}")

        # Intrinsic dimensions let the browser reserve the right space before the
        # image loads. Without them the reader reflows as each one arrives, which
        # reads as images flickering and text jumping while you scroll.
        size = (asset_sizes or {}).get(local)
        if size:
            img.set("width", str(size[0]))
            img.set("height", str(size[1]))
        else:
            img.attrib.pop("width", None)
            img.attrib.pop("height", None)

    for anchor in doc.iter("a"):
        href = anchor.get("href")
        if not href:
            continue
        absolute = urljoin(base_url, href)
        if urlsplit(absolute).scheme in ("http", "https"):
            anchor.set("href", absolute)
            anchor.set("target", "_blank")
        else:
            anchor.attrib.pop("href", None)

    return lxml_html.tostring(doc, encoding="unicode")
