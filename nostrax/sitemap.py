"""Parse sitemap.xml to extract URLs.

Copyright (c) 2024 prodrom3 / radamic
Licensed under the MIT License.
"""

import logging
from xml.etree import ElementTree

import aiohttp

logger = logging.getLogger(__name__)

SITEMAP_NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
MAX_SITEMAP_DEPTH = 5
# sitemaps.org caps uncompressed sitemaps at 50 MiB; match that.
MAX_SITEMAP_SIZE = 50 * 1024 * 1024


def _safe_parse_xml(text: str) -> ElementTree.Element | None:
    """Parse XML safely, disabling external entity processing."""
    # Reject DOCTYPE declarations to prevent XXE attacks
    if "<!DOCTYPE" in text or "<!ENTITY" in text:
        logger.warning("Rejecting XML with DOCTYPE/ENTITY declarations (XXE prevention)")
        return None
    try:
        return ElementTree.fromstring(text)
    except ElementTree.ParseError as e:
        logger.error("Failed to parse sitemap XML: %s", e)
        return None


async def fetch_sitemap(
    session: aiohttp.ClientSession,
    url: str,
    *,
    timeout: int = 10,
    proxy: str | None = None,
    _depth: int = 0,
    _visited: set[str] | None = None,
) -> list[str]:
    """Fetch and parse a sitemap.xml, returning all <loc> URLs.

    Handles both sitemap index files and regular sitemaps.
    Protected against infinite recursion and XXE attacks.
    """
    if _visited is None:
        _visited = set()

    # Prevent infinite recursion and circular references
    if _depth >= MAX_SITEMAP_DEPTH:
        logger.warning("Max sitemap recursion depth reached (%d), stopping", MAX_SITEMAP_DEPTH)
        return []
    if url in _visited:
        logger.debug("Already visited sitemap: %s", url)
        return []
    _visited.add(url)

    urls: list[str] = []

    try:
        async with session.get(
            url,
            timeout=aiohttp.ClientTimeout(total=timeout),
            allow_redirects=False,
            proxy=proxy,
        ) as response:
            if response.status != 200:
                logger.warning("Sitemap not found at %s (status %d)", url, response.status)
                return []
            body = await response.content.read(MAX_SITEMAP_SIZE + 1)
            if len(body) > MAX_SITEMAP_SIZE:
                logger.warning(
                    "Sitemap %s exceeds %d bytes, skipping",
                    url, MAX_SITEMAP_SIZE,
                )
                return []
            text = body.decode("utf-8", errors="replace")
    except (aiohttp.ClientError, TimeoutError) as e:
        logger.error("Failed to fetch sitemap %s: %s", url, e)
        return []

    root = _safe_parse_xml(text)
    if root is None:
        return []

    # Check if this is a sitemap index (contains <sitemap> elements)
    sitemaps = root.findall(f"{SITEMAP_NS}sitemap")
    if sitemaps:
        for sitemap in sitemaps:
            loc = sitemap.find(f"{SITEMAP_NS}loc")
            if loc is not None and loc.text:
                child_urls = await fetch_sitemap(
                    session, loc.text.strip(),
                    timeout=timeout,
                    proxy=proxy,
                    _depth=_depth + 1,
                    _visited=_visited,
                )
                urls.extend(child_urls)
        return urls

    # Regular sitemap - extract <url><loc> entries
    for url_element in root.findall(f"{SITEMAP_NS}url"):
        loc = url_element.find(f"{SITEMAP_NS}loc")
        if loc is not None and loc.text:
            urls.append(loc.text.strip())

    logger.info("Found %d URLs in sitemap %s", len(urls), url)
    return urls
