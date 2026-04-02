"""Config file support for nostrax.

Loads settings from .nostraxrc (TOML format) in the current directory
or home directory, merging with CLI arguments.

Copyright (c) 2024 prodrom3 / radamic
Licensed under the MIT License.
Last updated: 2026-04-02
"""

import logging
import os

logger = logging.getLogger(__name__)

CONFIG_FILENAMES = [".nostraxrc", "nostrax.toml"]

# Maps config keys to CLI argument names
CONFIG_KEYS: dict[str, type] = {
    "target": str,
    "depth": int,
    "timeout": int,
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
    """Parse a TOML file. Uses tomllib (3.11+) or falls back to manual parsing."""
    try:
        import tomllib
    except ImportError:
        try:
            import tomli as tomllib
        except ImportError:
            # Simple fallback parser for key = value lines
            return _parse_simple(path)

    with open(path, "rb") as f:
        return tomllib.load(f)


def _parse_simple(path: str) -> dict:
    """Simple key=value parser for environments without tomllib."""
    result: dict = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("["):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")

            if key in BOOL_KEYS:
                result[key] = value.lower() in ("true", "1", "yes")
            elif key in CONFIG_KEYS:
                try:
                    result[key] = CONFIG_KEYS[key](value)
                except (ValueError, TypeError):
                    logger.warning("Invalid value for %s in config: %s", key, value)
            else:
                result[key] = value

    return result


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


def merge_config(args: object, config: dict) -> None:
    """Apply config values to args, but CLI arguments take priority.

    Only sets values that are still at their defaults.
    """
    for key, value in config.items():
        # Convert hyphens to underscores for argparse compatibility
        attr = key.replace("-", "_")
        if not hasattr(args, attr):
            continue

        current = getattr(args, attr)

        # Only apply config if the CLI arg is at its default
        # For booleans, default is False; for optional strings, default is None
        # For ints/floats, compare to parser defaults
        if current is None or current is False:
            setattr(args, attr, value)
