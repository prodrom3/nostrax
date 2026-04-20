"""Async recursive web crawler built on top of the extractor.

Copyright (c) 2024 prodrom3 / radamic
Licensed under the MIT License.
"""

import asyncio
import logging
import random
import time
from collections.abc import Callable
from functools import partial
from urllib.parse import urlparse, urljoin

import aiohttp

from nostrax.cache import CrawlCache
from nostrax.exceptions import FetchError
from nostrax.extractor import extract_urls
from nostrax.models import UrlResult
from nostrax.normalize import normalize_url
from nostrax.resolver import SafeResolver
from nostrax.robots import RobotsChecker
from nostrax.sitemap import fetch_sitemap
from nostrax.validation import redact_credentials

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 10
DEFAULT_USER_AGENT = "nostrax/1.0"
DEFAULT_MAX_CONCURRENT = 10
DEFAULT_MAX_URLS = 50000
DEFAULT_MAX_RESPONSE_SIZE = 10 * 1024 * 1024  # 10 MB
DEFAULT_RETRIES = 2
DEFAULT_DNS_CACHE_TTL = 300  # 5 minutes

_HTML_CONTENT_TYPES = ("text/html", "application/xhtml+xml")


class PerHostRateLimiter:
    """Enforces a minimum interval between requests to the same host.

    The old implementation ran ``await asyncio.sleep(rate_limit)`` before
    every fetch, applied globally. A multi-domain crawl that asked for
    1 req/s therefore capped the whole crawl at 1 req/s even across
    unrelated hosts, and concurrent tasks that slept at the same instant
    still woke up in lockstep.

    This limiter keys by ``urlparse(url).netloc``. Each host has its own
    ``asyncio.Lock`` so waits are serialised per-host, and ``_last[host]``
    records the most recent wait completion so the next caller for that
    host sleeps just long enough to land on the next allowed slot.
    """

    def __init__(self, min_interval: float) -> None:
        self._min_interval = float(min_interval)
        self._last: dict[str, float] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    async def wait(self, host: str) -> None:
        if self._min_interval <= 0 or not host:
            return
        lock = self._locks.get(host)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[host] = lock
        async with lock:
            last = self._last.get(host, 0.0)
            now = time.monotonic()
            deficit = last + self._min_interval - now
            if deficit > 0:
                await asyncio.sleep(deficit)
            self._last[host] = time.monotonic()


def _build_timeout(
    total: int | float,
    connect: float | None = None,
    read: float | None = None,
) -> aiohttp.ClientTimeout:
    """Assemble an aiohttp.ClientTimeout from separated budgets.

    ``total`` bounds the whole request. ``connect`` bounds connection
    acquisition (TLS handshake, pool wait). ``read`` bounds each socket
    read, which catches slow-drip responses that would otherwise consume
    the entire total budget one byte at a time. ``None`` means "no
    per-phase cap, fall back to the total".
    """
    return aiohttp.ClientTimeout(total=total, connect=connect, sock_read=read)


async def fetch_page(
    session: aiohttp.ClientSession,
    url: str,
    *,
    timeout: int = DEFAULT_TIMEOUT,
    max_response_size: int = DEFAULT_MAX_RESPONSE_SIZE,
    retries: int = DEFAULT_RETRIES,
    proxy: str | None = None,
    connect_timeout: float | None = None,
    read_timeout: float | None = None,
) -> tuple[str | None, float]:
    """Fetch a web page and return (html, response_time_ms).

    Uses the shared aiohttp session for connection pooling.
    Retries transient failures with exponential backoff.
    Skips non-HTML responses and oversized responses.
    Returns (None, 0) on failure.
    """
    client_timeout = _build_timeout(timeout, connect_timeout, read_timeout)
    for attempt in range(1 + retries):
        start = time.monotonic()
        try:
            async with session.get(
                url,
                timeout=client_timeout,
                allow_redirects=False,
                proxy=proxy,
            ) as response:
                elapsed = (time.monotonic() - start) * 1000

                # Check Content-Type before reading body
                content_type = response.content_type or ""
                if content_type and not any(
                    ct in content_type for ct in _HTML_CONTENT_TYPES
                ):
                    logger.debug("Skipping non-HTML %s: %s", url, content_type)
                    return None, elapsed

                response.raise_for_status()

                content_length = response.content_length
                if content_length is not None and content_length > max_response_size:
                    logger.warning(
                        "Skipping %s: response too large (%d bytes)", url, content_length
                    )
                    return None, elapsed

                body = await response.content.read(max_response_size + 1)
                if len(body) > max_response_size:
                    logger.warning(
                        "Skipping %s: response exceeded %d byte limit",
                        url, max_response_size,
                    )
                    return None, elapsed

                # response.charset returns the Content-Type charset or None.
                # We avoid aiohttp's get_encoding() because it raises
                # RuntimeError on a body read via .content.read() (no
                # charset in header and no internal buffer to sniff).
                text = body.decode(
                    response.charset or "utf-8", errors="replace"
                )
                return text, elapsed

        except (aiohttp.ClientError, TimeoutError) as e:
            elapsed = (time.monotonic() - start) * 1000
            if attempt < retries:
                # Full-jitter backoff (AWS Architecture Blog). Removes the
                # lockstep retries that thunder a rate-limited target.
                delay = random.uniform(0, 2 ** attempt)
                logger.debug(
                    "Retry %d/%d for %s after %.0fms (waiting %.2fs): %s",
                    attempt + 1, retries, url, elapsed, delay, e,
                )
                await asyncio.sleep(delay)
            else:
                logger.error("Failed to fetch %s after %d attempts: %s", url, 1 + retries, e)
                return None, elapsed

    return None, 0


