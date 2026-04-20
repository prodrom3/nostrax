"""Tests for nostrax.extractor."""

from nostrax.extractor import extract_urls
from nostrax.models import UrlResult


SAMPLE_HTML = """
<html>
<head><link rel="stylesheet" href="/style.css"></head>
<body>
    <a href="/about">About</a>
    <a href="https://example.com/contact">Contact</a>
    <a href="/about">About duplicate</a>
    <a>No href</a>
    <a href="">Empty href</a>
    <a href="javascript:void(0)">JS link</a>
    <a href="mailto:test@example.com">Email</a>
    <a href="#section">Anchor</a>
    <img src="/logo.png">
    <script src="/app.js"></script>
    <form action="/submit"></form>
</body>
</html>
"""

BASE_URL = "https://example.com/page"


def test_extract_a_tags_only():
    urls = extract_urls(SAMPLE_HTML, BASE_URL)
    assert "https://example.com/about" in urls
    assert "https://example.com/contact" in urls
    assert "https://example.com/logo.png" not in urls
    assert "https://example.com/app.js" not in urls


def test_filters_none_and_empty_hrefs():
    urls = extract_urls(SAMPLE_HTML, BASE_URL)
    assert None not in urls
    assert "" not in urls


def test_filters_javascript_mailto_anchor():
    urls = extract_urls(SAMPLE_HTML, BASE_URL)
    for url in urls:
        assert not url.startswith("javascript:")
        assert not url.startswith("mailto:")
        assert url != "#section"


def test_base_href_overrides_page_url_for_relative_links():
    html = """
    <html>
      <head><base href="https://cdn.example.com/assets/"></head>
      <body>
        <a href="page.html">Relative</a>
        <a href="https://other.example.com/x">Absolute stays absolute</a>
      </body>
    </html>
    """
    urls = extract_urls(html, "https://example.com/docs/")
    assert "https://cdn.example.com/assets/page.html" in urls
    assert "https://other.example.com/x" in urls


def test_missing_base_falls_back_to_page_url():
    html = '<a href="page.html">x</a>'
    urls = extract_urls(html, "https://example.com/docs/")
    assert urls == ["https://example.com/docs/page.html"]


def test_empty_base_href_is_ignored():
    html = '<base href=""><a href="page.html">x</a>'
    urls = extract_urls(html, "https://example.com/docs/")
    assert urls == ["https://example.com/docs/page.html"]


def test_srcset_on_img_returns_every_candidate():
    html = (
        '<img src="fallback.jpg" '
        'srcset="small.jpg 300w, medium.jpg 800w, large.jpg 1600w">'
    )
    urls = extract_urls(
        html, "https://example.com/", tags={"img"}
    )
    assert set(urls) == {
        "https://example.com/fallback.jpg",
        "https://example.com/small.jpg",
        "https://example.com/medium.jpg",
        "https://example.com/large.jpg",
    }


def test_srcset_on_source_inside_picture():
    html = (
        '<picture>'
        '<source srcset="hero@2x.webp 2x, hero.webp 1x" type="image/webp">'
        '</picture>'
    )
    urls = extract_urls(html, "https://example.com/", tags={"source"})
    assert set(urls) == {
        "https://example.com/hero@2x.webp",
        "https://example.com/hero.webp",
    }


def test_meta_refresh_extracted_from_content():
    html = '<meta http-equiv="refresh" content="5; url=https://example.com/next">'
    urls = extract_urls(html, "https://example.com/", tags={"meta"})
    assert urls == ["https://example.com/next"]


def test_meta_refresh_case_insensitive_and_quoted():
    html = (
        '<meta http-equiv="Refresh" '
        'content="0; URL=\'https://example.com/quoted\'">'
    )
    urls = extract_urls(html, "https://example.com/", tags={"meta"})
    assert urls == ["https://example.com/quoted"]


def test_meta_without_refresh_is_ignored():
    html = '<meta http-equiv="content-type" content="text/html; charset=utf-8">'
    urls = extract_urls(html, "https://example.com/", tags={"meta"})
    assert urls == []


def test_meta_refresh_without_url_is_ignored():
    html = '<meta http-equiv="refresh" content="3">'
    urls = extract_urls(html, "https://example.com/", tags={"meta"})
    assert urls == []


def test_all_tags_includes_meta_and_srcset():
    html = (
        '<meta http-equiv="refresh" content="0; url=/m">'
        '<img srcset="/a.jpg 1x, /b.jpg 2x">'
        '<a href="/link">x</a>'
    )
    urls = extract_urls(html, "https://example.com/")
    # Default tags is {"a"}, so meta and img are NOT included.
    assert urls == ["https://example.com/link"]

    from nostrax.extractor import TAG_ATTRS
    urls = extract_urls(html, "https://example.com/", tags=set(TAG_ATTRS))
    assert "https://example.com/m" in urls
    assert "https://example.com/a.jpg" in urls
    assert "https://example.com/b.jpg" in urls
    assert "https://example.com/link" in urls


def test_resolves_relative_urls():
    urls = extract_urls(SAMPLE_HTML, BASE_URL)
    assert "https://example.com/about" in urls
    assert "/about" not in urls


def test_deduplication():
    urls = extract_urls(SAMPLE_HTML, BASE_URL)
    assert urls.count("https://example.com/about") == 1


def test_no_deduplication():
    urls = extract_urls(SAMPLE_HTML, BASE_URL, deduplicate=False)
    assert urls.count("https://example.com/about") == 2


def test_all_tags():
    tags = {"a", "img", "script", "link", "form"}
    urls = extract_urls(SAMPLE_HTML, BASE_URL, tags=tags)
    assert "https://example.com/logo.png" in urls
    assert "https://example.com/app.js" in urls
    assert "https://example.com/style.css" in urls
    assert "https://example.com/submit" in urls


def test_specific_tags():
    urls = extract_urls(SAMPLE_HTML, BASE_URL, tags={"img"})
    assert urls == ["https://example.com/logo.png"]


def test_empty_html():
    urls = extract_urls("", BASE_URL)
    assert urls == []


def test_no_links():
    urls = extract_urls("<html><body><p>Hello</p></body></html>", BASE_URL)
    assert urls == []


def test_include_metadata():
    results = extract_urls(SAMPLE_HTML, BASE_URL, include_metadata=True, depth=2)
    assert all(isinstance(r, UrlResult) for r in results)
    first = results[0]
    assert first.source == BASE_URL
    assert first.tag == "a"
    assert first.depth == 2


def test_metadata_all_tags():
    tags = {"a", "img"}
    results = extract_urls(SAMPLE_HTML, BASE_URL, tags=tags, include_metadata=True)
    tag_names = {r.tag for r in results}
    assert "a" in tag_names
    assert "img" in tag_names
