"""Async recursive web crawler built on top of the extractor.

Copyright (c) 2024 prodrom3 / radamic
Licensed under the MIT License.
"""

import asyncio
import inspect
import logging
import random
import time
from collections.abc import Callable
from functools import partial
from typing import Any, cast
from urllib.parse import urlparse, urljoin

import aiohttp

from nostrax.cache import CrawlCache
from nostrax.exceptions import FetchError, NostraxError
from nostrax.extractor import extract_urls
from nostrax.metrics import MetricsSink, NullMetricsSink
from nostrax.models import UrlResult
from nostrax.normalize import normalize_url
from nostrax.protocols import Extractor, Fetcher
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

# HTTP statuses worth retrying: request timeout and rate limiting are
# transient, so is anything 5xx. A plain 4xx (404, 403, 410 ...) is
# deterministic - retrying it just burns backoff sleeps on a result that
# will not change - so those are returned immediately without retry.
_RETRYABLE_STATUSES = frozenset({408, 429})


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
                if content_type and not any(ct in content_type for ct in _HTML_CONTENT_TYPES):
                    logger.debug("Skipping non-HTML %s: %s", url, content_type)
                    return None, elapsed

                # Explicit status handling replaces raise_for_status() so we
                # can retry only transient failures. A ClientResponseError from
                # raise_for_status() would be caught below and retried for every
                # 4xx, which is wasted work on deterministic client errors.
                status = response.status
                if status >= 400:
                    retryable = status in _RETRYABLE_STATUSES or 500 <= status < 600
                    if retryable and attempt < retries:
                        delay = random.uniform(0, 2**attempt)
                        logger.debug(
                            "Retry %d/%d for %s after HTTP %d (waiting %.2fs)",
                            attempt + 1,
                            retries,
                            url,
                            status,
                            delay,
                        )
                        await asyncio.sleep(delay)
                        continue
                    logger.warning(
                        "HTTP %d for %s%s",
                        status,
                        url,
                        "" if retryable else " (client error, not retried)",
                    )
                    return None, elapsed

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
                        url,
                        max_response_size,
                    )
                    return None, elapsed

                # response.charset returns the Content-Type charset or None.
                # We avoid aiohttp's get_encoding() because it raises
                # RuntimeError on a body read via .content.read() (no
                # charset in header and no internal buffer to sniff).
                text = body.decode(response.charset or "utf-8", errors="replace")
                return text, elapsed

        except (aiohttp.ClientError, TimeoutError) as e:
            elapsed = (time.monotonic() - start) * 1000
            if attempt < retries:
                # Full-jitter backoff (AWS Architecture Blog). Removes the
                # lockstep retries that thunder a rate-limited target.
                delay = random.uniform(0, 2**attempt)
                logger.debug(
                    "Retry %d/%d for %s after %.0fms (waiting %.2fs): %s",
                    attempt + 1,
                    retries,
                    url,
                    elapsed,
                    delay,
                    e,
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
                session,
                r.url,
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
    metrics: MetricsSink | None = None,
    fetcher: Fetcher | None = None,
    extractor: Extractor | None = None,
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
    if metrics is None:
        metrics = NullMetricsSink()
    if fetcher is None:
        fetcher = fetch_page
    if extractor is None:
        extractor = extract_urls
    # Extractors run inside loop.run_in_executor (HTML parsing is CPU
    # bound). An async function passed here would not be awaited by the
    # executor; it would return a coroutine that later explodes with a
    # cryptic "coroutine is not subscriptable" when indexed. Refuse up
    # front with a pointed message instead.
    if inspect.iscoroutinefunction(extractor):
        raise TypeError(
            "Extractor must be a synchronous callable; async extractors "
            "are not supported because the crawler runs them in a thread "
            "executor. Wrap async logic in a sync adapter if you need it."
        )
    base_parsed = urlparse(url)
    base_domain = base_parsed.netloc
    rate_limiter = PerHostRateLimiter(rate_limit)
    # completed: normalized URLs that were fully fetched (or permanently
    # skipped by robots.txt). This is the set persisted for resume.
    # pending: normalized URL -> (url, depth) for URLs that have been
    # enqueued but not yet completed. It doubles as the in-run dedup guard
    # and, at shutdown, as the frontier to persist so an interrupted crawl
    # can continue rather than only reloading prior results.
    completed: set[str] = set()
    pending: dict[str, tuple[str, int]] = {}
    all_results: list[UrlResult] = []
    semaphore = asyncio.Semaphore(max_concurrent)
    robots = RobotsChecker(user_agent) if respect_robots else None
    loop = asyncio.get_running_loop()
    pages_crawled = 0

    # Cache/resume support
    cache = None
    had_cached_results = False
    resume_frontier: list[tuple[str, int]] = []
    if cache_dir:
        cache = CrawlCache(cache_dir)
        cache.initialize()
        completed = cache.visited  # shared ref; cache.mark_visited updates it
        cached_results = cache.load_results()
        if cached_results:
            all_results.extend(cached_results)
            had_cached_results = True
            logger.info("Resumed with %d cached results", len(cached_results))
        resume_frontier = cache.load_frontier()
        if resume_frontier:
            logger.info("Resuming with %d pending frontier URLs", len(resume_frontier))

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
                    session,
                    url,
                    timeout=timeout,
                    proxy=proxy,
                    connect_timeout=connect_timeout,
                    read_timeout=read_timeout,
                )
                # Honour a robots.txt Crawl-delay by raising (never
                # lowering) the per-host minimum interval. An explicit
                # --rate-limit still wins if it is stricter.
                robots_delay = robots.crawl_delay()
                if robots_delay and robots_delay > rate_limit:
                    logger.info("Honouring robots.txt Crawl-delay of %.1fs", robots_delay)
                    rate_limiter = PerHostRateLimiter(robots_delay)

            # Optionally fetch sitemaps: those advertised in robots.txt plus
            # the conventional /sitemap.xml. Robots.txt is the standard place
            # to declare sitemaps that live elsewhere, so we consult it even
            # when --respect-robots is off (a lightweight extra fetch).
            if use_sitemap:
                sitemap_robots = robots
                if sitemap_robots is None:
                    sitemap_robots = RobotsChecker(user_agent)
                    await sitemap_robots.load(
                        session,
                        url,
                        timeout=timeout,
                        proxy=proxy,
                        connect_timeout=connect_timeout,
                        read_timeout=read_timeout,
                    )

                sitemap_targets: list[str] = list(sitemap_robots.sitemaps())
                default_sitemap = urljoin(
                    f"{base_parsed.scheme}://{base_parsed.netloc}", "/sitemap.xml"
                )
                if default_sitemap not in sitemap_targets:
                    sitemap_targets.append(default_sitemap)

                for sitemap_url in sitemap_targets:
                    sitemap_urls = await fetch_sitemap(
                        session,
                        sitemap_url,
                        timeout=timeout,
                        proxy=proxy,
                        connect_timeout=connect_timeout,
                        read_timeout=read_timeout,
                    )
                    for su in sitemap_urls:
                        all_results.append(
                            UrlResult(url=su, source=sitemap_url, tag="sitemap", depth=0)
                        )

            def _should_follow(link: str) -> bool:
                """Check if a link should be followed based on domain and scope.

                Deduplication against already-seen URLs is handled by
                ``_enqueue`` so this only encodes the domain/scope policy.
                """
                parsed = urlparse(link)
                if parsed.netloc != base_domain:
                    return False
                if scope and not parsed.path.startswith(scope):
                    return False
                return True

            # Unified engine: a frontier queue + max_concurrent workers.
            # DFS uses LifoQueue (last-in first-out = deepen first); BFS
            # uses FIFO Queue. Workers pull, fetch, enqueue children, and
            # mark task_done() so frontier.join() can detect completion.
            # max_concurrent workers replace the old per-request
            # Semaphore: having exactly N workers gives the same bound
            # without the extra primitive.
            #
            # The frontier is bounded at ``max_urls * 2``. _process_one
            # refuses to enqueue children once all_results hits
            # ``max_urls``, so this cap is a backstop against pathological
            # fan-out (e.g., a single page linking to 10^6 URLs would
            # otherwise balloon memory before we noticed). Workers block
            # on ``put()`` when the queue is full, which acts as natural
            # backpressure.
            frontier_max = max(max_urls * 2, max_concurrent * 2)
            frontier: asyncio.Queue[tuple[str, int]] = (
                asyncio.LifoQueue(maxsize=frontier_max)
                if strategy == "dfs"
                else asyncio.Queue(maxsize=frontier_max)
            )

            async def _enqueue(link: str, link_depth: int) -> None:
                """Add a URL to the frontier unless already seen or completed.

                Recording it in ``pending`` before the (possibly blocking)
                ``put`` both dedups concurrent discovery of the same URL and
                keeps ``pending`` an accurate snapshot of un-crawled work for
                frontier persistence.
                """
                norm = normalize_url(link)
                if norm in completed or norm in pending:
                    return
                pending[norm] = (link, link_depth)
                await frontier.put((link, link_depth))

            def _mark_done(normalized: str) -> None:
                completed.add(normalized)
                if cache:
                    cache.mark_visited(normalized)
                pending.pop(normalized, None)

            async def _process_one(current_url: str, current_depth: int) -> None:
                nonlocal pages_crawled

                normalized = normalize_url(current_url)
                if normalized in completed:
                    pending.pop(normalized, None)
                    return

                if len(all_results) >= max_urls:
                    return

                if robots and not robots.is_allowed(current_url):
                    logger.info("Blocked by robots.txt: %s", current_url)
                    try:
                        metrics.on_robots_blocked(current_url)
                    except Exception as e:
                        logger.warning("metrics sink raised in on_robots_blocked: %s", e)
                    # Permanently skipped: record as done so a resume does
                    # not keep retrying a URL robots.txt will block again.
                    _mark_done(normalized)
                    return

                await rate_limiter.wait(urlparse(current_url).netloc)

                logger.info("Crawling [depth=%d]: %s", current_depth, current_url)
                html, resp_time = await fetcher(
                    session,
                    current_url,
                    timeout=timeout,
                    max_response_size=max_response_size,
                    retries=retries,
                    proxy=proxy,
                    connect_timeout=connect_timeout,
                    read_timeout=read_timeout,
                )

                if html is None:
                    try:
                        metrics.on_fetch_failed(current_url, current_depth)
                    except Exception as e:
                        logger.warning("metrics sink raised in on_fetch_failed: %s", e)
                    return

                # Called with include_metadata=True, so the extractor returns
                # list[UrlResult]; the isinstance check below enforces it for
                # custom extractors that ignore the flag.
                found = cast(
                    "list[UrlResult]",
                    await loop.run_in_executor(
                        None,
                        partial(
                            extractor,
                            html,
                            current_url,
                            tags=tags,
                            deduplicate=False,
                            include_metadata=True,
                            depth=current_depth,
                        ),
                    ),
                )

                # Guard against custom extractors that ignore
                # include_metadata=True and return list[str]. Without this
                # check the crawl would crash at r.response_time = ...
                # with a cryptic AttributeError far from the real cause.
                if found and not isinstance(found[0], UrlResult):
                    raise TypeError(
                        f"Extractor returned {type(found[0]).__name__} but "
                        f"the crawler requires UrlResult when called with "
                        f"include_metadata=True. Custom Extractor "
                        f"implementations must honour the flag."
                    )

                for r in found:
                    r.response_time = resp_time
                all_results.extend(found)

                # Mark done only after a successful fetch. A failed fetch
                # (html is None, handled above) stays in ``pending`` so a
                # resume retries it instead of silently dropping its subtree.
                _mark_done(normalized)
                if cache:
                    for r in found:
                        cache.save_result(r)

                pages_crawled += 1
                if progress_callback is not None:
                    progress_callback(pages_crawled, len(all_results))
                try:
                    metrics.on_page_fetched(current_url, current_depth, resp_time, len(found))
                except Exception as e:
                    logger.warning("metrics sink raised in on_page_fetched: %s", e)

                if len(all_results) >= max_urls:
                    logger.warning("Reached max URL limit (%d), stopping crawl.", max_urls)
                    return

                if current_depth < depth:
                    for result in found:
                        if _should_follow(result.url):
                            await _enqueue(result.url, current_depth + 1)

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
                        logger.error("Worker failed on %s: %s", current_url, e, exc_info=True)
                        if first_error[0] is None:
                            first_error[0] = e
                    finally:
                        frontier.task_done()

            # Start the workers before seeding so that a large resume
            # frontier (which may exceed the queue's maxsize) drains as we
            # enqueue instead of dead-locking on a full queue.
            workers = [asyncio.create_task(_worker()) for _ in range(max_concurrent)]
            try:
                for f_url, f_depth in resume_frontier:
                    await _enqueue(f_url, f_depth)
                await _enqueue(url, 0)
                await frontier.join()
            finally:
                for w in workers:
                    w.cancel()
                await asyncio.gather(*workers, return_exceptions=True)

            if first_error[0] is not None:
                raise first_error[0]

            if check_status and all_results:
                await _attach_statuses(
                    session,
                    all_results,
                    semaphore,
                    timeout=timeout,
                    proxy=proxy,
                    connect_timeout=connect_timeout,
                    read_timeout=read_timeout,
                )

    finally:
        if cache:
            try:
                cache.save_visited()
                cache.save_frontier(list(pending.values()))
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
    metrics: MetricsSink | None = None,
    fetcher: Fetcher | None = None,
    extractor: Extractor | None = None,
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
            metrics=metrics,
            fetcher=fetcher,
            extractor=extractor,
        )
    )


