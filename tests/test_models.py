"""Tests for nostrax.models."""

from nostrax.models import UrlResult


def test_url_result_basic():
    r = UrlResult(url="https://example.com")
    assert r.url == "https://example.com"
    assert r.source == ""
    assert r.tag == ""
    assert r.depth == 0
    assert r.status is None


def test_url_result_with_metadata():
    r = UrlResult(
        url="https://example.com/page",
        source="https://example.com",
        tag="a",
        depth=2,
        status=200,
    )
    assert r.depth == 2
    assert r.status == 200


def test_url_result_to_dict_minimal():
    r = UrlResult(url="https://example.com")
    d = r.to_dict()
    assert d == {"url": "https://example.com"}


def test_url_result_to_dict_full():
    r = UrlResult(
        url="https://example.com",
        source="https://source.com",
        tag="img",
        depth=3,
        status=404,
    )
    d = r.to_dict()
    assert d["url"] == "https://example.com"
    assert d["source"] == "https://source.com"
    assert d["tag"] == "img"
    assert d["depth"] == 3
    assert d["status"] == 404


def test_url_result_response_time():
    r = UrlResult(url="https://example.com", response_time=123.456)
    d = r.to_dict()
    assert d["response_time_ms"] == 123.5


def test_url_result_response_time_none():
    r = UrlResult(url="https://example.com")
    assert r.response_time is None
    assert "response_time_ms" not in r.to_dict()
