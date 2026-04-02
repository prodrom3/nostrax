"""Data models for nostrax results.

Copyright (c) 2024 prodrom3 / radamic
Licensed under the MIT License.
Last updated: 2026-04-02
"""

from dataclasses import dataclass


@dataclass
class UrlResult:
    """A discovered URL with optional metadata."""

    url: str
    source: str = ""
    tag: str = ""
    depth: int = 0
    status: int | None = None
    response_time: float | None = None  # milliseconds

    def to_dict(self) -> dict:
        d: dict = {"url": self.url}
        if self.source:
            d["source"] = self.source
        if self.tag:
            d["tag"] = self.tag
        if self.depth:
            d["depth"] = self.depth
        if self.status is not None:
            d["status"] = self.status
        if self.response_time is not None:
            d["response_time_ms"] = round(self.response_time, 1)
        return d
