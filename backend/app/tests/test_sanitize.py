import pytest

from app.services.ingest.sanitize import (
    asset_filename,
    best_srcset_url,
    collect_image_urls,
    rewrite_urls,
    sanitize_article_html,
)

BASE = "https://news.example/2024/story"


# --- what must never survive -------------------------------------------------


@pytest.mark.parametrize(
    "payload",
    [
        "<script>alert(1)</script>",
        "<p>ok</p><script src='https://evil.example/x.js'></script>",
        '<img src="x" onerror="alert(1)">',
        '<div onclick="steal()">click</div>',
        '<a href="javascript:alert(1)">go</a>',
        '<iframe src="https://evil.example"></iframe>',
        "<style>body{display:none}</style>",
        '<object data="evil.swf"></object>',
        '<embed src="evil.swf">',
        '<form action="https://evil.example"><input name="pw"></form>',
        "<svg><script>alert(1)</script></svg>",
        "<math><mtext><table><mglyph><style><!--</style><img src=x onerror=alert(1)>",
        '<base href="https://evil.example/">',
        '<meta http-equiv="refresh" content="0;url=https://evil.example">',
        '<a href="data:text/html,<script>alert(1)</script>">x</a>',
    ],
)
def test_dangerous_markup_is_removed(payload):
    out = sanitize_article_html(payload).lower()
    assert "<script" not in out
    assert "onerror" not in out
    assert "onclick" not in out
    assert "javascript:" not in out
    assert "<iframe" not in out
    assert "<style" not in out
    assert "<object" not in out
    assert "<embed" not in out
    assert "<form" not in out
    assert "<base" not in out
    assert "<meta" not in out


def test_presentational_attributes_are_stripped():
    out = sanitize_article_html(
        '<p class="ad-slot" style="position:fixed" id="banner">text</p>'
    )
    assert "class=" not in out
    assert "style=" not in out
    assert "id=" not in out
    assert "text" in out


def test_srcset_is_stripped_so_nothing_reaches_the_network():
    out = sanitize_article_html(
        '<img src="/stream/web_1/asset/a.jpg" srcset="https://cdn.example/x.jpg 2x">'
    )
    assert "srcset" not in out
    assert "cdn.example" not in out


# --- what must survive -------------------------------------------------------


def test_article_content_survives():
    out = sanitize_article_html(
        "<h2>Heading</h2><p>Body <strong>bold</strong> <em>italic</em>.</p>"
        "<blockquote><p>quoted</p></blockquote>"
        "<ul><li>one</li></ul>"
        "<table><tr><td colspan='2'>cell</td></tr></table>"
        "<figure><img src='/stream/web_1/asset/a.jpg' alt='pic'>"
        "<figcaption>caption</figcaption></figure>"
        "<pre><code>x = 1</code></pre>"
    )
    for fragment in [
        "<h2>",
        "<p>",
        "<strong>",
        "<em>",
        "<blockquote>",
        "<ul>",
        "<li>",
        "<table>",
        "colspan",
        "<figure>",
        "<figcaption>",
        "<pre>",
        "<code>",
        "/stream/web_1/asset/a.jpg",
        'alt="pic"',
    ]:
        assert fragment in out, fragment


def test_external_links_survive_with_a_safe_rel():
    out = sanitize_article_html('<a href="https://example.com/x">link</a>')
    assert 'href="https://example.com/x"' in out
    assert "noopener" in out
    assert "nofollow" in out


# --- asset naming ------------------------------------------------------------


def test_asset_filename_is_deterministic_and_keeps_the_extension():
    a = asset_filename("https://cdn.example/photo.JPG")
    assert a == asset_filename("https://cdn.example/photo.JPG")
    assert a.endswith(".jpg")


def test_asset_filename_falls_back_to_the_content_type():
    assert asset_filename("https://cdn.example/img?id=7", "image/png").endswith(".png")


def test_asset_filename_is_always_a_single_safe_segment():
    name = asset_filename("https://cdn.example/../../etc/passwd")
    assert "/" not in name and ".." not in name


# --- srcset ------------------------------------------------------------------


def test_best_srcset_url_picks_the_widest():
    srcset = "small.jpg 320w, medium.jpg 640w, large.jpg 1280w"
    assert best_srcset_url(srcset, BASE) == "https://news.example/2024/large.jpg"


def test_best_srcset_url_handles_density_descriptors():
    assert (
        best_srcset_url("a.jpg 1x, b.jpg 3x", BASE) == "https://news.example/2024/b.jpg"
    )