async def crawl_seeds_async(
    seeds: list[str],
    *,
    deduplicate: bool = True,
    include_metadata: bool = False,
    **kwargs: Any,
) -> list[str] | list[UrlResult]:
    """Crawl several seed URLs and return the merged, de-duplicated results.

    Each seed is crawled independently with :func:`crawl_async` - its own
    base domain, scope, and robots.txt - so seeds may span different sites.
    A seed that fails to fetch is logged and skipped rather than aborting
    the whole batch; the call raises :class:`FetchError` only when *every*
    seed fails. Results are de-duplicated across seeds by normalized URL.

    ``cache_dir`` is not supported here: resume is a single-target concept,
    and a shared visited/frontier set across seeds would double-count
    reloaded results. Pass any other ``crawl_async`` keyword through
    ``kwargs``.
    """
    if not seeds:
        raise ValueError("no seed URLs provided")
    if kwargs.get("cache_dir"):
        raise ValueError(
            "cache_dir is not supported with multiple seeds; crawl a single target to use resume"
        )

    merged: list[UrlResult] = []
    failures = 0
    for seed in seeds:
        try:
            results = await crawl_async(seed, deduplicate=False, include_metadata=True, **kwargs)
        except NostraxError as e:
            logger.warning("Skipping seed %s: %s", seed, e)
            failures += 1
            continue
        # include_metadata=True above guarantees UrlResult items.
        merged.extend(cast("list[UrlResult]", results))

    if failures == len(seeds):
        raise FetchError(
            seeds[0],
            "no seed URLs could be crawled; check connectivity and logs",
        )

    if deduplicate:
        seen: set[str] = set()
        unique: list[UrlResult] = []
        for r in merged:
            norm = normalize_url(r.url)
            if norm not in seen:
                seen.add(norm)
                unique.append(r)
        merged = unique

    if include_metadata:
        return merged
    return [r.url for r in merged]


def crawl_seeds(
    seeds: list[str],
    *,
    deduplicate: bool = True,
    include_metadata: bool = False,
    **kwargs: Any,
) -> list[str] | list[UrlResult]:
    """Synchronous wrapper around :func:`crawl_seeds_async`."""
    return asyncio.run(
        crawl_seeds_async(
            seeds,
            deduplicate=deduplicate,
            include_metadata=include_metadata,
            **kwargs,
        )
    )
