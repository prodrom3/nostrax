"""Check HTTP status codes for discovered URLs.

Copyright (c) 2024 prodrom3 / radamic
Licensed under the MIT License.
"""

import asyncio
import logging

import aiohttp

logger = logging.getLogger(__name__)


async def check_url_status(
    session: aiohttp.ClientSession,
    url: str,
    *,
    timeout: int = 10,
    proxy: str | None = None,
) -> int | None:
    """Send a HEAD request and return the HTTP status code.

    Returns None if the request fails entirely.
    """
    try:
        async with session.head(
            url,
            timeout=aiohttp.ClientTimeout(total=timeout),
            allow_redirects=False,
            proxy=proxy,
        ) as response:
            return response.status
    except (aiohttp.ClientError, TimeoutError):
        return None


async def check_statuses(
    urls: list[str],
    *,
    timeout: int = 10,
    max_concurrent: int = 20,
    user_agent: str = "nostrax/1.0",
    auth: aiohttp.BasicAuth | None = None,
    proxy: str | None = None,
) -> dict[str, int | None]:
    """Check HTTP status for a list of URLs concurrently.

    Returns a dict mapping URL to status code (or None on failure).
    """
    semaphore = asyncio.Semaphore(max_concurrent)
    results: dict[str, int | None] = {}

    connector = aiohttp.TCPConnector(limit=max_concurrent)
    headers = {"User-Agent": user_agent}

    async with aiohttp.ClientSession(
        connector=connector,
        headers=headers,
        auth=auth,
    ) as session:
        async def _check(url: str) -> None:
            async with semaphore:
                results[url] = await check_url_status(
                    session, url, timeout=timeout, proxy=proxy
                )

        await asyncio.gather(*[_check(u) for u in urls])

    return results
