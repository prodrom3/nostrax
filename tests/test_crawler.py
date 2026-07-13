"""Tests for nostrax.crawler."""

import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nostrax.crawler import crawl, crawl_seeds, fetch_page
from nostrax.exceptions import NostraxError


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
    text,
    status=200,
    content_length=None,
    content_type="text/html",
    charset="utf-8",
    headers=None,
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
    mock_resp.headers = headers if headers is not None else {}
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

    await fetch_page(mock_session, "https://example.com", proxy="http://proxy:8080")

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
        mock_session,
        "https://example.com",
        timeout=30,
        connect_timeout=5,
        read_timeout=15,
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
async def test_fetch_page_does_not_retry_client_error_status(monkeypatch):
    """A deterministic 4xx (e.g. 404) is returned immediately without
    burning retry/backoff cycles - it will not change on a retry."""
    slept: list[float] = []

    async def fake_sleep(delay):
        slept.append(delay)

    monkeypatch.setattr("nostrax.crawler.asyncio.sleep", fake_sleep)

    mock_resp = _make_mock_response("nope", status=404)
    mock_session = AsyncMock()
    mock_session.get = MagicMock(return_value=mock_resp)

    html, _ = await fetch_page(mock_session, "https://example.com", retries=3)
    assert html is None
    assert mock_session.get.call_count == 1  # no retries
    assert slept == []  # no backoff sleeps


@pytest.mark.asyncio
async def test_fetch_page_retries_server_error_status(monkeypatch):
    """A 5xx is transient, so it is retried up to the retry budget."""

    async def fake_sleep(delay):
        return None

    monkeypatch.setattr("nostrax.crawler.asyncio.sleep", fake_sleep)

    mock_resp = _make_mock_response("boom", status=503)
    mock_session = AsyncMock()
    mock_session.get = MagicMock(return_value=mock_resp)

    html, _ = await fetch_page(mock_session, "https://example.com", retries=2)
    assert html is None
    assert mock_session.get.call_count == 3  # initial + 2 retries


def test_parse_retry_after_seconds():
    from nostrax.crawler import _parse_retry_after

    assert _parse_retry_after("30") == 30.0
    assert _parse_retry_after("  0 ") == 0.0
    assert _parse_retry_after(None) is None
    assert _parse_retry_after("") is None
    assert _parse_retry_after("garbage") is None


def test_parse_retry_after_http_date():
    from nostrax.crawler import _parse_retry_after

    # A date far in the future yields a large positive delay; a past date
    # clamps to 0.
    future = _parse_retry_after("Wed, 21 Oct 2099 07:28:00 GMT")
    assert future is not None and future > 0
    past = _parse_retry_after("Wed, 21 Oct 2015 07:28:00 GMT")
    assert past == 0.0


@pytest.mark.asyncio
async def test_fetch_page_honours_retry_after(monkeypatch):
    """A 503 with Retry-After waits exactly that long (capped), not jitter."""
    slept: list[float] = []

    async def fake_sleep(delay):
        slept.append(delay)

    monkeypatch.setattr("nostrax.crawler.asyncio.sleep", fake_sleep)

    mock_resp = _make_mock_response("busy", status=503, headers={"Retry-After": "7"})
    mock_session = AsyncMock()
    mock_session.get = MagicMock(return_value=mock_resp)

    html, _ = await fetch_page(mock_session, "https://example.com", retries=1)
    assert html is None
    assert slept == [7.0]  # honoured the header, not random jitter


@pytest.mark.asyncio
async def test_fetch_page_caps_retry_after(monkeypatch):
    """An absurd Retry-After is clamped to MAX_RETRY_AFTER."""
    from nostrax.crawler import MAX_RETRY_AFTER

    slept: list[float] = []

    async def fake_sleep(delay):
        slept.append(delay)

    monkeypatch.setattr("nostrax.crawler.asyncio.sleep", fake_sleep)

    mock_resp = _make_mock_response("busy", status=429, headers={"Retry-After": "999999"})
    mock_session = AsyncMock()
    mock_session.get = MagicMock(return_value=mock_resp)

    await fetch_page(mock_session, "https://example.com", retries=1)
    assert slept == [MAX_RETRY_AFTER]


