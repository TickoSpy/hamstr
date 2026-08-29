"""Recover article text from data the page already ships.

Most "JavaScript-only" pages are not actually withholding their content — they
render it client-side from a payload that is sitting in the initial HTML:
schema.org JSON-LD, or a framework hydration blob (`__NEXT_DATA__`, `__NUXT__`,
`window.__INITIAL_STATE__`). Reading that is cheaper and more faithful than
driving a browser, and it yields real byline/date fields as a bonus.
"""

import html as html_module
import json
import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Payloads above this are almost certainly whole-site state, not one article.
MAX_PAYLOAD_BYTES = 8 * 1024 * 1024
# Below this a "body" is a teaser, not an article.
MIN_BODY_CHARS = 400

_JSON_LD_RE = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)
_NEXT_DATA_RE = re.compile(
    r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)
# window.__X__ = {...};  — the assignment forms used by Nuxt/Redux/Apollo.
_STATE_ASSIGN_RE = re.compile(
    r"window\.__(?:NUXT|INITIAL_STATE|PRELOADED_STATE|APOLLO_STATE|INITIAL_DATA)__"
    r"\s*=\s*(\{.*?\})\s*[;<]",
    re.DOTALL,
)

# Keys that hold article prose in the wild, most explicit first. A payload can
# have several — "text" is also what a comment thread uses — so an unambiguous
# key beats a longer string under a vaguer one.
_PRIMARY_BODY_KEYS = frozenset(
    {"articlebody", "bodyhtml", "bodytext", "fulltext", "richtext", "story"}
)
_SECONDARY_BODY_KEYS = frozenset({"body", "content", "contenthtml", "html", "text"})
_BODY_KEYS = _PRIMARY_BODY_KEYS | _SECONDARY_BODY_KEYS
_TITLE_KEYS = ("headline", "title", "name")
_AUTHOR_KEYS = ("author", "byline", "creator")
_DATE_KEYS = ("datepublished", "published", "publisheddate", "date", "firstpublished")

_TAG_RE = re.compile(r"<[^>]+>")
_PARAGRAPH_SPLIT = re.compile(r"\n{2,}|\r\n\r\n")


@dataclass
class StructuredArticle:
    html: str
    text: str
    title: str | None = None
    byline: str | None = None
    published: str | None = None
    excerpt: str | None = None
    image: str | None = None
    source: str = "structured"


def _text_of(value: str) -> str:
    return _TAG_RE.sub(" ", value or "")


def _looks_like_prose(value: str) -> bool:
    """Long enough, and punctuated like sentences rather than like an ID blob."""
    if not isinstance(value, str) or len(value) < MIN_BODY_CHARS:
        return False
    plain = _text_of(value)
    if len(plain) < MIN_BODY_CHARS:
        return False
    # Real prose has sentence endings and spaces; base64 and CSS do not.
    if plain.count(" ") < 40:
        return False
    return sum(plain.count(c) for c in ".!?") >= 3


_BLOCK_TAG_RE = re.compile(
    r"<\s*(p|div|section|article|h[1-6]|ul|ol|li|br|blockquote|figure)\b", re.IGNORECASE
)


def _as_paragraph_html(value: str) -> str:
    """Wrap plain text in paragraphs; pass real markup through untouched.

    A stray "<" in prose must not make the whole body count as HTML — it would
    be emitted unescaped and swallow the text after it.
    """
    if _BLOCK_TAG_RE.search(value):
        return value
    parts = [p.strip() for p in _PARAGRAPH_SPLIT.split(value) if p.strip()]
    if not parts:
        parts = [value.strip()]
    return "".join(f"<p>{html_module.escape(p)}</p>" for p in parts)


def _first_string(node: object, keys: tuple[str, ...]) -> str | None:
    """Shallow lookup of the first usable string under any of `keys`."""
    if not isinstance(node, dict):
        return None
    lowered = {k.lower(): v for k, v in node.items()}
    for key in keys:
        value = lowered.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, dict):
            for inner in ("name", "@id", "url"):
                candidate = value.get(inner)
                if isinstance(candidate, str) and candidate.strip():
                    return candidate.strip()
        if isinstance(value, list) and value:
            names = [
                v.get("name") if isinstance(v, dict) else v
                for v in value
                if isinstance(v, (str, dict))
            ]
            names = [n.strip() for n in names if isinstance(n, str) and n.strip()]
            if names:
                return ", ".join(names)
    return None


def _walk_json_ld(html: str) -> StructuredArticle | None:
    """schema.org Article nodes carry the publisher's own `articleBody`."""
    for match in _JSON_LD_RE.finditer(html):
        raw = match.group(1).strip()
        if not raw or len(raw) > MAX_PAYLOAD_BYTES:
            continue
        try:
            data = json.loads(raw)
        except ValueError:
            continue

        stack = [data]
        while stack:
            node = stack.pop()
            if isinstance(node, list):
                stack.extend(node)
                continue
            if not isinstance(node, dict):
                continue
            stack.extend(v for v in node.values() if isinstance(v, (dict, list)))

            body = node.get("articleBody") or node.get("articlebody")
            if not isinstance(body, str) or len(body.strip()) < MIN_BODY_CHARS:
                continue

            body_html = _as_paragraph_html(body.strip())
            image = node.get("image")
            if isinstance(image, dict):
                image = image.get("url")
            if isinstance(image, list) and image:
                image = image[0].get("url") if isinstance(image[0], dict) else image[0]

            return StructuredArticle(
                html=body_html,
                text=_text_of(body_html),
                title=_first_string(node, _TITLE_KEYS),
                byline=_first_string(node, _AUTHOR_KEYS),
                published=_first_string(node, _DATE_KEYS),
                excerpt=_first_string(node, ("description",)),
                image=image if isinstance(image, str) else None,
                source="json-ld",
            )
    return None


