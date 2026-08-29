import hashlib
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

ARTICLE_ID_PREFIX = "web_"
FILE_ID_PREFIX = "dl_"

# Query parameters that identify the referrer, not the resource. Stripping them
# means the same article shared from two places dedupes to one item.
TRACKING_PARAMS = frozenset(
    {
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_term",
        "utm_content",
        "utm_id",
        "utm_name",
        "utm_reader",
        "fbclid",
        "gclid",
        "gbraid",
        "wbraid",
        "msclkid",
        "igshid",
        "mc_cid",
        "mc_eid",
        "ref",
        "ref_src",
        "ref_url",
        "referrer",
        "_hsenc",
        "_hsmi",
        "yclid",
        "dclid",
        "s_cid",
        "cmpid",
        "sh",
    }
)


def canonical_url(url: str) -> str:
    """Normalize a URL for ID derivation and dedupe only.

    The *original* URL is what gets fetched and stored — this is deliberately
    lossy (drops the fragment and tracking params) and must never be substituted
    for the real thing.
    """
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return url.strip()

    scheme = parts.scheme.lower()
    netloc = parts.netloc.lower()

    # Drop a default port
    if scheme == "http" and netloc.endswith(":80"):
        netloc = netloc[: -len(":80")]
    elif scheme == "https" and netloc.endswith(":443"):
        netloc = netloc[: -len(":443")]

    path = parts.path
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")

    query = urlencode(
        [
            (k, v)
            for k, v in parse_qsl(parts.query, keep_blank_values=True)
            if k.lower() not in TRACKING_PARAMS
        ]
    )

    return urlunsplit((scheme, netloc, path, query, ""))


def make_item_id(prefix: str, url: str) -> str:
    """Deterministic, filesystem-safe ID for a non-yt-dlp item.

    Mirrors the existing ``err_`` + sha256 precedent in routers/videos.py.
    16 hex chars = 64 bits, collision-free for a personal archive.
    """
    digest = hashlib.sha256(canonical_url(url).encode("utf-8")).hexdigest()
    return prefix + digest[:16]
