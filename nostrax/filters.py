"""Filter extracted URLs by various criteria.

Copyright (c) 2024 prodrom3 / radamic
Licensed under the MIT License.
"""

import logging
from urllib.parse import urlparse

import regex

logger = logging.getLogger(__name__)

# Per-URL regex match budget. The `regex` package's matcher is far more
# resilient to catastrophic backtracking than stdlib `re`, but this cap
# guarantees a bounded worst case even for pathological inputs.
_REGEX_TIMEOUT_SECONDS = 0.5


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

    Each per-URL match is wrapped in a ``_REGEX_TIMEOUT_SECONDS`` budget
    so that a pathological pattern cannot hang the process. Matches that
    exceed the budget are skipped with a warning; a syntactically invalid
    pattern returns the input list unchanged.
    """
    try:
        compiled = regex.compile(pattern)
    except regex.error as e:
        logger.error("Invalid regex pattern %r: %s", pattern, e)
        return urls

    safe: list[str] = []
    for u in urls:
        try:
            if compiled.search(u, timeout=_REGEX_TIMEOUT_SECONDS):
                safe.append(u)
        except TimeoutError:
            logger.warning(
                "Regex timed out on URL, skipping: %s (pattern=%r)", u, pattern
            )
    return safe


def filter_by_exclude(urls: list[str], pattern: str) -> list[str]:
    """Remove URLs matching the given regex pattern.

    Inverse of filter_by_pattern with the same timeout-bounded behaviour.
    """
    try:
        compiled = regex.compile(pattern)
    except regex.error as e:
        logger.error("Invalid exclude pattern %r: %s", pattern, e)
        return urls

    safe: list[str] = []
    for u in urls:
        try:
            if not compiled.search(u, timeout=_REGEX_TIMEOUT_SECONDS):
                safe.append(u)
        except TimeoutError:
            logger.warning(
                "Regex timed out on URL, skipping: %s (pattern=%r)", u, pattern
            )
    return safe
