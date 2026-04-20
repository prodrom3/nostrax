"""Tests for nostrax.config."""

import argparse

from nostrax.cli import build_parser
from nostrax.config import (
    _parse_simple,
    load_config,
    merge_config,
    user_provided_attrs,
)


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


def test_merge_config_applies_when_user_did_not_provide_flag():
    args = argparse.Namespace(
        depth=0, timeout=10, proxy=None, respect_robots=False,
    )
    config = {
        "proxy": "http://proxy:8080",
        "respect_robots": True,
        "depth": 3,
        "timeout": 30,
    }
    merge_config(args, config, provided=set())

    assert args.proxy == "http://proxy:8080"
    assert args.respect_robots is True
    # Regression: previously the merge was skipped for non-None / non-False
    # defaults, so int-valued config keys were silently ignored.
    assert args.depth == 3
    assert args.timeout == 30


def test_merge_config_cli_wins_when_user_provided_flag():
    args = argparse.Namespace(proxy="http://my-proxy:9090", depth=5)
    config = {"proxy": "http://other:8080", "depth": 2}
    merge_config(args, config, provided={"proxy", "depth"})

    assert args.proxy == "http://my-proxy:9090"
    assert args.depth == 5


def test_user_provided_attrs_detects_only_supplied_flags():
    parser = build_parser()
    provided = user_provided_attrs(parser, ["-t", "https://example.com", "--depth", "3"])
    assert "target" in provided
    assert "depth" in provided
    assert "timeout" not in provided
    assert "max_urls" not in provided


def test_user_provided_attrs_handles_short_and_long_forms():
    parser = build_parser()
    provided = user_provided_attrs(
        parser, ["-t", "https://x", "-d", "2", "--format", "json"]
    )
    assert provided == {"target", "depth", "format"}


def test_load_config_no_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = load_config()
    assert result == {}
