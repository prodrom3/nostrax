"""Tests for nostrax.output."""

import json
import os
import tempfile

import pytest

from nostrax.models import UrlResult
from nostrax.output import format_urls, write_output

URLS = ["https://example.com/a", "https://example.com/b"]


def test_format_plain():
    result = format_urls(URLS, "plain")
    assert result == "https://example.com/a\nhttps://example.com/b"


def test_format_json():
    result = format_urls(URLS, "json")
    parsed = json.loads(result)
    assert parsed == URLS


def test_format_csv():
    result = format_urls(URLS, "csv")
    lines = result.split("\n")
    assert lines[0] == "url"
    assert lines[1] == "https://example.com/a"
    assert lines[2] == "https://example.com/b"


def test_format_unknown():
    with pytest.raises(ValueError):
        format_urls(URLS, "xml")


def test_format_empty():
    assert format_urls([], "plain") == ""
    assert format_urls([], "json") == "[]"


def test_write_output_to_file():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        path = f.name

    try:
        write_output(URLS, fmt="plain", output_file=path)
        with open(path, encoding="utf-8") as f:
            content = f.read()
        assert "https://example.com/a" in content
        assert "https://example.com/b" in content
    finally:
        os.unlink(path)


def test_write_output_json_to_file():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        path = f.name

    try:
        write_output(URLS, fmt="json", output_file=path)
        with open(path, encoding="utf-8") as f:
            parsed = json.load(f)
        assert parsed == URLS
    finally:
        os.unlink(path)


def test_write_output_blocks_path_traversal(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    traversal_path = os.path.join(str(tmp_path), "..", "evil.txt")
    write_output(URLS, fmt="plain", output_file=traversal_path)
    assert not os.path.exists(os.path.realpath(traversal_path))


def test_format_plain_with_metadata():
    results = [
        UrlResult(url="https://example.com/a", source="https://example.com", tag="a", depth=0),
        UrlResult(url="https://example.com/b", source="https://example.com", tag="img", depth=1),
    ]
    output = format_urls(results, "plain", include_metadata=True)
    assert "from=https://example.com" in output
    assert "tag=a" in output
    assert "tag=img" in output
    assert "depth=1" in output


def test_format_json_with_metadata():
    results = [
        UrlResult(url="https://example.com/a", source="https://example.com", tag="a", depth=0),
    ]
    output = format_urls(results, "json", include_metadata=True)
    parsed = json.loads(output)
    assert parsed[0]["url"] == "https://example.com/a"
    assert parsed[0]["source"] == "https://example.com"
    assert parsed[0]["tag"] == "a"


def test_format_csv_with_metadata():
    results = [
        UrlResult(url="https://example.com/a", source="https://example.com", tag="a", depth=0),
    ]
    output = format_urls(results, "csv", include_metadata=True)
    lines = output.split("\n")
    assert "url" in lines[0]
    assert "source" in lines[0]
    assert "tag" in lines[0]
    assert "depth" in lines[0]


def test_format_with_statuses():
    statuses = {
        "https://example.com/a": 200,
        "https://example.com/b": 404,
    }
    output = format_urls(URLS, "plain", statuses=statuses)
    assert "[200]" in output
    assert "[404]" in output


def test_format_json_with_statuses():
    statuses = {"https://example.com/a": 200}
    results = [UrlResult(url="https://example.com/a")]
    output = format_urls(results, "json", statuses=statuses)
    parsed = json.loads(output)
    assert parsed[0]["status"] == 200
