"""Observability hook for the crawler.

Exposes a lightweight Protocol that callers can implement to route
crawl events into Prometheus, OpenTelemetry, Datadog, a SIEM pipeline,
or anything else. The crawler core calls the sink methods
synchronously on the event-loop thread, so implementations must be
cheap: update counters, enqueue to a worker, emit a log line, but do
not block.

Every method has a default no-op implementation on ``NullMetricsSink``
so a consumer only overrides the events they care about.

Copyright (c) 2024 prodrom3 / radamic
Licensed under the MIT License.
"""

from typing import Protocol, runtime_checkable


@runtime_checkable
class MetricsSink(Protocol):
    """Receives events emitted by :func:`nostrax.crawler.crawl_async`."""

    def on_page_fetched(
        self, url: str, depth: int, elapsed_ms: float, urls_found: int
    ) -> None:
        """A page was fetched, parsed, and had its links extracted."""

    def on_fetch_failed(self, url: str, depth: int) -> None:
        """fetch_page returned no HTML (timeout, non-HTML, oversized, error)."""

    def on_robots_blocked(self, url: str) -> None:
        """robots.txt refused the URL and we skipped it without fetching."""


class NullMetricsSink:
    """Default no-op sink. Safe to use as a type-erased placeholder."""

    def on_page_fetched(
        self, url: str, depth: int, elapsed_ms: float, urls_found: int
    ) -> None:
        return None

    def on_fetch_failed(self, url: str, depth: int) -> None:
        return None

    def on_robots_blocked(self, url: str) -> None:
        return None
