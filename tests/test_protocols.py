"""Tests for Fetcher / Extractor plug-in substitution in crawl_async."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nostrax.crawler import crawl
from nostrax.models import UrlResult


def _session_context() -> MagicMock:
    """Return a patched ClientSession that yields a no-op mock session."""
    mock_session = AsyncMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=mock_session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


def test_custom_fetcher_replaces_default():
    """A user-supplied fetcher must be called in place of fetch_page."""
    seen: list[str] = []

    async def my_fetcher(
        session, url, *, timeout, max_response_size, retries,
        proxy, connect_timeout, read_timeout,
    ):
        seen.append(url)
        return "<html><a href='/next'>n</a></html>", 10.0

    ctx = _session_context()
    with patch("nostrax.crawler.aiohttp.ClientSession", return_value=ctx):
        urls = crawl("https://example.com", fetcher=my_fetcher)

    assert seen == ["https://example.com"]
    assert "https://example.com/next" in urls


def test_custom_extractor_replaces_default():
    """A user-supplied extractor must get the fetched html and its URLs returned."""

    def my_extractor(html, base_url, *, tags, deduplicate, include_metadata, depth):
        assert "<body>" in html
        return [UrlResult(url="https://override.example/x", depth=depth)]

    # Stub the fetcher too so we do not need a mock aiohttp response
    async def stub_fetcher(
        session, url, *, timeout, max_response_size, retries,
        proxy, connect_timeout, read_timeout,
    ):
        return "<body>whatever</body>", 5.0

    ctx = _session_context()
    with patch("nostrax.crawler.aiohttp.ClientSession", return_value=ctx):
        urls = crawl(
            "https://example.com",
            fetcher=stub_fetcher,
            extractor=my_extractor,
        )

    assert urls == ["https://override.example/x"]


def test_default_fetcher_and_extractor_still_work_when_unset():
    """Omitting both arguments uses the built-in fetch_page + extract_urls."""

    async def passthrough_fetcher(
        session, url, *, timeout, max_response_size, retries,
        proxy, connect_timeout, read_timeout,
    ):
        # Use the real HTML that the default extractor knows how to handle.
        return '<html><body><a href="/page">x</a></body></html>', 1.0

    ctx = _session_context()
    with patch("nostrax.crawler.aiohttp.ClientSession", return_value=ctx):
        urls = crawl("https://example.com", fetcher=passthrough_fetcher)

    assert urls == ["https://example.com/page"]
