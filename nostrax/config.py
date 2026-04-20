"""Config file support for nostrax.

Loads settings from .nostraxrc (TOML format) in the current directory
or home directory, merging with CLI arguments.

Copyright (c) 2024 prodrom3 / radamic
Licensed under the MIT License.
"""

import argparse
import logging
import os

logger = logging.getLogger(__name__)

CONFIG_FILENAMES = [".nostraxrc", "nostrax.toml"]

# Maps config keys to CLI argument names
CONFIG_KEYS: dict[str, type] = {
    "target": str,
    "depth": int,
    "timeout": int,
    "connect_timeout": float,
    "read_timeout": float,
    "user_agent": str,
    "max_concurrent": int,
    "max_urls": int,
    "rate_limit": float,
    "proxy": str,
    "auth": str,
    "domain": str,
    "protocol": str,
    "pattern": str,
    "exclude": str,
    "format": str,
    "output": str,
    "tags": str,
    "scope": str,
    "strategy": str,
    "retries": int,
    "cache_dir": str,
}

# Boolean flags
BOOL_KEYS: set[str] = {
    "silent",
    "verbose",
    "all_tags",
    "sort",
    "no_dedup",
    "respect_robots",
    "sitemap",
    "check_status",
    "metadata",
    "progress",
}


def _find_config_file() -> str | None:
    """Search for a config file in cwd, then home directory."""
    search_dirs = [os.getcwd(), os.path.expanduser("~")]

    for directory in search_dirs:
        for filename in CONFIG_FILENAMES:
            path = os.path.join(directory, filename)
            if os.path.isfile(path):
                return path
    return None


def _parse_toml(path: str) -> dict:
    """Parse a TOML file via stdlib tomllib (3.11+) or the tomli backport (3.10)."""
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib  # pyproject.toml pins this on Python < 3.11
    with open(path, "rb") as f:
        return tomllib.load(f)


def load_config() -> dict:
    """Load config from file if it exists. Returns empty dict if not found."""
    path = _find_config_file()
    if path is None:
        return {}

    logger.info("Loading config from %s", path)
    try:
        config = _parse_toml(path)
        # Flatten if there's a [nostrax] section
        if "nostrax" in config and isinstance(config["nostrax"], dict):
            config = config["nostrax"]
        return config
    except Exception as e:
        logger.warning("Failed to parse config file %s: %s", path, e)
        return {}


def user_provided_attrs(
    parser: argparse.ArgumentParser, argv: list[str] | None
) -> set[str]:
    """Return the set of ``dest`` names the user explicitly passed on argv.

    Done by temporarily setting every action's default to ``argparse.SUPPRESS``
    and reparsing, so the resulting namespace contains only user-supplied
    values. The parser is restored before returning so the caller can keep
    using it with its real defaults.
    """
    saved: list[tuple[argparse.Action, object]] = []
    for action in parser._actions:
        saved.append((action, action.default))
        action.default = argparse.SUPPRESS
    try:
        ns = parser.parse_args(argv)
    finally:
        for action, default in saved:
            action.default = default
    return set(vars(ns).keys())


def merge_config(
    args: object, config: dict, provided: set[str]
) -> None:
    """Apply config values to ``args`` for keys the user did not pass on argv.

    ``provided`` is the set of ``dest`` names the user explicitly supplied
    (see :func:`user_provided_attrs`). Config keys corresponding to those
    names are skipped; every other recognised key overrides its default.
    """
    for key, value in config.items():
        attr = key.replace("-", "_")
        if not hasattr(args, attr):
            continue
        if attr in provided:
            continue
        setattr(args, attr, value)
