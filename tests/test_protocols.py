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


def test_async_extractor_is_refused_with_a_pointed_error():
    """An async def extractor cannot be awaited by run_in_executor, so
    the crawler must refuse it up front rather than let it explode later."""

    async def async_extractor(
        html, base_url, *, tags, deduplicate, include_metadata, depth,
    ):
        return []

    # We do not even need to mock the session - the guard fires before
    # any network activity because the argument is validated early.
    with pytest.raises(TypeError, match="synchronous callable"):
        crawl("https://example.com", extractor=async_extractor)


def test_extractor_returning_strings_fails_fast_with_clear_error():
    """A custom Extractor that ignores include_metadata=True and returns
    list[str] must trigger a helpful TypeError, not a deep AttributeError
    when the crawler tries to set r.response_time on a string."""

    def bad_extractor(html, base_url, *, tags, deduplicate, include_metadata, depth):
        # Violates the protocol: should be list[UrlResult] when
        # include_metadata=True.
        return ["https://example.com/x"]

    async def stub_fetcher(
        session, url, *, timeout, max_response_size, retries,
        proxy, connect_timeout, read_timeout,
    ):
        return "<body>x</body>", 1.0

    ctx = _session_context()
    with patch("nostrax.crawler.aiohttp.ClientSession", return_value=ctx):
        with pytest.raises(TypeError, match="Extractor returned str"):
            crawl(
                "https://example.com",
                fetcher=stub_fetcher,
                extractor=bad_extractor,
            )


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
