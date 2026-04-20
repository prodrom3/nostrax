"""Tests for nostrax.crawler."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nostrax.crawler import crawl, crawl_async, fetch_page


SAMPLE_HTML = """
<html><body>
    <a href="/page2">Page 2</a>
    <a href="https://example.com/page3">Page 3</a>
    <a href="https://external.com/other">External</a>
</body></html>
"""

SAMPLE_HTML_PAGE2 = """
<html><body>
    <a href="/page4">Page 4</a>
</body></html>
"""


def _make_mock_response(text, status=200, content_length=None, content_type="text/html"):
    """Create a mock aiohttp response usable as an async context manager.

    The response object is returned from `session.get(...)` and is then
    entered via `async with ... as response`. We wire `__aenter__` to yield
    the same mock so configured attributes actually reach the code under test.
    """
    encoded = text.encode("utf-8")
    mock_resp = AsyncMock()
    mock_resp.status = status
    mock_resp.content_length = content_length
    mock_resp.content_type = content_type
    mock_resp.raise_for_status = MagicMock()
    mock_resp.get_encoding = MagicMock(return_value="utf-8")

    mock_content = MagicMock()
    mock_content.read = AsyncMock(return_value=encoded)
    mock_resp.content = mock_content

    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)

    return mock_resp


@pytest.mark.asyncio
async def test_fetch_page_success():
    mock_resp = _make_mock_response("<html>OK</html>")
    mock_session = AsyncMock()
    mock_session.get = MagicMock(return_value=mock_resp)

    html, resp_time = await fetch_page(mock_session, "https://example.com")
    assert html == "<html>OK</html>"
    assert resp_time >= 0


@pytest.mark.asyncio
async def test_fetch_page_failure():
    import aiohttp

    mock_session = AsyncMock()
    mock_session.get = MagicMock(side_effect=aiohttp.ClientError("fail"))

    html, resp_time = await fetch_page(mock_session, "https://example.com")
    assert html is None


@pytest.mark.asyncio
async def test_fetch_page_skips_large_content_length():
    mock_resp = _make_mock_response("big", content_length=20_000_000)
    mock_session = AsyncMock()
    mock_session.get = MagicMock(return_value=mock_resp)

    html, resp_time = await fetch_page(mock_session, "https://example.com", max_response_size=10_000_000)
    assert html is None


@pytest.mark.asyncio
async def test_fetch_page_skips_large_body():
    big_body = "x" * 1001
    mock_resp = _make_mock_response(big_body, content_length=None)
    mock_session = AsyncMock()
    mock_session.get = MagicMock(return_value=mock_resp)

    html, resp_time = await fetch_page(mock_session, "https://example.com", max_response_size=1000)
    assert html is None


def test_crawl_depth_zero():
    with patch("nostrax.crawler.aiohttp.ClientSession") as mock_cls:
        mock_session = AsyncMock()
        mock_resp = _make_mock_response(SAMPLE_HTML)
        mock_session.get = MagicMock(return_value=mock_resp)
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        urls = crawl("https://example.com")
        assert "https://example.com/page2" in urls
        assert "https://example.com/page3" in urls
        assert "https://external.com/other" in urls


def test_crawl_depth_one():
    def get_side_effect(url, **kwargs):
        pages = {
            "https://example.com": SAMPLE_HTML,
            "https://example.com/page2": SAMPLE_HTML_PAGE2,
            "https://example.com/page3": "<html><body></body></html>",
        }
        html = pages.get(url, "<html></html>")
        return _make_mock_response(html)

    with patch("nostrax.crawler.aiohttp.ClientSession") as mock_cls:
        mock_session = AsyncMock()
        mock_session.get = MagicMock(side_effect=get_side_effect)
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        urls = crawl("https://example.com", depth=1)
        assert "https://example.com/page2" in urls
        assert "https://example.com/page3" in urls
        assert "https://example.com/page4" in urls
        assert "https://external.com/other" in urls


def test_crawl_deduplicates():
    html = """
    <html><body>
        <a href="/same">Link 1</a>
        <a href="/same">Link 2</a>
    </body></html>
    """
    with patch("nostrax.crawler.aiohttp.ClientSession") as mock_cls:
        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=_make_mock_response(html))
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        urls = crawl("https://example.com")
        assert urls.count("https://example.com/same") == 1


def test_crawl_fetch_failure():
    import aiohttp as aio

    with patch("nostrax.crawler.aiohttp.ClientSession") as mock_cls:
        mock_session = AsyncMock()
        mock_session.get = MagicMock(side_effect=aio.ClientError("fail"))
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        urls = crawl("https://example.com")
        assert urls == []


def test_crawl_with_metadata():
    with patch("nostrax.crawler.aiohttp.ClientSession") as mock_cls:
        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=_make_mock_response(SAMPLE_HTML))
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        results = crawl("https://example.com", include_metadata=True)
        from nostrax.models import UrlResult
        assert all(isinstance(r, UrlResult) for r in results)
        assert results[0].source == "https://example.com"
