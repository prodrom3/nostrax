"""Tests for nostrax.crawler.PerHostRateLimiter."""

import asyncio
import time

import pytest

from nostrax.crawler import PerHostRateLimiter


@pytest.mark.asyncio
async def test_noop_when_interval_non_positive():
    """A zero or negative interval is a pass-through - no sleep, no locks."""
    limiter = PerHostRateLimiter(0)
    t0 = time.monotonic()
    await limiter.wait("example.com")
    await limiter.wait("example.com")
    assert time.monotonic() - t0 < 0.05


@pytest.mark.asyncio
async def test_serialises_per_host_within_interval():
    """Two waits for the same host within the interval should be spaced."""
    limiter = PerHostRateLimiter(0.1)

    t0 = time.monotonic()
    await limiter.wait("example.com")
    await limiter.wait("example.com")
    elapsed = time.monotonic() - t0

    # Second call must wait roughly min_interval after the first.
    assert elapsed >= 0.1
    assert elapsed < 0.3


@pytest.mark.asyncio
async def test_different_hosts_do_not_serialise():
    """A wait on host B must not be delayed by a prior wait on host A."""
    limiter = PerHostRateLimiter(0.5)

    await limiter.wait("host-a.example")
    t0 = time.monotonic()
    await limiter.wait("host-b.example")
    # Should be immediate because host-b has no previous timestamp.
    assert time.monotonic() - t0 < 0.05


@pytest.mark.asyncio
async def test_concurrent_waits_on_same_host_queue():
    """Three concurrent waits on the same host should complete in sequence,
    separated by at least the interval."""
    limiter = PerHostRateLimiter(0.1)

    async def call():
        await limiter.wait("example.com")
        return time.monotonic()

    results = await asyncio.gather(call(), call(), call())
    # Sorted to avoid relying on gather order.
    results.sort()
    assert results[1] - results[0] >= 0.1
    assert results[2] - results[1] >= 0.1
