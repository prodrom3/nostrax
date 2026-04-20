"""Tests for nostrax.resolver.SafeResolver."""

import socket
from unittest.mock import AsyncMock

import pytest

from nostrax.resolver import SafeResolver


def _info(host: str, family: int = socket.AF_INET) -> dict:
    return {"hostname": "example.com", "host": host, "port": 80, "family": family, "flags": 0}


@pytest.mark.asyncio
async def test_safe_resolver_passes_public_addresses(monkeypatch):
    r = SafeResolver()
    monkeypatch.setattr(
        r._inner, "resolve", AsyncMock(return_value=[_info("93.184.216.34")])
    )

    result = await r.resolve("example.com", 80)
    assert result == [_info("93.184.216.34")]


@pytest.mark.asyncio
async def test_safe_resolver_filters_private_addresses(monkeypatch):
    r = SafeResolver()
    monkeypatch.setattr(
        r._inner,
        "resolve",
        AsyncMock(return_value=[_info("93.184.216.34"), _info("10.0.0.5")]),
    )

    result = await r.resolve("mixed.example.com", 80)
    assert result == [_info("93.184.216.34")]


@pytest.mark.asyncio
async def test_safe_resolver_raises_when_all_unsafe(monkeypatch):
    r = SafeResolver()
    monkeypatch.setattr(
        r._inner,
        "resolve",
        AsyncMock(return_value=[_info("10.0.0.5"), _info("127.0.0.1")]),
    )

    with pytest.raises(OSError, match="unsafe SSRF"):
        await r.resolve("evil.example.com", 80)


@pytest.mark.asyncio
async def test_safe_resolver_blocks_cloud_metadata(monkeypatch):
    r = SafeResolver()
    monkeypatch.setattr(
        r._inner, "resolve", AsyncMock(return_value=[_info("169.254.169.254")])
    )

    with pytest.raises(OSError, match="unsafe SSRF"):
        await r.resolve("metadata.example.com", 80)


@pytest.mark.asyncio
async def test_safe_resolver_delegates_close(monkeypatch):
    r = SafeResolver()
    closer = AsyncMock()
    monkeypatch.setattr(r._inner, "close", closer)

    await r.close()
    closer.assert_awaited_once()
