# nostrax examples

Runnable examples of nostrax's extension points. These are not imported by the
package and are not installed with it; copy what you need into your own project.

## `playwright_fetcher.py` - crawl JavaScript-rendered sites

nostrax's default fetcher uses aiohttp and sees only server-rendered HTML.
Single-page apps that build their DOM in the browser expose few links to it.
`PlaywrightFetcher` implements the `nostrax.protocols.Fetcher` protocol with a
real headless browser so the crawler extracts links from the rendered page.

```bash
pip install "nostrax[playwright]"
playwright install chromium
python examples/playwright_fetcher.py https://example.com
```

```python
import asyncio
from nostrax import crawl_async
from examples.playwright_fetcher import PlaywrightFetcher

async def main():
    async with PlaywrightFetcher(headless=True) as fetcher:
        urls = await crawl_async("https://example.com", depth=1, fetcher=fetcher.fetch)
    print("\n".join(urls))

asyncio.run(main())
```

Any callable matching the `Fetcher` signature works the same way - a caching
fetcher, a rate-limited fetcher, or one that reads from a local mirror.
