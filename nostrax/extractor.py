"""Extract URLs from HTML content.

Copyright (c) 2024 prodrom3 / radamic
Licensed under the MIT License.
"""

import logging
from urllib.parse import urljoin

from bs4 import BeautifulSoup, SoupStrainer, Tag

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

# Prefixes to skip - not useful URLs. Compared case-insensitively so
# "JavaScript:" / "MAILTO:" are skipped too (schemes are case-insensitive).
_SKIP_PREFIXES = ("javascript:", "vbscript:", "mailto:", "tel:", "#", "data:")


def _should_skip(value: str) -> bool:
    """True if ``value`` is a non-navigable pseudo-URL we should drop."""
    return value.lower().startswith(_SKIP_PREFIXES)


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
    # Accept "url=x", "URL = x", "url =x" - browsers tolerate whitespace
    # around the '=' and any case for the "url" key.
    if rest[:3].lower() != "url":
        return None
    after = rest[3:].lstrip()
    if not after.startswith("="):
        return None
    url = after[1:].strip().strip('"').strip("'")
    return url or None


def _urls_for_element(element, tag_name: str) -> list[str]:
    """Return every URL-bearing attribute value on ``element``.

    bs4 can return a list for multi-valued attributes, so each attribute
    read is guarded with ``isinstance(..., str)``; the URL attributes we
    care about (href/src/action/content) are always single-valued.
    """
    if tag_name == "meta":
        http_equiv = element.get("http-equiv")
        if not isinstance(http_equiv, str) or http_equiv.lower() != "refresh":
            return []
        content = element.get("content")
        if not isinstance(content, str):
            return []
        url = _parse_meta_refresh(content)
        return [url] if url else []

    values: list[str] = []
    attr = TAG_ATTRS.get(tag_name)
    if attr:
        v = element.get(attr)
        if isinstance(v, str) and v:
            values.append(v)
    if tag_name in _SRCSET_TAGS:
        srcset = element.get("srcset")
        if isinstance(srcset, str) and srcset:
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
    if isinstance(base_el, Tag):
        href = base_el.get("href")
        if isinstance(href, str) and href.strip():
            resolved_base = urljoin(base_url, href.strip())

    results: list[UrlResult] = []
    seen: set[str] = set()

    valid_tags = [t for t in tags if t in TAG_ATTRS]
    for t in tags:
        if t not in TAG_ATTRS:
            logger.warning("Unsupported tag: %s", t)

    # Single document-order pass over all requested tags instead of one
    # full tree traversal per tag. lxml's find_all with a tag list walks
    # the tree once and yields elements in the order they appear, which
    # also makes the output reflect document order across tag types.
    for element in soup.find_all(valid_tags):
        tag_name = element.name
        for value in _urls_for_element(element, tag_name):
            value = value.strip()
            if not value or _should_skip(value):
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
