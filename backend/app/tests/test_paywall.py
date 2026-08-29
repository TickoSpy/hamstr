from dataclasses import dataclass

import pytest

from app.services.ingest.archive import (
    archive_today_urls,
    is_challenge,
    looks_like_archive_miss,
    strip_wayback_chrome,
)
from app.services.ingest.paywall import detect_paywall


@dataclass
class FakeExtraction:
    word_count: int
    text: str = ""


LONG_DESCRIPTION = (
    "An in-depth investigation into the state of municipal water infrastructure "
    "across the country, based on two years of public records requests."
)


def _page(*, description: str = "", body: str = "", extra: str = "") -> str:
    meta = (
        f'<meta property="og:description" content="{description}">'
        if description
        else ""
    )
    return f"<html><head>{meta}{extra}</head><body>{body}</body></html>"


# --- hard signals ------------------------------------------------------------


@pytest.mark.parametrize("code", [401, 402, 403, 451])
def test_refusal_status_codes_are_conclusive(code):
    verdict = detect_paywall(status_code=code, html="", extracted=None)
    assert verdict.paywalled
    assert str(code) in verdict.reason


def test_schema_org_is_accessible_for_free_false():
    html = _page(
        extra='<script type="application/ld+json">{"isAccessibleForFree": false}</script>'
    )
    assert detect_paywall(status_code=200, html=html, extracted=None).paywalled


def test_schema_org_string_false_variant():
    html = _page(
        extra='<script type="application/ld+json">{"isAccessibleForFree":"False"}</script>'
    )
    assert detect_paywall(status_code=200, html=html, extracted=None).paywalled


@pytest.mark.parametrize("tier", ["locked", "metered"])
def test_article_content_tier_meta(tier):
    html = _page(extra=f'<meta property="article:content_tier" content="{tier}">')
    verdict = detect_paywall(status_code=200, html=html, extracted=None)
    assert verdict.paywalled
    assert tier in verdict.reason


def test_schema_org_accessible_for_free_true_is_not_a_paywall():
    html = _page(
        extra='<script type="application/ld+json">{"isAccessibleForFree": true}</script>'
    )
    assert not detect_paywall(
        status_code=200, html=html, extracted=FakeExtraction(900)
    ).paywalled


# --- soft signals need corroboration -----------------------------------------


def test_marker_plus_stub_extraction_is_a_paywall():
    html = _page(
        description=LONG_DESCRIPTION,
        body='<div class="paywall-overlay">Subscribe to continue reading.</div>',
    )
    verdict = detect_paywall(status_code=200, html=html, extracted=FakeExtraction(40))
    assert verdict.paywalled


def test_a_marker_alone_is_not_enough():
    """A full article that merely mentions subscribing must not be flagged."""
    html = _page(
        description=LONG_DESCRIPTION,
        body="<p>Subscribe to continue reading our newsletter.</p>",
    )
    verdict = detect_paywall(status_code=200, html=html, extracted=FakeExtraction(1400))
    assert not verdict.paywalled


def test_a_short_page_without_a_description_is_not_a_paywall():
    """The false-positive guard: a short blog post advertises nothing grander."""
    html = _page(body="<p>Quick note: the meeting moved to Thursday.</p>")
    verdict = detect_paywall(status_code=200, html=html, extracted=FakeExtraction(12))
    assert not verdict.paywalled


def test_a_short_page_with_a_long_description_alone_is_not_enough():
    """One signal shouldn't convict — a link roundup looks exactly like this."""
    html = _page(description=LONG_DESCRIPTION, body="<p>Three links this week.</p>")
    verdict = detect_paywall(status_code=200, html=html, extracted=FakeExtraction(30))
    assert not verdict.paywalled


def test_vendor_fingerprint_plus_stub():
    html = _page(
        description=LONG_DESCRIPTION,
        extra='<script src="https://cdn.tinypass.com/api/tinypass.min.js"></script>',
    )
    assert detect_paywall(
        status_code=200, html=html, extracted=FakeExtraction(50)
    ).paywalled


def test_truncated_text_plus_marker():
    html = _page(body='<div data-paywall="true"></div>')
    extracted = FakeExtraction(120, text="The mayor said the plan would…")
    assert detect_paywall(status_code=200, html=html, extracted=extracted).paywalled


def test_a_full_article_is_clean():
    html = _page(description=LONG_DESCRIPTION, body="<article>lots of words</article>")
    verdict = detect_paywall(status_code=200, html=html, extracted=FakeExtraction(2200))
    assert not verdict.paywalled
    assert verdict.reason == "no paywall signals"


def test_german_paywall_copy_is_recognised():
    html = _page(
        description=LONG_DESCRIPTION, body="<div>Jetzt weiterlesen mit Abo</div>"
    )
    assert detect_paywall(
        status_code=200, html=html, extracted=FakeExtraction(60)
    ).paywalled


# --- archive helpers ---------------------------------------------------------


def test_archive_today_urls_cover_every_configured_mirror():
    urls = archive_today_urls("https://news.example/a?b=c")
    assert len(urls) >= 4
    assert all(u.startswith("https://") and "/newest/" in u for u in urls)
    # The target URL keeps its own scheme and query intact.
    assert all("https://news.example/a?b=c" in u for u in urls)


def test_challenge_detection_covers_the_captcha_wall():
    """This is what archive.ph actually serves to a datacenter IP."""
    html = (
        "<html><head><title>archive.ph</title></head><body>"
        "<h1>One more step</h1><p>Please complete the security check to access</p>"
        "</body></html>"
    )
    assert is_challenge(html)


def test_a_429_is_a_challenge_regardless_of_body():
    assert is_challenge("<html>whatever</html>", 429)


def test_cloudflare_interstitials_are_challenges():
    assert is_challenge("<title>Just a moment...</title>")
    assert is_challenge("<div class='cf-browser-verification'>")


def test_a_real_snapshot_is_not_a_challenge():
    assert not is_challenge(
        "<html><body><article>Real content here</article></body></html>"
    )


def test_archive_miss_detection():
    assert looks_like_archive_miss("<p>No results</p>")
    assert not looks_like_archive_miss("<article>Real content</article>")


def test_strip_wayback_chrome_removes_the_toolbar():
    html = (
        '<html><body><div id="wm-ipp-base">TOOLBAR MARKUP</div>'
        '<script>__wm.init("https://web.archive.org/web");</script>'
        "<article>Real content</article></body></html>"
    )
    out = strip_wayback_chrome(html)
    assert "TOOLBAR MARKUP" not in out
    assert "__wm.init" not in out
    assert "Real content" in out


def test_strip_wayback_chrome_leaves_normal_pages_alone():
    html = "<html><body><article>Untouched</article></body></html>"
    assert strip_wayback_chrome(html) == html


@pytest.mark.parametrize("quote", ["'", '"'])
def test_markers_match_either_attribute_quoting(quote):
    """HTML lets you quote attributes either way; markers must not care."""
    html = _page(
        description=LONG_DESCRIPTION,
        body=f"<div class={quote}paywall-overlay{quote}>Subscribe to continue reading.</div>",
    )
    assert detect_paywall(
        status_code=200, html=html, extracted=FakeExtraction(40)
    ).paywalled
