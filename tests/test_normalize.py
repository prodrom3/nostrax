"""Tests for nostrax.normalize."""

from nostrax.normalize import normalize_url


def test_removes_fragment():
    assert normalize_url("https://example.com/page#section") == "https://example.com/page"


def test_removes_trailing_slash():
    assert normalize_url("https://example.com/page/") == "https://example.com/page"


def test_keeps_root_slash():
    assert normalize_url("https://example.com/") == "https://example.com/"


def test_lowercases_scheme_and_host():
    assert normalize_url("HTTPS://Example.COM/Page") == "https://example.com/Page"


def test_removes_default_http_port():
    assert normalize_url("http://example.com:80/page") == "http://example.com/page"


def test_removes_default_https_port():
    assert normalize_url("https://example.com:443/page") == "https://example.com/page"


def test_keeps_nondefault_port():
    assert normalize_url("https://example.com:8080/page") == "https://example.com:8080/page"


def test_sorts_query_params():
    result = normalize_url("https://example.com/page?z=1&a=2")
    assert result == "https://example.com/page?a=2&z=1"


def test_removes_empty_query():
    assert normalize_url("https://example.com/page?") == "https://example.com/page"


def test_identical_urls_normalize_same():
    urls = [
        "https://example.com/page",
        "https://example.com/page/",
        "https://example.com/page#top",
        "HTTPS://EXAMPLE.COM/page",
    ]
    normalized = {normalize_url(u) for u in urls}
    assert len(normalized) == 1


def test_strips_credentials():
    result = normalize_url("https://user:pass@example.com/page")
    assert "user" not in result
    assert "pass" not in result
    assert result == "https://example.com/page"
