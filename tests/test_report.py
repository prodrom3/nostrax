"""Tests for nostrax.report."""

from nostrax.models import UrlResult
from nostrax.report import generate_html_report


def test_report_basic():
    results = [
        UrlResult(url="https://example.com/a", source="https://example.com", tag="a", depth=0),
        UrlResult(url="https://example.com/b", source="https://example.com", tag="img", depth=1),
    ]
    html = generate_html_report(results, "https://example.com")
    assert "<!DOCTYPE html>" in html
    assert "https://example.com/a" in html
    assert "https://example.com/b" in html
    assert "nostrax Report" in html


def test_report_with_statuses():
    results = [
        UrlResult(url="https://example.com/ok", tag="a"),
        UrlResult(url="https://example.com/broken", tag="a"),
    ]
    statuses = {
        "https://example.com/ok": 200,
        "https://example.com/broken": 404,
    }
    html = generate_html_report(results, "https://example.com", statuses=statuses)
    assert "200" in html
    assert "404" in html
    assert "OK" in html  # status summary
    assert "Broken" in html


def test_report_with_response_time():
    results = [
        UrlResult(url="https://example.com/a", response_time=123.4),
    ]
    html = generate_html_report(results, "https://example.com")
    assert "123ms" in html


def test_report_empty():
    html = generate_html_report([], "https://example.com")
    assert "<!DOCTYPE html>" in html
    assert "Total URLs" in html


def test_report_contains_filter_script():
    results = [UrlResult(url="https://example.com/a")]
    html = generate_html_report(results, "https://example.com")
    assert "filterTable" in html
