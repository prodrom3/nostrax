"""Tests for nostrax.status."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from nostrax.status import check_url_status, check_statuses


def _make_mock_response(status=200):
    mock_resp = AsyncMock()
    mock_resp.status = status
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)
    return mock_resp


@pytest.mark.asyncio
async def test_check_url_status_success():
    mock_session = AsyncMock()
    mock_session.head = MagicMock(return_value=_make_mock_response(200))

    result = await check_url_status(mock_session, "https://example.com")
    assert result == 200


@pytest.mark.asyncio
async def test_check_url_status_404():
    mock_session = AsyncMock()
    mock_session.head = MagicMock(return_value=_make_mock_response(404))

    result = await check_url_status(mock_session, "https://example.com/missing")
    assert result == 404


@pytest.mark.asyncio
async def test_check_url_status_failure():
    import aiohttp

    mock_session = AsyncMock()
    mock_session.head = MagicMock(side_effect=aiohttp.ClientError("fail"))

    result = await check_url_status(mock_session, "https://example.com")
    assert result is None


@pytest.mark.asyncio
async def test_check_url_status_forwards_proxy():
    mock_session = AsyncMock()
    mock_session.head = MagicMock(return_value=_make_mock_response(200))

    await check_url_status(
        mock_session, "https://example.com", proxy="http://proxy:8080"
    )

    _, kwargs = mock_session.head.call_args
    assert kwargs["proxy"] == "http://proxy:8080"
