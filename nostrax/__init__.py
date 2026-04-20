"""nostrax - Extract URLs and paths from web pages.

Copyright (c) 2024 prodrom3 / radamic
Licensed under the MIT License.
"""

from importlib import metadata as _metadata

try:
    __version__ = _metadata.version("nostrax")
except _metadata.PackageNotFoundError:
    # Running from a checkout without an install (e.g. in-tree tests).
    __version__ = "0.0.0+unknown"

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
