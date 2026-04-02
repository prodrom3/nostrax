"""Tests for nostrax.robots."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from nostrax.robots import RobotsChecker


ROBOTS_TXT = """
User-agent: *
Disallow: /private/
Disallow: /admin/
Allow: /

User-agent: nostrax/1.0
Disallow: /secret/
"""


def _make_mock_response(text, status=200):
    mock_resp = AsyncMock()
    mock_resp.status = status
    mock_resp.text = AsyncMock(return_value=text)
    return mock_resp


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
