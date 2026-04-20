"""Async recursive web crawler built on top of the extractor.

Copyright (c) 2024 prodrom3 / radamic
Licensed under the MIT License.
Last updated: 2026-04-02
"""

import asyncio
import logging
import random
import time
from collections.abc import Callable
from collections import deque
from functools import partial
from urllib.parse import urlparse, urljoin

import aiohttp

from nostrax.cache import CrawlCache
from nostrax.exceptions import FetchError
from nostrax.extractor import extract_urls
from nostrax.models import UrlResult
from nostrax.normalize import normalize_url
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


async def fetch_page(
    session: aiohttp.ClientSession,
    url: str,
    *,
    timeout: int = DEFAULT_TIMEOUT,
    max_response_size: int = DEFAULT_MAX_RESPONSE_SIZE,
    retries: int = DEFAULT_RETRIES,
    proxy: str | None = None,
) -> tuple[str | None, float]:
    """Fetch a web page and return (html, response_time_ms).

    Uses the shared aiohttp session for connection pooling.
    Retries transient failures with exponential backoff.
    Skips non-HTML responses and oversized responses.
    Returns (None, 0) on failure.
    """
    for attempt in range(1 + retries):
        start = time.monotonic()
        try:
            async with session.get(
                url,
                timeout=aiohttp.ClientTimeout(total=timeout),
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

                text = body.decode(
                    response.get_encoding() or "utf-8", errors="replace"
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


async def crawl_async(
    url: str,
    *,
    depth: int = 0,
    tags: set[str] | None = None,
    deduplicate: bool = True,
    timeout: int = DEFAULT_TIMEOUT,
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

    Returns:
        List of discovered URLs (str) or UrlResult objects.
    """
    base_parsed = urlparse(url)
    base_domain = base_parsed.netloc
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
    )
    headers = {"User-Agent": user_agent}

    if proxy:
        logger.debug("Using proxy %s for all outbound fetches", redact_credentials(proxy))

    async with aiohttp.ClientSession(
        connector=connector,
        headers=headers,
        auth=basic_auth,
    ) as session:
        if robots:
            await robots.load(session, url, timeout=timeout, proxy=proxy)

        # Optionally fetch sitemap.xml
        if use_sitemap:
            sitemap_url = urljoin(
                f"{base_parsed.scheme}://{base_parsed.netloc}", "/sitemap.xml"
            )
            sitemap_urls = await fetch_sitemap(
                session, sitemap_url, timeout=timeout, proxy=proxy
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

        if strategy == "bfs":
            # Breadth-first crawling
            queue: deque[tuple[str, int]] = deque()
            queue.append((url, 0))

            while queue and len(all_results) < max_urls:
                current_url, current_depth = queue.popleft()

                normalized = normalize_url(current_url)
                if normalized in visited:
                    continue
                visited.add(normalized)

                if cache:
                    cache.mark_visited(normalized)

                if robots and not robots.is_allowed(current_url):
                    logger.info("Blocked by robots.txt: %s", current_url)
                    continue

                if rate_limit > 0:
                    await asyncio.sleep(rate_limit)

                async with semaphore:
                    logger.info("Crawling [depth=%d]: %s", current_depth, current_url)
                    html, resp_time = await fetch_page(
                        session, current_url,
                        timeout=timeout,
                        max_response_size=max_response_size,
                        retries=retries,
                        proxy=proxy,
                    )

                if html is None:
                    continue

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

                if current_depth < depth:
                    for result in found:
                        if _should_follow(result.url):
                            queue.append((result.url, current_depth + 1))

        else:
            # Depth-first crawling (default)
            async def _crawl_page(current_url: str, current_depth: int) -> None:
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

                if rate_limit > 0:
                    await asyncio.sleep(rate_limit)

                async with semaphore:
                    logger.info("Crawling [depth=%d]: %s", current_depth, current_url)
                    html, resp_time = await fetch_page(
                        session, current_url,
                        timeout=timeout,
                        max_response_size=max_response_size,
                        retries=retries,
                        proxy=proxy,
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
                    tasks = []
                    for result in found:
                        if _should_follow(result.url):
                            tasks.append(_crawl_page(result.url, current_depth + 1))
                    if tasks:
                        await asyncio.gather(*tasks)

            await _crawl_page(url, 0)

    # Save final visited state
    if cache:
        cache.save_visited()

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
) -> list[str] | list[UrlResult]:
    """Synchronous wrapper around crawl_async for simple usage."""
    return asyncio.run(
        crawl_async(
            url,
            depth=depth,
            tags=tags,
            deduplicate=deduplicate,
            timeout=timeout,
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
        )
    )
