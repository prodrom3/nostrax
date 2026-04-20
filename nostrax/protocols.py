"""Extensibility protocols for the fetch and extract stages.

The default crawler uses :func:`nostrax.crawler.fetch_page` and
:func:`nostrax.extractor.extract_urls`. Callers that need something
else - a JavaScript-rendering Playwright fetcher, a caching fetcher,
a custom parser for JSON-LD or sitemap-like pages - can pass any
callable that matches these Protocol signatures to ``crawl_async``.

Copyright (c) 2024 prodrom3 / radamic
Licensed under the MIT License.
"""

from typing import Protocol

import aiohttp

from nostrax.models import UrlResult


class Fetcher(Protocol):
    """Return ``(html_or_None, elapsed_ms)`` for a single URL.

    Implementations must swallow transient network errors and return
    ``(None, elapsed)`` on failure; raising propagates out of the crawl.
    """

    async def __call__(
        self,
        session: aiohttp.ClientSession,
        url: str,
        *,
        timeout: int,
        max_response_size: int,
        retries: int,
        proxy: str | None,
        connect_timeout: float | None,
        read_timeout: float | None,
    ) -> tuple[str | None, float]:
        ...


class Extractor(Protocol):
    """Return the list of URLs discovered in ``html``.

    The default Extractor ignores ``deduplicate=False`` in the crawl
    hot path because the crawler dedupes at a higher level; a custom
    implementation should still honour the flag so library callers
    retain the documented behaviour.
    """

    def __call__(
        self,
        html: str,
        base_url: str,
        *,
        tags: set[str] | None,
        deduplicate: bool,
        include_metadata: bool,
        depth: int,
    ) -> list[str] | list[UrlResult]:
        ...
