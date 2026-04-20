"""Extract URLs from HTML content.

Copyright (c) 2024 prodrom3 / radamic
Licensed under the MIT License.
Last updated: 2026-04-02
"""

import logging
from urllib.parse import urljoin

from bs4 import BeautifulSoup, SoupStrainer

from nostrax.models import UrlResult

logger = logging.getLogger(__name__)

# Tag/attribute pairs to extract URLs from
TAG_ATTRS: dict[str, str] = {
    "a": "href",
    "img": "src",
    "script": "src",
    "link": "href",
    "form": "action",
    "iframe": "src",
    "video": "src",
    "audio": "src",
    "source": "src",
}

# Default: only extract <a> tags
DEFAULT_TAGS: set[str] = {"a"}

# Prefixes to skip - not useful URLs
_SKIP_PREFIXES = ("javascript:", "mailto:", "tel:", "#", "data:")


def extract_urls(
    html: str,
    base_url: str,
    *,
    tags: set[str] | None = None,
    deduplicate: bool = True,
    include_metadata: bool = False,
    depth: int = 0,
) -> list[str] | list[UrlResult]:
    """Extract URLs from HTML content.

    Args:
        html: Raw HTML string.
        base_url: Base URL for resolving relative paths. Overridden by a
            ``<base href="...">`` element if present in the document.
        tags: Which HTML tags to extract from. Defaults to {"a"}.
        deduplicate: Remove duplicate URLs.
        include_metadata: If True, return UrlResult objects instead of strings.
        depth: Current crawl depth (used for metadata).

    Returns:
        List of absolute URLs (str) or UrlResult objects.
    """
    if tags is None:
        tags = DEFAULT_TAGS

    # Always pull <base> alongside the requested tags so we can honour it
    # for relative-link resolution even when the caller only asked for <a>.
    strainer = SoupStrainer(list(tags | {"base"}))
    soup = BeautifulSoup(html, "lxml", parse_only=strainer)

    resolved_base = base_url
    base_el = soup.find("base")
    if base_el is not None:
        href = (base_el.get("href") or "").strip()
        if href:
            resolved_base = urljoin(base_url, href)

    results: list[UrlResult] = []
    seen: set[str] = set()

    for tag_name in tags:
        attr = TAG_ATTRS.get(tag_name)
        if attr is None:
            logger.warning("Unsupported tag: %s", tag_name)
            continue

        for element in soup.find_all(tag_name):
            value = element.get(attr)
            if value is None:
                continue
            value = value.strip()
            if not value or value.startswith(_SKIP_PREFIXES):
                continue
            absolute_url = urljoin(resolved_base, value)

            if deduplicate:
                if absolute_url in seen:
                    continue
                seen.add(absolute_url)

            results.append(UrlResult(
                url=absolute_url,
                source=base_url,
                tag=tag_name,
                depth=depth,
            ))

    if include_metadata:
        return results
    return [r.url for r in results]
