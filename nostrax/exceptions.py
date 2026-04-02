"""Custom exception hierarchy for nostrax.

Copyright (c) 2024 prodrom3 / radamic
Licensed under the MIT License.
Last updated: 2026-04-02
"""


class NostraxError(Exception):
    """Base exception for all nostrax errors."""


class FetchError(NostraxError):
    """Failed to fetch a URL."""

    def __init__(self, url: str, reason: str) -> None:
        self.url = url
        self.reason = reason
        super().__init__(f"Failed to fetch {url}: {reason}")


class ParseError(NostraxError):
    """Failed to parse HTML content."""

    def __init__(self, url: str, reason: str) -> None:
        self.url = url
        self.reason = reason
        super().__init__(f"Failed to parse {url}: {reason}")


class RobotsBlockedError(NostraxError):
    """URL is blocked by robots.txt."""

    def __init__(self, url: str) -> None:
        self.url = url
        super().__init__(f"Blocked by robots.txt: {url}")


class ResponseTooLargeError(FetchError):
    """Response body exceeds size limit."""

    def __init__(self, url: str, size: int, limit: int) -> None:
        self.size = size
        self.limit = limit
        super().__init__(url, f"response too large ({size} bytes, limit {limit})")


class NonHtmlResponseError(FetchError):
    """Response Content-Type is not HTML."""

    def __init__(self, url: str, content_type: str) -> None:
        self.content_type = content_type
        super().__init__(url, f"non-HTML content type: {content_type}")


class ConfigError(NostraxError):
    """Error loading or parsing config file."""
