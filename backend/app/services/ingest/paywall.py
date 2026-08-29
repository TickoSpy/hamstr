"""Detecting that a page withheld its content.

A pure function over (status, html, extraction) so it can be exercised without a
network. The hard part is not spotting paywalls — it's not crying paywall on
short blog posts and link roundups, which is why the soft signals require
corroboration from the page's own advertised description.
"""

import re
from dataclasses import dataclass

# Any one of these is conclusive on its own.
HARD_STATUS_CODES = frozenset({401, 402, 403, 451})

_JSON_LD_NOT_FREE = re.compile(
    r'"isAccessibleForFree"\s*:\s*(?:false|"false"|"False")', re.IGNORECASE
)
_CONTENT_TIER = re.compile(
    r'<meta[^>]+(?:name|property)=["\']article:content_tier["\'][^>]+'
    r'content=["\'](locked|metered)["\']',
    re.IGNORECASE,
)
_OG_DESCRIPTION = re.compile(
    r'<meta[^>]+(?:property|name)=["\'](?:og:description|description|'
    r'twitter:description)["\'][^>]+content=["\']([^"\']{0,600})["\']',
    re.IGNORECASE,
)

# Phrases and markup that suggest a wall. Individually weak — a news article can
# legitimately mention the word "subscribe" — so two are required.
SOFT_MARKERS: tuple[str, ...] = (
    "data-paywall",
    'class="paywall',
    'id="paywall',
    "paywall-",
    "regwall",
    "pw-gate",
    "meteredcontent",
    "metered-content",
    "subscribe to continue",
    "subscribe to read",
    "subscription required",
    "this article is for subscribers",
    "for subscribers only",
    "become a member to read",
    "you've reached your article limit",
    "you have reached your article limit",
    "register to continue",
    "sign in to read",
    "jetzt weiterlesen",
    "nur mit abo",
    "artikel ist nur für abonnenten",
    "weiterlesen mit",
)

# Paywall vendors — a strong hint the page is gated even without wall copy.
VENDOR_MARKERS: tuple[str, ...] = (
    "piano.io",
    "tinypass",
    "cxense",
    "zephr.com",
    "poool.fr",
    "leakyPaywall",
    "pelcro",
    "memberful",
)

# An extraction below this is a stub, not an article.
STUB_WORD_COUNT = 220
# ...but only when the page itself claims to be about something substantial.
MEANINGFUL_DESCRIPTION_CHARS = 120
# Text that trails off mid-thought this early is a teaser.
TRUNCATION_WORD_COUNT = 400


@dataclass(frozen=True)
class PaywallVerdict:
    paywalled: bool
    reason: str


def og_description(html: str) -> str:
    match = _OG_DESCRIPTION.search(html or "")
    return match.group(1).strip() if match else ""


def detect_paywall(
    *,
    status_code: int,
    html: str,
    extracted: object | None,
) -> PaywallVerdict:
    """Decide whether a fetched page withheld its article.

    `extracted` is an ExtractedArticle or None; it's typed loosely to keep this
    module free of import cycles and trivially unit-testable.
    """
    if status_code in HARD_STATUS_CODES:
        return PaywallVerdict(True, f"HTTP {status_code}")

    html = html or ""
    # Attribute quoting is a free choice in HTML, so normalise it rather than
    # carrying two spellings of every marker.
    lowered = html.lower().replace("'", '"')

    if _JSON_LD_NOT_FREE.search(html):
        return PaywallVerdict(True, "schema.org isAccessibleForFree=false")

    tier = _CONTENT_TIER.search(html)
    if tier:
        return PaywallVerdict(True, f"article:content_tier={tier.group(1)}")

    word_count = int(getattr(extracted, "word_count", 0) or 0)
    text = str(getattr(extracted, "text", "") or "")
    description = og_description(html)

    reasons: list[str] = []

    hit = next((m for m in SOFT_MARKERS if m in lowered), None)
    if hit:
        reasons.append(f"marker {hit!r}")

    vendor = next((v for v in VENDOR_MARKERS if v.lower() in lowered), None)
    if vendor:
        reasons.append(f"vendor {vendor!r}")

    # The page advertises a real article but we only got a stub out of it.
    if (extracted is None or word_count < STUB_WORD_COUNT) and len(
        description
    ) >= MEANINGFUL_DESCRIPTION_CHARS:
        reasons.append(
            f"only {word_count} words behind a {len(description)}-char description"
        )

    stripped = text.strip()
    if stripped.endswith(("…", "...")) and word_count < TRUNCATION_WORD_COUNT:
        reasons.append("extraction ends mid-sentence")

    if len(reasons) >= 2:
        return PaywallVerdict(True, "; ".join(reasons))

    return PaywallVerdict(False, "; ".join(reasons) or "no paywall signals")