def test_best_srcset_url_handles_a_bare_single_entry():
    assert best_srcset_url("only.jpg", BASE) == "https://news.example/2024/only.jpg"


# --- image collection --------------------------------------------------------


def test_collect_image_urls_prefers_srcset_and_lazy_attributes():
    html = (
        '<img src="placeholder.gif" data-src="real.jpg">'
        '<img srcset="s.jpg 100w, big.jpg 900w">'
        '<img src="data:image/gif;base64,AAA">'
        '<img src="plain.png">'
    )
    urls = collect_image_urls(html, BASE, limit=10)
    assert urls == [
        "https://news.example/2024/real.jpg",
        "https://news.example/2024/big.jpg",
        "https://news.example/2024/plain.png",
    ]


def test_collect_image_urls_respects_the_limit():
    html = "".join(f'<img src="{i}.jpg">' for i in range(50))
    assert len(collect_image_urls(html, BASE, limit=5)) == 5


def test_collect_image_urls_dedupes():
    html = '<img src="a.jpg"><img src="a.jpg">'
    assert len(collect_image_urls(html, BASE, limit=10)) == 1


# --- rewriting ---------------------------------------------------------------


def test_rewrite_points_images_at_local_assets():
    html = '<p><img src="photo.jpg" alt="x"></p>'
    out = rewrite_urls(
        html,
        base_url=BASE,
        item_id="web_abc",
        asset_map={"https://news.example/2024/photo.jpg": "deadbeef.jpg"},
    )
    assert 'src="/stream/web_abc/asset/deadbeef.jpg"' in out
    assert "news.example" not in out


def test_rewrite_drops_images_that_failed_to_download():
    """Leaving them would make reading an archived page hit the origin."""
    html = '<p>before<img src="photo.jpg">after</p>'
    out = rewrite_urls(html, base_url=BASE, item_id="web_abc", asset_map={})
    assert "<img" not in out
    assert "before" in out and "after" in out


def test_rewrite_absolutizes_links():
    out = rewrite_urls(
        '<a href="/other">x</a>', base_url=BASE, item_id="web_abc", asset_map={}
    )
    assert 'href="https://news.example/other"' in out
    assert 'target="_blank"' in out


def test_rewrite_removes_non_http_hrefs():
    out = rewrite_urls(
        '<a href="javascript:alert(1)">x</a>',
        base_url=BASE,
        item_id="web_abc",
        asset_map={},
    )
    assert "javascript:" not in out


def test_rewrite_then_sanitize_leaves_only_local_image_sources():
    html = (
        '<figure><img src="p.jpg" srcset="https://cdn.example/p2.jpg 2x" '
        'onerror="alert(1)"><figcaption>cap</figcaption></figure>'
    )
    rewritten = rewrite_urls(
        html,
        base_url=BASE,
        item_id="web_abc",
        asset_map={"https://cdn.example/p2.jpg": "aa.jpg"},
    )
    out = sanitize_article_html(rewritten)
    assert 'src="/stream/web_abc/asset/aa.jpg"' in out
    assert "onerror" not in out
    assert "cdn.example" not in out
    assert "cap" in out


# --- trafilatura's <graphic> tag ---------------------------------------------


def test_graphic_elements_are_normalized_to_img():
    """trafilatura's HTML output uses <graphic>, not <img>. Without this, no
    article image is ever collected — the sanitizer just drops the unknown tag."""
    from app.services.ingest.sanitize import normalize_media_tags

    out = normalize_media_tags('<p>x</p><graphic src="/a.jpg" alt="A"/>')
    assert "<img" in out
    assert 'src="/a.jpg"' in out
    assert 'alt="A"' in out
    assert "<graphic" not in out


def test_normalize_media_tags_is_a_noop_without_graphics():
    html = "<p>plain</p>"
    from app.services.ingest.sanitize import normalize_media_tags

    assert normalize_media_tags(html) == html


def test_graphic_images_are_collected_after_normalizing():
    from app.services.ingest.sanitize import normalize_media_tags

    html = normalize_media_tags('<graphic src="https://cdn.example/pic.jpg"/>')
    assert collect_image_urls(html, BASE, limit=5) == ["https://cdn.example/pic.jpg"]


def test_unnormalized_graphic_is_dropped_by_the_sanitizer():
    """Documents why normalize_media_tags has to run first."""
    assert "graphic" not in sanitize_article_html('<graphic src="/a.jpg"/>')
