"""Smoke tests for the shipped examples (no browser required)."""

import importlib.util
import os

import pytest

_EXAMPLE = os.path.join(
    os.path.dirname(__file__), "..", "examples", "playwright_fetcher.py"
)


def _load_example():
    spec = importlib.util.spec_from_file_location("playwright_fetcher", _EXAMPLE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_playwright_example_imports_without_browser():
    # Playwright is imported lazily inside start(), so the module (and the
    # Fetcher class) must import even when Playwright is not installed.
    module = _load_example()
    assert hasattr(module, "PlaywrightFetcher")


@pytest.mark.asyncio
async def test_playwright_fetch_requires_start():
    module = _load_example()
    fetcher = module.PlaywrightFetcher()
    with pytest.raises(RuntimeError):
        await fetcher.fetch(None, "https://example.com")
