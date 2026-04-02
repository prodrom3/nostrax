"""Tests for nostrax.config."""

import os
import argparse

from nostrax.config import load_config, merge_config, _parse_simple


def test_parse_simple(tmp_path):
    config_file = tmp_path / ".nostraxrc"
    config_file.write_text(
        '# comment\n'
        'depth = 3\n'
        'timeout = 30\n'
        'user_agent = "mybot/1.0"\n'
        'respect_robots = true\n'
        'rate_limit = 0.5\n'
    )

    result = _parse_simple(str(config_file))
    assert result["depth"] == 3
    assert result["timeout"] == 30
    assert result["user_agent"] == "mybot/1.0"
    assert result["respect_robots"] is True
    assert result["rate_limit"] == 0.5


def test_merge_config_applies_defaults():
    args = argparse.Namespace(
        depth=0,
        timeout=10,
        proxy=None,
        respect_robots=False,
    )
    config = {"proxy": "http://proxy:8080", "respect_robots": True}

    merge_config(args, config)
    assert args.proxy == "http://proxy:8080"
    assert args.respect_robots is True


def test_merge_config_cli_takes_priority():
    args = argparse.Namespace(
        proxy="http://my-proxy:9090",
        depth=5,
    )
    config = {"proxy": "http://other:8080", "depth": 2}

    merge_config(args, config)
    # CLI value should win
    assert args.proxy == "http://my-proxy:9090"


def test_load_config_no_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = load_config()
    assert result == {}
