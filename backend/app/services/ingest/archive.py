"""Archive mirrors used when the origin withholds an article.

archive.today is tried first because it stores a rendered snapshot that usually
includes the full text. In practice it sits behind a CAPTCHA/rate-limit wall for
datacenter and many residential IPs, so its refusals are detected and skipped
quietly — the Wayback Machine is the leg that actually works unattended.
"""

import logging
import re
from urllib.parse import quote

import httpx

from app.config import settings
from app.services.ingest.http import build_client, safe_get

logger = logging.getLogger(__name__)

WAYBACK_AVAILABILITY_API = "https://archive.org/wayback/available"

# archive.today's URL grammar keeps these characters literal.
_QUOTE_SAFE = ":/?#[]@!$&'()*+,;="

_CHALLENGE_MARKERS = (
    "please complete the security check",
    "one more step",
    "completing the captcha",
    "checking your browser before accessing",
    "just a moment",
    "cf-browser-verification",
    "cf_chl_",
    "attention required",
)

_MISS_MARKERS = (
    "no results",
    "the page you are looking for was not archived",
    "this page has not been archived",
    "hasn't been archived",
)

# The Wayback banner injected into every snapshot.
_WAYBACK_CHROME = re.compile(
    r"<div[^>]+id=[\"'](?:wm-ipp-base|wm-ipp|donato)[\"'].*?</div>\s*",
    re.IGNORECASE | re.DOTALL,
)
_WAYBACK_SCRIPTS = re.compile(
    r"<script[^>]*>.*?(?:__wm\.|archive\.org/_static|RufflePlayer).*?</script>",
    re.IGNORECASE | re.DOTALL,
)


def archive_today_urls(url: str) -> list[str]:
    """`/newest/<url>` on each configured mirror, in preference order."""
    encoded = quote(url, safe=_QUOTE_SAFE)
    return [f"https://{host}/newest/{encoded}" for host in settings.archive_today_hosts]


def is_challenge(html: str, status_code: int = 200) -> bool:
    """True when the mirror served a CAPTCHA/rate-limit page instead of a snapshot."""
    if status_code == 429:
        return True
    lowered = (html or "")[:4000].lower()
    return any(marker in lowered for marker in _CHALLENGE_MARKERS)


def looks_like_archive_miss(html: str) -> bool:
    lowered = (html or "")[:4000].lower()
    return any(marker in lowered for marker in _MISS_MARKERS)


def strip_wayback_chrome(html: str) -> str:
    """Remove the Wayback toolbar so it can't be mistaken for article content."""
    if "web.archive.org" not in (html or "") and "wm-ipp" not in (html or ""):
        return html
    html = _WAYBACK_CHROME.sub("", html)
    return _WAYBACK_SCRIPTS.sub("", html)


async def wayback_snapshot_url(client: httpx.AsyncClient, url: str) -> str | None:
    """The closest usable Wayback snapshot for a URL, or None."""
    try:
        response = await client.get(
            WAYBACK_AVAILABILITY_API, params={"url": url}, timeout=10.0
        )
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        logger.info("Wayback availability lookup failed for %s: %s", url, exc)
        return None

    closest = (data.get("archived_snapshots") or {}).get("closest") or {}
    if not closest.get("available") or str(closest.get("status", "200")) != "200":
        return None

    snapshot = closest.get("url")
    if not snapshot:
        return None
    # The API still hands back http:// URLs.
    return snapshot.replace("http://", "https://", 1)


async def fetch_archive_snapshot(
    client: httpx.AsyncClient, url: str, *, timeout: float = 15.0
) -> str | None:
    """Fetch a mirror URL, returning its HTML or None if it refused/missed.

    The plain-UA retry in safe_get is disabled here: a CAPTCHA wall is not a
    user-agent problem, so retrying only doubles the latency of a known failure.
    """
    try:
        response = await safe_get(
            client,
            url,
            max_bytes=settings.max_article_bytes,
            timeout=timeout,
            ua_retry=False,
        )
    except Exception as exc:
        logger.info("Archive mirror %s failed: %s", url, exc)
        return None

    if is_challenge(response.text, response.status_code):
        logger.info("Archive mirror %s served a challenge page — skipping", url)
        return None
    if response.status_code >= 400:
        logger.info("Archive mirror %s returned %s", url, response.status_code)
        return None
    if looks_like_archive_miss(response.text):
        logger.info("Archive mirror %s has no snapshot", url)
        return None

    return response.text


def build_archive_client() -> httpx.AsyncClient:
    return build_client(timeout=20.0)
