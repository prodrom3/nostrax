"""Tests for nostrax.exceptions."""

from nostrax.exceptions import (
    FetchError,
    NostraxError,
    NonHtmlResponseError,
    ParseError,
    ResponseTooLargeError,
    RobotsBlockedError,
)


def test_fetch_error():
    e = FetchError("https://example.com", "timeout")
    assert e.url == "https://example.com"
    assert e.reason == "timeout"
    assert "timeout" in str(e)


def test_parse_error():
    e = ParseError("https://example.com", "malformed HTML")
    assert e.url == "https://example.com"
    assert isinstance(e, NostraxError)


def test_robots_blocked():
    e = RobotsBlockedError("https://example.com/private")
    assert e.url == "https://example.com/private"
    assert "robots.txt" in str(e)


def test_response_too_large():
    e = ResponseTooLargeError("https://example.com", 20_000_000, 10_000_000)
    assert e.size == 20_000_000
    assert e.limit == 10_000_000
    assert isinstance(e, FetchError)


def test_non_html_response():
    e = NonHtmlResponseError("https://example.com/image.png", "image/png")
    assert e.content_type == "image/png"
    assert isinstance(e, FetchError)


def test_hierarchy():
    assert issubclass(FetchError, NostraxError)
    assert issubclass(ParseError, NostraxError)
    assert issubclass(RobotsBlockedError, NostraxError)
    assert issubclass(ResponseTooLargeError, FetchError)
    assert issubclass(NonHtmlResponseError, FetchError)
