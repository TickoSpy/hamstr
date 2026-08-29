import json

from app.services.ingest.article import extract_article
from app.services.ingest.structured import extract_structured

PROSE = " ".join(
    f"Paragraph {i} explains a further consequence of the policy change and what "
    f"it means for the people affected by it."
    for i in range(1, 12)
)


def _page(head: str = "", body: str = "") -> str:
    return f"<!DOCTYPE html><html><head>{head}</head><body>{body}</body></html>"


def _ld(payload: dict | list) -> str:
    return f'<script type="application/ld+json">{json.dumps(payload)}</script>'


# --- JSON-LD -----------------------------------------------------------------


def test_json_ld_article_body_is_recovered():
    html = _page(
        head=_ld(
            {
                "@context": "https://schema.org",
                "@type": "NewsArticle",
                "headline": "Council approves the plan",
                "author": {"@type": "Person", "name": "Jane Roe"},
                "datePublished": "2024-05-06T09:00:00Z",
                "description": "A short summary.",
                "image": {"url": "https://news.example/lead.jpg"},
                "articleBody": PROSE,
            }
        ),
        body="<div id='root'></div>",
    )
    got = extract_structured(html)
    assert got is not None
    assert got.source == "json-ld"
    assert "Paragraph 1 explains" in got.text
    assert got.title == "Council approves the plan"
    assert got.byline == "Jane Roe"
    assert got.published.startswith("2024-05-06")
    assert got.excerpt == "A short summary."
    assert got.image == "https://news.example/lead.jpg"


def test_json_ld_handles_a_graph_and_a_list_of_authors():
    html = _page(
        head=_ld(
            {
                "@graph": [
                    {"@type": "WebSite", "name": "Example News"},
                    {
                        "@type": "Article",
                        "headline": "Two bylines",
                        "author": [{"name": "A. One"}, {"name": "B. Two"}],
                        "articleBody": PROSE,
                    },
                ]
            }
        )
    )
    got = extract_structured(html)
    assert got is not None
    assert got.byline == "A. One, B. Two"


def test_json_ld_plain_text_becomes_paragraphs():
    html = _page(head=_ld({"@type": "Article", "articleBody": PROSE}))
    got = extract_structured(html)
    assert got is not None
    assert got.html.startswith("<p>")


def test_json_ld_escapes_markup_in_plain_text_bodies():
    """A plain-text body must not smuggle in tags.

    (A literal </script> is not used here: it would close the JSON-LD element
    itself, which is why publishers escape it — that is the browser's problem,
    not the extractor's.)
    """
    hostile = PROSE + ' <img src=x onerror="alert(1)"> and <b>markup</b>'
    got = extract_structured(
        _page(head=_ld({"@type": "Article", "articleBody": hostile}))
    )
    assert got is not None
    # The word "onerror" survives as inert text; what matters is that no tag does.
    assert "<img" not in got.html
    assert "<b>" not in got.html
    assert "&lt;img" in got.html and "&lt;b&gt;" in got.html
    # Only the paragraph wrappers we added are real markup.
    assert got.html.count("<") == got.html.count("<p>") + got.html.count("</p>")


def test_a_body_that_is_real_markup_is_kept_as_markup():
    body = "".join(
        f"<p>Paragraph {i} of genuine article markup here.</p>" for i in range(30)
    )
    got = extract_structured(_page(head=_ld({"@type": "Article", "articleBody": body})))
    assert got is not None
    assert got.html.count("<p>") >= 30


def test_a_teaser_length_body_is_ignored():
    html = _page(head=_ld({"@type": "Article", "articleBody": "Too short to count."}))
    assert extract_structured(html) is None


def test_malformed_json_ld_is_skipped():
    html = _page(head='<script type="application/ld+json">{not json,,}</script>')
    assert extract_structured(html) is None


# --- hydration payloads ------------------------------------------------------


def test_next_data_block_array_is_reassembled():
    """The common Next.js shape: an array of typed blocks, not one long string."""
    blocks = [
        {
            "type": "paragraph",
            "text": f"Block {i} carries a sentence of real prose "
            f"about the subject at hand and its consequences.",
        }
        for i in range(1, 12)
    ]
    payload = {"props": {"pageProps": {"article": {"body": blocks}}}}
    html = _page(
        head="",
        body=f'<script id="__NEXT_DATA__" type="application/json">{json.dumps(payload)}</script>',
    )
    got = extract_structured(html)
    assert got is not None
    assert got.source == "hydration"
    assert "Block 1 carries" in got.text
    assert "Block 11 carries" in got.text


def test_window_initial_state_assignment_is_parsed():
    payload = {"article": {"content": PROSE}}
    html = _page(
        body=f"<script>window.__INITIAL_STATE__ = {json.dumps(payload)};</script>"
    )
    got = extract_structured(html)
    assert got is not None
    assert got.source == "hydration"
    assert "Paragraph 1 explains" in got.text


def test_a_recognised_body_key_beats_a_longer_unrelated_string():
    """Comment threads and related-article blurbs must not win."""
    noise = " ".join(
        f"Comment {i} is chatter that happens to be long." for i in range(1, 60)
    )
    payload = {"comments": {"text": noise}, "article": {"articleBody": PROSE}}
    html = _page(
        body=f"<script>window.__INITIAL_STATE__ = {json.dumps(payload)};</script>"
    )
    got = extract_structured(html)
    assert got is not None
    assert "Paragraph 1 explains" in got.text


def test_non_prose_payloads_are_rejected():
    """Base64, CSS and id blobs are long strings but not articles."""
    for junk in [
        "A" * 5000,
        "data:image/png;base64," + "Q" * 4000,
        ".a{color:red}" * 400,
    ]:
        html = _page(
            body=f"<script>window.__INITIAL_STATE__ = {json.dumps({'x': junk})};</script>"
        )
        assert extract_structured(html) is None, junk[:20]


def test_no_payload_at_all():
    assert extract_structured(_page(body="<p>Hi</p>")) is None
    assert extract_structured("") is None


# --- integration with the extraction ladder ----------------------------------


def test_structured_rescues_a_page_the_dom_extractors_cannot_read():
    """A client-rendered page: empty DOM, content only in the payload."""
    html = _page(
        head=_ld(
            {
                "@type": "Article",
                "headline": "Rendered client-side",
                "author": {"name": "Jane Roe"},
                "articleBody": PROSE,
            }
        ),
        body='<div id="app"></div>',
    )
    got = extract_article(html, "https://spa.example/story")
    assert got is not None
    assert "Paragraph 1 explains" in got.text
    assert got.title == "Rendered client-side"
    assert got.byline == "Jane Roe"


def test_declared_metadata_fills_gaps_when_the_dom_extractor_wins():
    """trafilatura reads the prose but often not the byline; JSON-LD has both."""
    body_html = "".join(f"<p>{s}.</p>" for s in PROSE.split(". "))
    html = _page(
        head=_ld(
            {
                "@type": "Article",
                "headline": "Server rendered",
                "author": {"name": "Declared Author"},
                "datePublished": "2024-05-06",
            }
        ),
        body=f"<article><h1>Server rendered</h1>{body_html}</article>",
    )
    got = extract_article(html, "https://news.example/story")
    assert got is not None
    assert got.word_count > 100
    assert got.byline == "Declared Author"
