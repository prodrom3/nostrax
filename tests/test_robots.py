"""Tests for nostrax.robots."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from nostrax.robots import RobotsChecker


ROBOTS_TXT = """
User-agent: *
Disallow: /private/
Disallow: /admin/
Allow: /

User-agent: nostrax
Disallow: /secret/
"""

ROBOTS_TXT_WITH_DELAY = """
User-agent: *
Crawl-delay: 2.5
Disallow: /private/
"""


def _make_mock_response(text, status=200):
    mock_resp = AsyncMock()
    mock_resp.status = status
    mock_resp.text = AsyncMock(return_value=text)
    mock_content = MagicMock()
    mock_content.read = AsyncMock(return_value=text.encode("utf-8"))
    mock_resp.content = mock_content
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)
    return mock_resp


@pytest.mark.asyncio
async def test_robots_crawl_delay_parsed():
    checker = RobotsChecker("nostrax/1.0")
    mock_session = AsyncMock()
    mock_session.get = MagicMock(return_value=_make_mock_response(ROBOTS_TXT_WITH_DELAY))

    await checker.load(mock_session, "https://example.com/page")
    assert checker.crawl_delay() == 2.5


def test_robots_crawl_delay_none_when_not_loaded():
    checker = RobotsChecker("nostrax/1.0")
    assert checker.crawl_delay() is None


@pytest.mark.asyncio
async def test_robots_crawl_delay_prefers_specific_agent():
    """A named group's Crawl-delay wins over the wildcard group, and a
    fractional value (which stdlib's parser silently drops) is honoured."""
    txt = "User-agent: *\nCrawl-delay: 10\n\nUser-agent: nostrax\nCrawl-delay: 0.5\n"
    checker = RobotsChecker("nostrax/1.0")
    mock_session = AsyncMock()
    mock_session.get = MagicMock(return_value=_make_mock_response(txt))
    await checker.load(mock_session, "https://example.com/page")
    assert checker.crawl_delay() == 0.5


@pytest.mark.asyncio
async def test_robots_sitemaps_discovered():
    txt = (
        "User-agent: *\n"
        "Disallow: /x/\n"
        "Sitemap: https://example.com/sitemap-a.xml\n"
        "Sitemap: https://example.com/sitemap-b.xml\n"
    )
    checker = RobotsChecker("nostrax/1.0")
    mock_session = AsyncMock()
    mock_session.get = MagicMock(return_value=_make_mock_response(txt))
    await checker.load(mock_session, "https://example.com/page")
    assert checker.sitemaps() == [
        "https://example.com/sitemap-a.xml",
        "https://example.com/sitemap-b.xml",
    ]


def test_robots_sitemaps_empty_when_not_loaded():
    assert RobotsChecker("nostrax/1.0").sitemaps() == []


@pytest.mark.asyncio
async def test_robots_allows_public_path():
    checker = RobotsChecker("nostrax/1.0")
    mock_session = AsyncMock()
    mock_session.get = MagicMock(return_value=_make_mock_response(ROBOTS_TXT))

    await checker.load(mock_session, "https://example.com/page")
    assert checker.is_allowed("https://example.com/public/page") is True


@pytest.mark.asyncio
async def test_robots_blocks_disallowed_path():
    checker = RobotsChecker("nostrax/1.0")
    mock_session = AsyncMock()
    mock_session.get = MagicMock(return_value=_make_mock_response(ROBOTS_TXT))

    await checker.load(mock_session, "https://example.com/page")
    assert checker.is_allowed("https://example.com/secret/data") is False


@pytest.mark.asyncio
async def test_robots_wildcard_blocks():
    checker = RobotsChecker("other-bot")
    mock_session = AsyncMock()
    mock_session.get = MagicMock(return_value=_make_mock_response(ROBOTS_TXT))

    await checker.load(mock_session, "https://example.com/page")
    assert checker.is_allowed("https://example.com/private/stuff") is False
    assert checker.is_allowed("https://example.com/admin/panel") is False


@pytest.mark.asyncio
async def test_robots_missing_allows_all():
    checker = RobotsChecker("nostrax/1.0")
    mock_session = AsyncMock()
    mock_session.get = MagicMock(return_value=_make_mock_response("", status=404))

    await checker.load(mock_session, "https://example.com/page")
    assert checker.is_allowed("https://example.com/anything") is True


@pytest.mark.asyncio
async def test_robots_not_loaded_allows_all():
    checker = RobotsChecker("nostrax/1.0")
    # Never call load
    assert checker.is_allowed("https://example.com/anything") is True


@pytest.mark.asyncio
async def test_robots_fetch_error_allows_all():
    import aiohttp

    checker = RobotsChecker("nostrax/1.0")
    mock_session = AsyncMock()
    mock_session.get = MagicMock(side_effect=aiohttp.ClientError("timeout"))

    await checker.load(mock_session, "https://example.com/page")
    assert checker.is_allowed("https://example.com/anything") is True
