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


def _make_mock_response(
    text, status=200, content_length=None, content_type="text/html", charset="utf-8"
):
    """Create a mock aiohttp response usable as an async context manager.

    The response object is returned from `session.get(...)` and is then
    entered via `async with ... as response`. We wire `__aenter__` to yield
    the same mock so configured attributes actually reach the code under test.

    ``charset`` may be None to simulate a response whose Content-Type header
    omits the charset directive; fetch_page must default to utf-8 in that
    case without calling aiohttp's body-sniffing fallback.
    """
    encoded = text.encode("utf-8")
    mock_resp = AsyncMock()
    mock_resp.status = status
    mock_resp.content_length = content_length
    mock_resp.content_type = content_type
    mock_resp.charset = charset
    mock_resp.raise_for_status = MagicMock()

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
async def test_fetch_page_decodes_when_content_type_omits_charset():
    """A real aiohttp response with no charset in Content-Type (example.com
    does exactly this) must decode cleanly as utf-8 rather than triggering
    aiohttp's body-sniffing fallback, which raises when content was read via
    content.read() instead of text()."""
    mock_resp = _make_mock_response("<html>OK</html>", charset=None)
    mock_session = AsyncMock()
    mock_session.get = MagicMock(return_value=mock_resp)

    html, _ = await fetch_page(mock_session, "https://example.com")
    assert html == "<html>OK</html>"


@pytest.mark.asyncio
async def test_fetch_page_forwards_proxy_to_session():
    mock_resp = _make_mock_response("<html>OK</html>")
    mock_session = AsyncMock()
    mock_session.get = MagicMock(return_value=mock_resp)

    await fetch_page(
        mock_session, "https://example.com", proxy="http://proxy:8080"
    )

    _, kwargs = mock_session.get.call_args
    assert kwargs["proxy"] == "http://proxy:8080"
    assert kwargs["allow_redirects"] is False


@pytest.mark.asyncio
async def test_fetch_page_applies_separated_timeouts():
    """connect_timeout and read_timeout are threaded into ClientTimeout
    alongside the total budget, not silently dropped."""
    mock_resp = _make_mock_response("<html>OK</html>")
    mock_session = AsyncMock()
    mock_session.get = MagicMock(return_value=mock_resp)

    await fetch_page(
        mock_session, "https://example.com",
        timeout=30, connect_timeout=5, read_timeout=15,
    )

    _, kwargs = mock_session.get.call_args
    ct = kwargs["timeout"]
    assert ct.total == 30
    assert ct.connect == 5
    assert ct.sock_read == 15


@pytest.mark.asyncio
async def test_fetch_page_uses_full_jitter_backoff(monkeypatch):
    """Retry delays are drawn from random.uniform(0, 2**attempt), not 2**attempt flat."""
    import aiohttp

    mock_session = AsyncMock()
    mock_session.get = MagicMock(side_effect=aiohttp.ClientError("fail"))

    observed_ranges: list[tuple[float, float]] = []
    observed_sleeps: list[float] = []

    def fake_uniform(a, b):
        observed_ranges.append((a, b))
        return 0.0  # deterministic, zero wait

    async def fake_sleep(delay):
        observed_sleeps.append(delay)

    monkeypatch.setattr("nostrax.crawler.random.uniform", fake_uniform)
    monkeypatch.setattr("nostrax.crawler.asyncio.sleep", fake_sleep)

    html, _ = await fetch_page(mock_session, "https://example.com", retries=3)
    assert html is None
    assert observed_ranges == [(0, 1), (0, 2), (0, 4)]
    assert observed_sleeps == [0.0, 0.0, 0.0]


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


def test_crawl_saves_cache_on_unexpected_exception(tmp_path, monkeypatch):
    """crawl_async wraps the session block in try/finally so that even an
    exception raised mid-crawl (SIGINT-as-KeyboardInterrupt, connection
    reset, anything) leaves the visited-set flushed to disk for resume."""
    monkeypatch.chdir(tmp_path)
    cache_dir = str(tmp_path / "cache")

    import aiohttp as aio

    class Boom(Exception):
        pass

    def raising_get(*args, **kwargs):
        # First GET succeeds and populates visited; second raises Boom.
        if raising_get.calls == 0:
            raising_get.calls += 1
            return _make_mock_response(SAMPLE_HTML)
        raise Boom("simulated interrupt")
    raising_get.calls = 0

    with patch("nostrax.crawler.aiohttp.ClientSession") as mock_cls:
        mock_session = AsyncMock()
        mock_session.get = MagicMock(side_effect=raising_get)
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        import pytest
        with pytest.raises(Boom):
            crawl("https://example.com", depth=1, cache_dir=cache_dir)

    # The visited file must exist even though the crawl raised.
    import json
    visited_path = tmp_path / "cache" / "visited.json"
    assert visited_path.is_file(), "visited cache was not flushed on exception"
    visited = json.loads(visited_path.read_text())
    assert any("example.com" in u for u in visited)


def test_crawl_check_status_requires_metadata():
    import pytest

    with pytest.raises(ValueError, match="include_metadata"):
        crawl("https://example.com", check_status=True, include_metadata=False)


def test_crawl_check_status_attaches_status_from_same_session():
    """check_status=True should reuse the crawl's session for HEAD probes
    and attach each status to the UrlResult without a second session."""
    with patch("nostrax.crawler.aiohttp.ClientSession") as mock_cls:
        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=_make_mock_response(SAMPLE_HTML))
        mock_session.head = MagicMock(
            return_value=_make_mock_response("", status=204)
        )
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        results = crawl(
            "https://example.com",
            include_metadata=True,
            check_status=True,
        )
        assert results, "expected some results"
        assert all(r.status == 204 for r in results)
        # Sanity: ClientSession was constructed exactly once (not a second
        # time for status probing).
        assert mock_cls.call_count == 1


def test_crawl_raises_fetch_error_when_start_unreachable():
    import aiohttp as aio

    from nostrax.exceptions import FetchError

    with patch("nostrax.crawler.aiohttp.ClientSession") as mock_cls:
        mock_session = AsyncMock()
        mock_session.get = MagicMock(side_effect=aio.ClientError("fail"))
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        with pytest.raises(FetchError) as exc_info:
            crawl("https://example.com")
        assert exc_info.value.url == "https://example.com"


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