@pytest.mark.asyncio
async def test_fetch_page_retries_429_rate_limited(monkeypatch):
    """429 Too Many Requests is retryable even though it is a 4xx."""

    async def fake_sleep(delay):
        return None

    monkeypatch.setattr("nostrax.crawler.asyncio.sleep", fake_sleep)

    mock_resp = _make_mock_response("slow down", status=429)
    mock_session = AsyncMock()
    mock_session.get = MagicMock(return_value=mock_resp)

    html, _ = await fetch_page(mock_session, "https://example.com", retries=1)
    assert html is None
    assert mock_session.get.call_count == 2  # initial + 1 retry


@pytest.mark.asyncio
async def test_fetch_page_skips_large_content_length():
    mock_resp = _make_mock_response("big", content_length=20_000_000)
    mock_session = AsyncMock()
    mock_session.get = MagicMock(return_value=mock_resp)

    html, resp_time = await fetch_page(
        mock_session, "https://example.com", max_response_size=10_000_000
    )
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


def test_crawl_honours_robots_crawl_delay():
    """When robots.txt declares a Crawl-delay stricter than --rate-limit,
    the crawler rebuilds its per-host limiter with the larger interval."""
    from nostrax.crawler import PerHostRateLimiter as _RealLimiter

    constructed: list[float] = []

    class RecordingLimiter(_RealLimiter):
        def __init__(self, interval):
            constructed.append(interval)
            super().__init__(interval)

    with patch("nostrax.crawler.RobotsChecker") as RobotsClass:
        robots = RobotsClass.return_value
        robots.load = AsyncMock()
        robots.is_allowed = MagicMock(return_value=True)
        robots.crawl_delay = MagicMock(return_value=0.3)

        with patch("nostrax.crawler.PerHostRateLimiter", RecordingLimiter):
            with patch("nostrax.crawler.aiohttp.ClientSession") as mock_cls:
                mock_session = AsyncMock()
                mock_session.get = MagicMock(return_value=_make_mock_response(SAMPLE_HTML))
                mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
                mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

                crawl("https://example.com", respect_robots=True, rate_limit=0.1)

    assert 0.3 in constructed  # limiter rebuilt with the robots Crawl-delay


def test_crawl_discovers_sitemaps_from_robots():
    """--sitemap consults robots.txt Sitemap: directives, not just the
    conventional /sitemap.xml path."""
    robots_txt = "User-agent: *\nDisallow:\nSitemap: https://example.com/custom-sitemap.xml\n"
    custom_sitemap = (
        '<?xml version="1.0"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        "<url><loc>https://example.com/from-robots-sitemap</loc></url>"
        "</urlset>"
    )

    def get_side_effect(url, **kwargs):
        if url.endswith("/robots.txt"):
            return _make_mock_response(robots_txt)
        if url.endswith("/custom-sitemap.xml"):
            return _make_mock_response(custom_sitemap)
        if url.endswith("/sitemap.xml"):
            return _make_mock_response("not xml", status=404)
        return _make_mock_response("<html><body></body></html>")

    with patch("nostrax.crawler.aiohttp.ClientSession") as mock_cls:
        mock_session = AsyncMock()
        mock_session.get = MagicMock(side_effect=get_side_effect)
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        results = crawl("https://example.com", use_sitemap=True, include_metadata=True)

    urls = {r.url for r in results}
    assert "https://example.com/from-robots-sitemap" in urls