async def _attach_statuses(
    session: aiohttp.ClientSession,
    results: list[UrlResult],
    semaphore: asyncio.Semaphore,
    *,
    timeout: int,
    proxy: str | None,
    connect_timeout: float | None,
    read_timeout: float | None,
) -> None:
    """HEAD every discovered URL on the same session and attach r.status.

    Runs as a post-crawl phase so the HEAD probes reuse the session, its
    DNS cache, its SafeResolver, and its connection pool. Bounded by the
    same semaphore the crawl used, so we do not burst past the target's
    concurrency budget.
    """
    from nostrax.status import check_url_status

    async def _probe(r: UrlResult) -> None:
        async with semaphore:
            r.status = await check_url_status(
                session, r.url,
                timeout=timeout,
                proxy=proxy,
                connect_timeout=connect_timeout,
                read_timeout=read_timeout,
            )

    await asyncio.gather(*(_probe(r) for r in results))


async def crawl_async(
    url: str,
    *,
    depth: int = 0,
    tags: set[str] | None = None,
    deduplicate: bool = True,
    timeout: int = DEFAULT_TIMEOUT,
    connect_timeout: float | None = None,
    read_timeout: float | None = None,
    user_agent: str = DEFAULT_USER_AGENT,
    max_concurrent: int = DEFAULT_MAX_CONCURRENT,
    respect_robots: bool = False,
    max_urls: int = DEFAULT_MAX_URLS,
    max_response_size: int = DEFAULT_MAX_RESPONSE_SIZE,
    rate_limit: float = 0,
    proxy: str | None = None,
    auth: tuple[str, str] | None = None,
    use_sitemap: bool = False,
    include_metadata: bool = False,
    progress_callback: Callable[[int, int], None] | None = None,
    retries: int = DEFAULT_RETRIES,
    scope: str | None = None,
    strategy: str = "dfs",
    cache_dir: str | None = None,
    check_status: bool = False,
) -> list[str] | list[UrlResult]:
    """Crawl a URL and optionally follow links concurrently.

    Args:
        url: Starting URL.
        depth: How many levels deep to follow links. 0 means only the initial page.
        tags: HTML tags to extract URLs from.
        deduplicate: Remove duplicate URLs from results.
        timeout: Request timeout in seconds.
        user_agent: User-Agent header string.
        max_concurrent: Max number of concurrent HTTP requests.
        respect_robots: Whether to check robots.txt before fetching.
        max_urls: Stop crawling after collecting this many URLs.
        max_response_size: Skip responses larger than this (bytes).
        rate_limit: Minimum seconds between requests (0 = no limit).
        proxy: Proxy URL (e.g. "http://proxy:8080").
        auth: Tuple of (username, password) for HTTP basic auth.
        use_sitemap: Also parse sitemap.xml for URLs.
        include_metadata: Return UrlResult objects instead of plain strings.
        progress_callback: Called with (pages_crawled, urls_found) after each page.
        retries: Number of retry attempts for failed requests.
        scope: URL path prefix to restrict crawling to (e.g. "/docs/").
        strategy: Crawl strategy - "dfs" (depth-first) or "bfs" (breadth-first).
        cache_dir: Directory to cache crawl state for resume support.
        check_status: When True, HEAD every discovered URL with the same
            aiohttp session used for the crawl and attach the status code
            to each UrlResult. Requires ``include_metadata=True``.

    Returns:
        List of discovered URLs (str) or UrlResult objects.
    """
    if check_status and not include_metadata:
        raise ValueError(
            "check_status=True requires include_metadata=True to attach status to results"
        )
    base_parsed = urlparse(url)
    base_domain = base_parsed.netloc
    rate_limiter = PerHostRateLimiter(rate_limit)
    visited: set[str] = set()
    all_results: list[UrlResult] = []
    semaphore = asyncio.Semaphore(max_concurrent)
    robots = RobotsChecker(user_agent) if respect_robots else None
    loop = asyncio.get_running_loop()
    pages_crawled = 0

    # Cache/resume support
    cache = None
    had_cached_results = False
    if cache_dir:
        cache = CrawlCache(cache_dir)
        cache.initialize()
        visited = cache.visited
        cached_results = cache.load_results()
        if cached_results:
            all_results.extend(cached_results)
            had_cached_results = True
            logger.info("Resumed with %d cached results", len(cached_results))

    basic_auth = aiohttp.BasicAuth(auth[0], auth[1]) if auth else None

    connector = aiohttp.TCPConnector(
        limit=max_concurrent,
        limit_per_host=max_concurrent,
        ttl_dns_cache=DEFAULT_DNS_CACHE_TTL,
        use_dns_cache=True,
        resolver=SafeResolver(),
    )
    headers = {"User-Agent": user_agent}

    if proxy:
        logger.debug("Using proxy %s for all outbound fetches", redact_credentials(proxy))

    try:
        async with aiohttp.ClientSession(
            connector=connector,
            headers=headers,
            auth=basic_auth,
        ) as session:
            if robots:
                await robots.load(
                    session, url,
                    timeout=timeout,
                    proxy=proxy,
                    connect_timeout=connect_timeout,
                    read_timeout=read_timeout,
                )

            # Optionally fetch sitemap.xml
            if use_sitemap:
                sitemap_url = urljoin(
                    f"{base_parsed.scheme}://{base_parsed.netloc}", "/sitemap.xml"
                )
                sitemap_urls = await fetch_sitemap(
                    session, sitemap_url,
                    timeout=timeout,
                    proxy=proxy,
                    connect_timeout=connect_timeout,
                    read_timeout=read_timeout,
                )
                for su in sitemap_urls:
                    all_results.append(
                        UrlResult(url=su, source="sitemap.xml", tag="sitemap", depth=0)
                    )

            def _should_follow(link: str) -> bool:
                """Check if a link should be followed based on domain and scope."""
                parsed = urlparse(link)
                if parsed.netloc != base_domain:
                    return False
                if scope and not parsed.path.startswith(scope):
                    return False
                normalized = normalize_url(link)
                return normalized not in visited

            # Unified engine: a frontier queue + max_concurrent workers.
            # DFS uses LifoQueue (last-in first-out = deepen first); BFS
            # uses FIFO Queue. Workers pull, fetch, enqueue children, and
            # mark task_done() so frontier.join() can detect completion.
            # max_concurrent workers replace the old per-request
            # Semaphore: having exactly N workers gives the same bound
            # without the extra primitive.
            frontier: asyncio.Queue[tuple[str, int]] = (
                asyncio.LifoQueue() if strategy == "dfs" else asyncio.Queue()
            )
            await frontier.put((url, 0))

            async def _process_one(current_url: str, current_depth: int) -> None:
                nonlocal pages_crawled

                normalized = normalize_url(current_url)
                if normalized in visited:
                    return
                visited.add(normalized)

                if cache:
                    cache.mark_visited(normalized)

                if len(all_results) >= max_urls:
                    return

                if robots and not robots.is_allowed(current_url):
                    logger.info("Blocked by robots.txt: %s", current_url)
                    return

                await rate_limiter.wait(urlparse(current_url).netloc)

                logger.info("Crawling [depth=%d]: %s", current_depth, current_url)
                html, resp_time = await fetch_page(
                    session, current_url,
                    timeout=timeout,
                    max_response_size=max_response_size,
                    retries=retries,
                    proxy=proxy,
                    connect_timeout=connect_timeout,
                    read_timeout=read_timeout,
                )

                if html is None:
                    return

                found = await loop.run_in_executor(
                    None,
                    partial(
                        extract_urls, html, current_url,
                        tags=tags, deduplicate=False,
                        include_metadata=True, depth=current_depth,
                    ),
                )

                for r in found:
                    r.response_time = resp_time
                all_results.extend(found)

                if cache:
                    for r in found:
                        cache.save_result(r)

                pages_crawled += 1
                if progress_callback is not None:
                    progress_callback(pages_crawled, len(all_results))

                if len(all_results) >= max_urls:
                    logger.warning(
                        "Reached max URL limit (%d), stopping crawl.", max_urls
                    )
                    return

                if current_depth < depth:
                    for result in found:
                        if _should_follow(result.url):
                            await frontier.put((result.url, current_depth + 1))

            # Capture the first exception raised inside any worker so it
            # propagates out of crawl_async after frontier.join() completes.
            # fetch_page already swallows ClientError / TimeoutError, so
            # anything that escapes _process_one is either a real bug or a
            # caller-visible failure (Boom from a test, KeyboardInterrupt
            # surfaced as a regular Exception, etc.) and must not be lost.
            first_error: list[BaseException | None] = [None]

            async def _worker() -> None:
                while True:
                    current_url, current_depth = await frontier.get()
                    try:
                        if first_error[0] is not None:
                            continue
                        await _process_one(current_url, current_depth)
                    except Exception as e:
                        logger.error(
                            "Worker failed on %s: %s", current_url, e, exc_info=True
                        )
                        if first_error[0] is None:
                            first_error[0] = e
                    finally:
                        frontier.task_done()

            workers = [
                asyncio.create_task(_worker()) for _ in range(max_concurrent)
            ]
            try:
                await frontier.join()
            finally:
                for w in workers:
                    w.cancel()
                await asyncio.gather(*workers, return_exceptions=True)

            if first_error[0] is not None:
                raise first_error[0]

            if check_status and all_results:
                await _attach_statuses(
                    session, all_results, semaphore,
                    timeout=timeout,
                    proxy=proxy,
                    connect_timeout=connect_timeout,
                    read_timeout=read_timeout,
                )

    finally:
        if cache:
            try:
                cache.save_visited()
            finally:
                cache.close()

    if pages_crawled == 0 and not had_cached_results:
        raise FetchError(
            url,
            "no pages were successfully fetched; check connectivity, "
            "robots.txt, and logs for details",
        )

    if deduplicate:
        seen: set[str] = set()
        unique: list[UrlResult] = []
        for r in all_results:
            norm = normalize_url(r.url)
            if norm not in seen:
                seen.add(norm)
                unique.append(r)
        all_results = unique

    if include_metadata:
        return all_results
    return [r.url for r in all_results]


