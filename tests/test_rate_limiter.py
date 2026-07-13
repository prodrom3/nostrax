"""Tests for nostrax.crawler.PerHostRateLimiter."""

import asyncio
import time

import pytest

from nostrax.crawler import AdaptiveRateLimiter, PerHostRateLimiter, ProxyPool


def test_proxy_pool_round_robin():
    pool = ProxyPool(["http://a:1", "http://b:2", "http://c:3"])
    assert bool(pool) is True
    got = [pool.next() for _ in range(7)]
    assert got == [
        "http://a:1",
        "http://b:2",
        "http://c:3",
        "http://a:1",
        "http://b:2",
        "http://c:3",
        "http://a:1",
    ]


def test_proxy_pool_empty():
    pool = ProxyPool([])
    assert bool(pool) is False
    assert pool.next() is None


def test_adaptive_limiter_backs_off_on_failure():
    lim = AdaptiveRateLimiter(start_delay=1.0, min_delay=0.5, max_delay=10.0)
    lim.record("h", latency_s=0.2, success=False)
    lim.record("h", latency_s=0.2, success=False)
    # two failures from a start of 1.0 -> ~4.0 (doubled twice), under the cap
    assert lim._delays["h"] == pytest.approx(4.0)


def test_adaptive_limiter_respects_floor_and_cap():
    lim = AdaptiveRateLimiter(start_delay=1.0, min_delay=0.5, max_delay=3.0)
    # Fast responses pull the delay down, but never below min_delay.
    for _ in range(20):
        lim.record("h", latency_s=0.0, success=True)
    assert lim._delays["h"] >= 0.5
    # A failure cannot exceed max_delay.
    for _ in range(20):
        lim.record("h", latency_s=0.0, success=False)
    assert lim._delays["h"] <= 3.0


def test_adaptive_limiter_matches_latency():
    lim = AdaptiveRateLimiter(start_delay=1.0, min_delay=0.0, max_delay=10.0)
    # Sustained 2s latency with target_concurrency 1.0 converges toward 2s.
    for _ in range(30):
        lim.record("h", latency_s=2.0, success=True)
    assert lim._delays["h"] == pytest.approx(2.0, abs=0.1)


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