# Block-array shapes: {"body": [{"type": "paragraph", "text": "..."}, ...]}
_BLOCK_TEXT_KEYS = ("text", "html", "content", "value")


def _join_blocks(node: object) -> str | None:
    """Reassemble prose from a list of block objects.

    Next.js and friends usually ship an article as an array of typed blocks
    rather than one string, so looking only for long strings misses them.
    """
    if not isinstance(node, list) or not node:
        return None
    parts: list[str] = []
    for item in node:
        if isinstance(item, str):
            parts.append(item)
            continue
        if not isinstance(item, dict):
            continue
        lowered = {k.lower(): v for k, v in item.items()}
        for key in _BLOCK_TEXT_KEYS:
            value = lowered.get(key)
            if isinstance(value, str) and value.strip():
                parts.append(value.strip())
                break
            # One more level: {"model": {"text": "..."}} / {"data": {...}}
            if isinstance(value, dict):
                for inner in _BLOCK_TEXT_KEYS:
                    nested = value.get(inner)
                    if isinstance(nested, str) and nested.strip():
                        parts.append(nested.strip())
                        break
    if not parts:
        return None
    joined = "\n\n".join(parts)
    return joined if _looks_like_prose(joined) else None


def _deepest_prose(payload: object) -> str | None:
    """The longest prose-looking string in a hydration payload.

    Frameworks nest the article at wildly different paths per site, so this looks
    for the content itself rather than trying to know every shape. Preferring
    recognised keys keeps comment threads and related-article blurbs from winning.
    """
    # Tier 0 = unambiguous body key, 1 = plausible key, 2 = anything prose-like.
    best_by_tier: dict[int, tuple[int, str]] = {}
    stack: list[tuple[object, str | None]] = [(payload, None)]
    seen = 0

    def offer(value: str, key: str | None) -> None:
        lowered = (key or "").lower()
        if lowered in _PRIMARY_BODY_KEYS:
            tier = 0
        elif lowered in _SECONDARY_BODY_KEYS:
            tier = 1
        else:
            tier = 2
        current = best_by_tier.get(tier)
        if current is None or len(value) > current[0]:
            best_by_tier[tier] = (len(value), value)

    while stack and seen < 200_000:
        node, key = stack.pop()
        seen += 1
        if isinstance(node, dict):
            stack.extend((v, k) for k, v in node.items())
        elif isinstance(node, list):
            joined = _join_blocks(node)
            if joined:
                offer(joined, key)
            stack.extend((v, key) for v in node)
        elif isinstance(node, str) and _looks_like_prose(node):
            offer(node, key)

    for tier in (0, 1, 2):
        if tier in best_by_tier:
            return best_by_tier[tier][1]
    return None


def _from_hydration(html: str) -> StructuredArticle | None:
    payloads: list[str] = []
    for match in _NEXT_DATA_RE.finditer(html):
        payloads.append(match.group(1))
    for match in _STATE_ASSIGN_RE.finditer(html):
        payloads.append(match.group(1))

    for raw in payloads:
        raw = raw.strip()
        if not raw or len(raw) > MAX_PAYLOAD_BYTES:
            continue
        try:
            data = json.loads(raw)
        except ValueError:
            continue

        body = _deepest_prose(data)
        if not body:
            continue

        body_html = _as_paragraph_html(body)
        return StructuredArticle(
            html=body_html,
            text=_text_of(body_html),
            source="hydration",
        )
    return None


def extract_declared_metadata(html: str) -> StructuredArticle | None:
    """Publisher-declared title/byline/date/description, with or without a body.

    Most news sites ship JSON-LD metadata even when the prose is in the DOM, and
    it is far more reliable than the DOM extractors' guesses at a byline.
    """
    if not html:
        return None
    for match in _JSON_LD_RE.finditer(html):
        raw = match.group(1).strip()
        if not raw or len(raw) > MAX_PAYLOAD_BYTES:
            continue
        try:
            data = json.loads(raw)
        except ValueError:
            continue

        stack = [data]
        while stack:
            node = stack.pop()
            if isinstance(node, list):
                stack.extend(node)
                continue
            if not isinstance(node, dict):
                continue
            stack.extend(v for v in node.values() if isinstance(v, (dict, list)))

            node_type = node.get("@type") or node.get("type") or ""
            types = node_type if isinstance(node_type, list) else [node_type]
            if not any(
                "article" in str(t).lower() or "posting" in str(t).lower()
                for t in types
            ):
                continue

            image = node.get("image")
            if isinstance(image, dict):
                image = image.get("url")
            if isinstance(image, list) and image:
                image = image[0].get("url") if isinstance(image[0], dict) else image[0]

            title = _first_string(node, _TITLE_KEYS)
            byline = _first_string(node, _AUTHOR_KEYS)
            published = _first_string(node, _DATE_KEYS)
            if not any((title, byline, published)):
                continue

            return StructuredArticle(
                html="",
                text="",
                title=title,
                byline=byline,
                published=published,
                excerpt=_first_string(node, ("description",)),
                image=image if isinstance(image, str) else None,
                source="json-ld-meta",
            )
    return None


def extract_structured(html: str) -> StructuredArticle | None:
    """Article content the page shipped as data, or None.

    JSON-LD is tried first: it is the publisher's own declaration of what the
    article is, and it carries metadata. Hydration payloads are a fallback
    because their shape is site-specific guesswork.
    """
    if not html:
        return None
    try:
        found = _walk_json_ld(html) or _from_hydration(html)
    except Exception:
        logger.debug("structured extraction failed", exc_info=True)
        return None
    if found and len(found.text.strip()) >= MIN_BODY_CHARS:
        return found
    return None
