"""A JavaScript-rendering Fetcher for nostrax, backed by Playwright.

nostrax's default fetcher uses aiohttp, which sees only the server-rendered
HTML. Single-page apps that build their DOM in the browser therefore expose
few or no links to it. This adapter implements the ``nostrax.protocols.Fetcher``
protocol using a real Chromium/Firefox/WebKit browser, so the crawler extracts
links from the fully rendered page.

Install the extra and a browser binary first::

    pip install "nostrax[playwright]"
    playwright install chromium

Usage::

    import asyncio
    from nostrax import crawl_async
    from examples.playwright_fetcher import PlaywrightFetcher

    async def main():
        async with PlaywrightFetcher(headless=True) as fetcher:
            urls = await crawl_async(
                "https://example.com",
                depth=1,
                fetcher=fetcher.fetch,   # pass the bound method
            )
        for u in urls:
            print(u)

    asyncio.run(main())

The ``session`` argument required by the Fetcher protocol is ignored here:
Playwright drives its own browser rather than the crawl's aiohttp session.

Copyright (c) 2024 prodrom3 / radamic
Licensed under the MIT License.
"""

import logging
import time

import aiohttp

logger = logging.getLogger(__name__)

DEFAULT_MAX_RESPONSE_SIZE = 10 * 1024 * 1024


class PlaywrightFetcher:
    """Render pages with a headless browser and return their HTML.

    Manages a single browser process for the life of the object; call
    :meth:`start`/:meth:`close` or use it as an async context manager. The
    :meth:`fetch` method matches the ``Fetcher`` protocol and can be passed
    straight to :func:`nostrax.crawl_async` as ``fetcher=``.
    """

    def __init__(
        self,
        *,
        browser: str = "chromium",
        headless: bool = True,
        wait_until: str = "networkidle",
    ) -> None:
        self._browser_name = browser
        self._headless = headless
        self._wait_until = wait_until
        self._playwright = None
        self._browser = None

    async def start(self) -> "PlaywrightFetcher":
        # Imported lazily so nostrax has no hard dependency on Playwright.
        from playwright.async_api import async_playwright

        self._playwright = await async_playwright().start()
        launcher = getattr(self._playwright, self._browser_name)
        self._browser = await launcher.launch(headless=self._headless)
        return self

    async def close(self) -> None:
        if self._browser is not None:
            await self._browser.close()
            self._browser = None
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None

    async def __aenter__(self) -> "PlaywrightFetcher":
        return await self.start()

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    async def fetch(
        self,
        session: aiohttp.ClientSession,
        url: str,
        *,
        timeout: int = 10,
        max_response_size: int = DEFAULT_MAX_RESPONSE_SIZE,
        retries: int = 2,
        proxy: str | None = None,
        connect_timeout: float | None = None,
        read_timeout: float | None = None,
    ) -> tuple[str | None, float]:
        """Render ``url`` and return ``(html_or_None, elapsed_ms)``.

        Swallows navigation errors and returns ``(None, elapsed)`` on
        failure, as the Fetcher protocol requires. ``session`` is unused.
        """
        if self._browser is None:
            raise RuntimeError("PlaywrightFetcher.start() was not called")

        context_kwargs: dict = {}
        if proxy:
            context_kwargs["proxy"] = {"server": proxy}

        for attempt in range(1 + retries):
            start = time.monotonic()
            context = await self._browser.new_context(**context_kwargs)
            page = await context.new_page()
            try:
                await page.goto(
                    url, timeout=timeout * 1000, wait_until=self._wait_until
                )
                html = await page.content()
                elapsed = (time.monotonic() - start) * 1000
                if len(html.encode("utf-8", "ignore")) > max_response_size:
                    logger.warning("Skipping %s: rendered page too large", url)
                    return None, elapsed
                return html, elapsed
            except Exception as e:  # noqa: BLE001 - protocol says swallow + retry
                elapsed = (time.monotonic() - start) * 1000
                if attempt < retries:
                    logger.debug("Retry %d for %s: %s", attempt + 1, url, e)
                    continue
                logger.error("Playwright failed to render %s: %s", url, e)
                return None, elapsed
            finally:
                await page.close()
                await context.close()

        return None, 0.0


async def _demo(target: str) -> None:  # pragma: no cover - manual demo
    from nostrax import crawl_async

    async with PlaywrightFetcher(headless=True) as fetcher:
        urls = await crawl_async(target, depth=1, fetcher=fetcher.fetch)
    for url in urls:
        print(url)


if __name__ == "__main__":  # pragma: no cover - manual demo
    import asyncio
    import sys

    asyncio.run(_demo(sys.argv[1] if len(sys.argv) > 1 else "https://example.com"))
