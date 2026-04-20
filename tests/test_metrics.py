"""Tests for nostrax.metrics and the MetricsSink integration in the crawler."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nostrax.crawler import crawl
from nostrax.metrics import MetricsSink, NullMetricsSink


class RecordingSink:
    """Collects events as plain dicts so tests can assert on them."""

    def __init__(self) -> None:
        self.events: list[dict] = []

    def on_page_fetched(self, url, depth, elapsed_ms, urls_found):
        self.events.append(
            {"kind": "fetched", "url": url, "depth": depth, "urls_found": urls_found}
        )

    def on_fetch_failed(self, url, depth):
        self.events.append({"kind": "failed", "url": url, "depth": depth})

    def on_robots_blocked(self, url):
        self.events.append({"kind": "robots", "url": url})


def test_null_sink_implements_protocol():
    """NullMetricsSink must satisfy the MetricsSink protocol contract."""
    assert isinstance(NullMetricsSink(), MetricsSink)


def test_recording_sink_implements_protocol():
    """User-side sinks satisfy the protocol without explicit inheritance."""
    assert isinstance(RecordingSink(), MetricsSink)


def _mock_response(body: str = "<a href='/x'>x</a>"):
    encoded = body.encode("utf-8")
    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.content_length = None
    mock_resp.content_type = "text/html"
    mock_resp.charset = "utf-8"
    mock_resp.raise_for_status = MagicMock()
    content = MagicMock()
    content.read = AsyncMock(return_value=encoded)
    mock_resp.content = content
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)
    return mock_resp


def test_metrics_sink_receives_on_page_fetched():
    sink = RecordingSink()

    with patch("nostrax.crawler.aiohttp.ClientSession") as mock_cls:
        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=_mock_response())
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        crawl("https://example.com", metrics=sink)

    fetched = [e for e in sink.events if e["kind"] == "fetched"]
    assert len(fetched) == 1
    assert fetched[0]["url"] == "https://example.com"
    assert fetched[0]["depth"] == 0
    assert fetched[0]["urls_found"] == 1


def test_metrics_sink_receives_on_fetch_failed_when_html_missing():
    sink = RecordingSink()

    resp = _mock_response()
    resp.content_type = "application/octet-stream"  # forces fetch_page to return None

    with patch("nostrax.crawler.aiohttp.ClientSession") as mock_cls:
        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=resp)
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        with pytest.raises(Exception):
            # pages_crawled stays 0, crawl_async raises FetchError.
            crawl("https://example.com", metrics=sink)

    failed = [e for e in sink.events if e["kind"] == "failed"]
    assert len(failed) == 1
    assert failed[0]["url"] == "https://example.com"
    assert failed[0]["depth"] == 0


def test_metrics_sink_receives_on_robots_blocked():
    """A URL refused by robots.txt triggers on_robots_blocked."""
    sink = RecordingSink()

    with patch("nostrax.crawler.RobotsChecker") as RobotsClass:
        robots = RobotsClass.return_value
        robots.load = AsyncMock()
        robots.is_allowed = MagicMock(return_value=False)

        with patch("nostrax.crawler.aiohttp.ClientSession") as mock_cls:
            mock_session = AsyncMock()
            mock_session.get = MagicMock(return_value=_mock_response())
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            with pytest.raises(Exception):
                # Nothing fetches, so crawl_async raises FetchError at the end.
                crawl("https://example.com", respect_robots=True, metrics=sink)

    robots_events = [e for e in sink.events if e["kind"] == "robots"]
    assert len(robots_events) == 1
    assert robots_events[0]["url"] == "https://example.com"


class BrokenSink:
    """A sink whose methods all raise. Verifies we isolate user bugs."""

    def on_page_fetched(self, *a, **kw):
        raise RuntimeError("oops in on_page_fetched")

    def on_fetch_failed(self, *a, **kw):
        raise RuntimeError("oops in on_fetch_failed")

    def on_robots_blocked(self, *a, **kw):
        raise RuntimeError("oops in on_robots_blocked")


def test_buggy_sink_does_not_crash_the_crawl():
    """A user-supplied sink that raises must not propagate the exception
    out of crawl; the crawl continues and returns the extracted URLs."""
    with patch("nostrax.crawler.aiohttp.ClientSession") as mock_cls:
        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=_mock_response())
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        # Must not raise even though every sink call raises internally.
        urls = crawl("https://example.com", metrics=BrokenSink())
        assert "https://example.com/x" in urls