def test_resume_continues_interrupted_frontier(tmp_path, monkeypatch):
    """A crawl whose pages fail mid-run persists the un-crawled frontier;
    a resume retries them and reaches pages that were never discoverable
    before. This is the core of true resumability (not just result reload)."""
    monkeypatch.chdir(tmp_path)
    cache_dir = str(tmp_path / "c")

    pages = {
        "https://site.test": '<a href="https://site.test/a">a</a>',
        "https://site.test/a": '<a href="https://site.test/b">b</a>',
        "https://site.test/b": "leaf",
    }
    fail = {"urls": {"https://site.test/a"}}
    fetched: list[str] = []

    async def fake_fetch(session, url, **kw):
        key = url.rstrip("/")
        if key in fail["urls"]:
            return (None, 1.0)
        body = pages.get(key)
        if body is not None:
            fetched.append(key)
        return (body, 1.0)

    # Run 1: /a fails, so /b is never discovered. /a must be persisted.
    crawl(
        "https://site.test",
        depth=5,
        cache_dir=cache_dir,
        include_metadata=True,
        fetcher=fake_fetch,
    )
    frontier = json.load(open(os.path.join(cache_dir, "frontier.json")))
    assert ["https://site.test/a", 1] in frontier

    # Run 2: failure cleared. Resume retries /a and then reaches /b.
    fail["urls"] = set()
    fetched.clear()
    r2 = crawl(
        "https://site.test",
        depth=5,
        cache_dir=cache_dir,
        include_metadata=True,
        fetcher=fake_fetch,
    )
    got = {r.url for r in r2}
    assert "https://site.test/a" in fetched  # retried
    assert "https://site.test/b" in got  # newly reached after resume
    # Fully crawled now -> frontier cleared.
    assert json.load(open(os.path.join(cache_dir, "frontier.json"))) == []


def test_crawl_seeds_merges_across_domains_and_isolates_failures():
    pages = {
        "https://a.test": '<a href="https://a.test/1">1</a>',
        "https://a.test/1": "leaf",
        "https://b.test": '<a href="https://b.test/2">2</a>',
        "https://b.test/2": "leaf",
    }

    async def fake_fetch(session, url, **kw):
        return (pages.get(url.rstrip("/")), 1.0)

    res = crawl_seeds(
        ["https://a.test", "https://b.test", "https://dead.test"],
        depth=2,
        include_metadata=True,
        fetcher=fake_fetch,
    )
    urls = {r.url for r in res}
    assert "https://a.test/1" in urls  # from seed 1's domain
    assert "https://b.test/2" in urls  # from seed 2's domain (multi-domain)
    # The dead seed was skipped, not fatal.


def test_crawl_seeds_all_fail_raises():
    async def fake_fetch(session, url, **kw):
        return (None, 1.0)

    with pytest.raises(NostraxError):
        crawl_seeds(["https://dead1.test", "https://dead2.test"], fetcher=fake_fetch)


def test_crawl_seeds_rejects_cache_dir():
    with pytest.raises(ValueError):
        crawl_seeds(["https://a.test"], cache_dir="cache")


def test_crawl_rotates_proxy_pool_across_fetches():
    """With a proxy pool, successive page fetches go out through different
    proxies (round-robin), so egress is spread across IPs."""
    pages = {
        "https://p.test": '<a href="https://p.test/1">1</a><a href="https://p.test/2">2</a>',
        "https://p.test/1": "leaf",
        "https://p.test/2": "leaf",
    }
    used_proxies: list[str] = []

    async def fake_fetch(session, url, *, proxy=None, **kw):
        used_proxies.append(proxy)
        return (pages.get(url.rstrip("/")), 1.0)

    crawl(
        "https://p.test",
        depth=1,
        fetcher=fake_fetch,
        proxies=["http://a:1", "http://b:2"],
    )
    # 3 pages fetched; proxies rotate round-robin over the pool of 2.
    assert len(used_proxies) == 3
    assert set(used_proxies) == {"http://a:1", "http://b:2"}
    assert used_proxies[0] != used_proxies[1]  # actually alternating


def test_crawl_auto_throttle_runs():
    """Smoke: auto_throttle uses the adaptive limiter without breaking a crawl."""
    pages = {
        "https://t.test": '<a href="https://t.test/1">1</a>',
        "https://t.test/1": "leaf",
    }

    async def fake_fetch(session, url, **kw):
        return (pages.get(url.rstrip("/")), 5.0)

    results = crawl(
        "https://t.test",
        depth=1,
        fetcher=fake_fetch,
        auto_throttle=True,
        auto_throttle_max_delay=2.0,
    )
    assert "https://t.test/1" in results


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
        mock_session.head = MagicMock(return_value=_make_mock_response("", status=204))
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
