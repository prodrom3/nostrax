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
