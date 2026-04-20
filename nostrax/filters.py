"""Filter extracted URLs by various criteria.

Copyright (c) 2024 prodrom3 / radamic
Licensed under the MIT License.
"""

import logging
import re
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


def _parse_urls(urls: list[str]) -> list[tuple[str, str, str]]:
    """Parse URLs once and return (url, scheme, netloc) tuples."""
    return [(u, p.scheme, p.netloc) for u, p in ((u, urlparse(u)) for u in urls)]


def filter_by_domain(
    urls: list[str], base_url: str, *, mode: str = "all"
) -> list[str]:
    """Filter URLs by domain relationship to base URL.

    Args:
        urls: List of URLs to filter.
        base_url: The original target URL.
        mode: "internal" (same domain), "external" (different domain), or "all".
    """
    if mode == "all":
        return urls

    base_domain = urlparse(base_url).netloc
    parsed = _parse_urls(urls)

    if mode == "internal":
        return [u for u, _, netloc in parsed if netloc == base_domain]
    elif mode == "external":
        return [u for u, _, netloc in parsed if netloc != base_domain]
    else:
        raise ValueError(f"Invalid domain filter mode: {mode!r}")


def filter_by_protocol(urls: list[str], protocols: set[str]) -> list[str]:
    """Keep only URLs matching the given protocols (e.g. {'https', 'http'})."""
    parsed = _parse_urls(urls)
    return [u for u, scheme, _ in parsed if scheme in protocols]


def filter_by_pattern(urls: list[str], pattern: str) -> list[str]:
    """Keep only URLs matching the given regex pattern.

    Validates the pattern before use. Returns the original list
    if the pattern is invalid.
    """
    try:
        compiled = re.compile(pattern)
    except re.error as e:
        logger.error("Invalid regex pattern %r: %s", pattern, e)
        return urls

    safe: list[str] = []
    for u in urls:
        try:
            if compiled.search(u):
                safe.append(u)
        except RecursionError:
            logger.warning("Regex caused excessive backtracking on URL, skipping: %s", u)
    return safe


def filter_by_exclude(urls: list[str], pattern: str) -> list[str]:
    """Remove URLs matching the given regex pattern.

    Inverse of filter_by_pattern. Returns the original list
    if the pattern is invalid.
    """
    try:
        compiled = re.compile(pattern)
    except re.error as e:
        logger.error("Invalid exclude pattern %r: %s", pattern, e)
        return urls

    safe: list[str] = []
    for u in urls:
        try:
            if not compiled.search(u):
                safe.append(u)
        except RecursionError:
            logger.warning("Regex caused excessive backtracking on URL, skipping: %s", u)
    return safe
