"""Tests for nostrax.cache."""

import os

from nostrax.cache import CrawlCache
from nostrax.models import UrlResult


def test_cache_initialize_creates_dir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cache_dir = str(tmp_path / "cache")
    cache = CrawlCache(cache_dir)
    cache.initialize()
    assert os.path.isdir(cache_dir)


def test_cache_mark_and_save_visited(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cache = CrawlCache(str(tmp_path))
    cache.initialize()

    cache.mark_visited("https://example.com/page1")
    cache.mark_visited("https://example.com/page2")
    cache.save_visited()

    cache2 = CrawlCache(str(tmp_path))
    cache2.initialize()
    assert "https://example.com/page1" in cache2.visited
    assert "https://example.com/page2" in cache2.visited


def test_cache_save_and_load_results(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cache = CrawlCache(str(tmp_path))
    cache.initialize()

    cache.save_result(UrlResult(url="https://example.com/a", source="https://example.com", tag="a", depth=0))
    cache.save_result(UrlResult(url="https://example.com/b", tag="img", depth=1))

    results = cache.load_results()
    assert len(results) == 2
    assert results[0].url == "https://example.com/a"
    assert results[1].tag == "img"


def test_cache_clear(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cache = CrawlCache(str(tmp_path))
    cache.initialize()

    cache.mark_visited("https://example.com")
    cache.save_visited()
    cache.save_result(UrlResult(url="https://example.com"))

    cache.clear()

    cache2 = CrawlCache(str(tmp_path))
    cache2.initialize()
    assert len(cache2.visited) == 0
    assert len(cache2.load_results()) == 0


def test_cache_empty_load(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cache = CrawlCache(str(tmp_path))
    cache.initialize()
    assert cache.load_results() == []
    assert cache.visited == set()


def test_save_visited_is_atomic_no_tmp_left_behind(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cache = CrawlCache(str(tmp_path))
    cache.initialize()
    cache.mark_visited("https://example.com/a")
    cache.save_visited()

    assert os.path.isfile(str(tmp_path / "visited.json"))
    assert not os.path.exists(str(tmp_path / "visited.json.tmp"))


def test_save_visited_preserves_prior_file_if_rename_fails(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cache = CrawlCache(str(tmp_path))
    cache.initialize()

    cache.mark_visited("https://example.com/first")
    cache.save_visited()

    cache.mark_visited("https://example.com/second")
    monkeypatch.setattr("os.replace", _boom)
    import pytest
    with pytest.raises(OSError):
        cache.save_visited()

    # Previous state must survive the failed rewrite.
    reloaded = CrawlCache(str(tmp_path))
    reloaded.initialize()
    assert "https://example.com/first" in reloaded.visited
    assert "https://example.com/second" not in reloaded.visited


def _boom(*args, **kwargs):
    raise OSError("simulated rename failure")


def test_cache_rejects_path_traversal(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    import pytest
    with pytest.raises(ValueError, match="must be under"):
        CrawlCache(str(tmp_path / ".." / "evil_cache"))
