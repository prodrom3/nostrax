"""Extract URLs from HTML content.

Copyright (c) 2024 prodrom3 / radamic
Licensed under the MIT License.
"""

import logging
from urllib.parse import urljoin

from bs4 import BeautifulSoup, SoupStrainer

from nostrax.models import UrlResult

logger = logging.getLogger(__name__)

# Tag/attribute pairs to extract URLs from. "meta" uses a content-attribute
# parser rather than a single attribute read (see _urls_for_meta).
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
    "meta": "content",
}

# Tags whose srcset attribute also carries URLs (responsive images and
# <source> inside <picture>).
_SRCSET_TAGS = frozenset({"img", "source"})

# Default: only extract <a> tags
DEFAULT_TAGS: set[str] = {"a"}

# Prefixes to skip - not useful URLs
_SKIP_PREFIXES = ("javascript:", "mailto:", "tel:", "#", "data:")


def _parse_srcset(value: str) -> list[str]:
    """Extract URLs from an HTML5 srcset attribute.

    srcset is a comma-separated list of candidates, each ``URL [descriptor]``
    where the descriptor is ``<int>w`` or ``<float>x``. We pull the URL
    token from each candidate. URLs containing literal commas are rare
    and typically URL-encoded, so a plain comma split is good enough.
    """
    urls: list[str] = []
    for candidate in value.split(","):
        candidate = candidate.strip()
        if not candidate:
            continue
        parts = candidate.split(None, 1)
        if parts:
            urls.append(parts[0])
    return urls


def _parse_meta_refresh(content: str) -> str | None:
    """Extract the URL from a ``<meta http-equiv="refresh" content="...">``.

    Expected shape: ``<seconds>; url=<target>`` (case-insensitive ``url``),
    with or without whitespace around the separator and optional quoting
    around the target.
    """
    semi = content.find(";")
    if semi < 0:
        return None
    rest = content[semi + 1:].strip()
    if rest[:4].lower() != "url=":
        return None
    url = rest[4:].strip().strip('"').strip("'")
    return url or None


def _urls_for_element(element, tag_name: str) -> list[str]:
    """Return every URL-bearing attribute value on ``element``."""
    if tag_name == "meta":
        if (element.get("http-equiv") or "").lower() != "refresh":
            return []
        url = _parse_meta_refresh(element.get("content") or "")
        return [url] if url else []

    values: list[str] = []
    attr = TAG_ATTRS.get(tag_name)
    if attr:
        v = element.get(attr)
        if v:
            values.append(v)
    if tag_name in _SRCSET_TAGS:
        srcset = element.get("srcset")
        if srcset:
            values.extend(_parse_srcset(srcset))
    return values


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
        if tag_name not in TAG_ATTRS:
            logger.warning("Unsupported tag: %s", tag_name)
            continue

        for element in soup.find_all(tag_name):
            for value in _urls_for_element(element, tag_name):
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
