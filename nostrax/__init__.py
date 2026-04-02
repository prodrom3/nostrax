"""nostrax - Extract URLs and paths from web pages.

Copyright (c) 2024 prodrom3 / radamic
Licensed under the MIT License.
Last updated: 2026-04-02
"""

__version__ = "2.0.0"

from nostrax.extractor import extract_urls
from nostrax.crawler import crawl, crawl_async
from nostrax.models import UrlResult
from nostrax.normalize import normalize_url
from nostrax.exceptions import NostraxError

__all__ = [
    "extract_urls",
    "crawl",
    "crawl_async",
    "UrlResult",
    "normalize_url",
    "NostraxError",
]
