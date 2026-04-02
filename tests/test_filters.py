"""Tests for nostrax.filters."""

import pytest

from nostrax.filters import (
    filter_by_domain,
    filter_by_exclude,
    filter_by_pattern,
    filter_by_protocol,
)

URLS = [
    "https://example.com/page1",
    "https://example.com/page2",
    "https://other.com/page3",
    "http://example.com/insecure",
    "ftp://files.example.com/data",
    "https://example.com/images/photo.jpg",
]

BASE = "https://example.com"


def test_filter_domain_all():
    result = filter_by_domain(URLS, BASE, mode="all")
    assert result == URLS


def test_filter_domain_internal():
    result = filter_by_domain(URLS, BASE, mode="internal")
    assert "https://other.com/page3" not in result
    assert "ftp://files.example.com/data" not in result


def test_filter_domain_external():
    result = filter_by_domain(URLS, BASE, mode="external")
    assert "https://example.com/page1" not in result
    assert "https://other.com/page3" in result


def test_filter_domain_invalid_mode():
    with pytest.raises(ValueError):
        filter_by_domain(URLS, BASE, mode="invalid")


def test_filter_protocol_https():
    result = filter_by_protocol(URLS, {"https"})
    assert all(u.startswith("https://") for u in result)


def test_filter_protocol_multiple():
    result = filter_by_protocol(URLS, {"http", "https"})
    assert "ftp://files.example.com/data" not in result
    assert len(result) == 5


def test_filter_pattern_jpg():
    result = filter_by_pattern(URLS, r"\.jpg$")
    assert result == ["https://example.com/images/photo.jpg"]


def test_filter_pattern_page():
    result = filter_by_pattern(URLS, r"/page\d+")
    assert len(result) == 3


def test_filter_pattern_no_match():
    result = filter_by_pattern(URLS, r"\.xml$")
    assert result == []


def test_filter_pattern_invalid_regex():
    result = filter_by_pattern(URLS, r"[invalid")
    assert result == URLS


def test_filter_pattern_safe_against_backtracking():
    urls = ["https://example.com/" + "a" * 100]
    result = filter_by_pattern(urls, r"(a+)+b")
    assert isinstance(result, list)


def test_filter_exclude_removes_matches():
    result = filter_by_exclude(URLS, r"\.jpg$")
    assert "https://example.com/images/photo.jpg" not in result
    assert len(result) == 5


def test_filter_exclude_no_match():
    result = filter_by_exclude(URLS, r"\.xml$")
    assert result == URLS


def test_filter_exclude_invalid_regex():
    result = filter_by_exclude(URLS, r"[invalid")
    assert result == URLS


def test_filter_exclude_pages():
    result = filter_by_exclude(URLS, r"/page\d+")
    assert len(result) == 3
    assert all("/page" not in u for u in result)