def crawl(
    url: str,
    *,
    depth: int = 0,
    tags: set[str] | None = None,
    deduplicate: bool = True,
    timeout: int = DEFAULT_TIMEOUT,
    connect_timeout: float | None = None,
    read_timeout: float | None = None,
    user_agent: str = DEFAULT_USER_AGENT,
    max_concurrent: int = DEFAULT_MAX_CONCURRENT,
    respect_robots: bool = False,
    max_urls: int = DEFAULT_MAX_URLS,
    max_response_size: int = DEFAULT_MAX_RESPONSE_SIZE,
    rate_limit: float = 0,
    proxy: str | None = None,
    auth: tuple[str, str] | None = None,
    use_sitemap: bool = False,
    include_metadata: bool = False,
    retries: int = DEFAULT_RETRIES,
    scope: str | None = None,
    strategy: str = "dfs",
    cache_dir: str | None = None,
    check_status: bool = False,
) -> list[str] | list[UrlResult]:
    """Synchronous wrapper around crawl_async for simple usage."""
    return asyncio.run(
        crawl_async(
            url,
            depth=depth,
            tags=tags,
            deduplicate=deduplicate,
            timeout=timeout,
            connect_timeout=connect_timeout,
            read_timeout=read_timeout,
            user_agent=user_agent,
            max_concurrent=max_concurrent,
            respect_robots=respect_robots,
            max_urls=max_urls,
            max_response_size=max_response_size,
            rate_limit=rate_limit,
            proxy=proxy,
            auth=auth,
            use_sitemap=use_sitemap,
            include_metadata=include_metadata,
            retries=retries,
            scope=scope,
            strategy=strategy,
            cache_dir=cache_dir,
            check_status=check_status,
        )
    )
