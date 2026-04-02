"""Check for newer versions of nostrax on PyPI.

Copyright (c) 2024 prodrom3 / radamic
Licensed under the MIT License.
Last updated: 2026-04-02
"""

import json
import logging
from urllib.error import URLError
from urllib.request import Request, urlopen

from nostrax import __version__

logger = logging.getLogger(__name__)

PYPI_URL = "https://pypi.org/pypi/nostrax/json"
TIMEOUT = 5


def parse_version(version: str) -> tuple[int, ...]:
    """Parse a semver string into a comparable tuple."""
    return tuple(int(x) for x in version.split("."))


def get_latest_version() -> str | None:
    """Fetch the latest version string from PyPI.

    Returns None if the request fails.
    """
    try:
        req = Request(PYPI_URL, headers={"Accept": "application/json"})
        with urlopen(req, timeout=TIMEOUT) as resp:
            data = json.loads(resp.read())
            return data["info"]["version"]
    except (URLError, OSError, KeyError, json.JSONDecodeError) as e:
        logger.debug("Could not reach PyPI: %s", e)
        return None


def check_update() -> str:
    """Check if a newer version is available.

    Returns a human-readable status message.
    """
    latest = get_latest_version()

    if latest is None:
        return (
            f"nostrax {__version__} (installed)\n"
            "Could not reach PyPI to check for updates."
        )

    try:
        current = parse_version(__version__)
        remote = parse_version(latest)
    except ValueError:
        return (
            f"nostrax {__version__} (installed)\n"
            f"Could not parse version: {latest}"
        )

    if remote > current:
        return (
            f"nostrax {__version__} (installed)\n"
            f"nostrax {latest} (available)\n"
            f"Run: pip install --upgrade nostrax"
        )
    elif remote == current:
        return f"nostrax {__version__} - up to date."
    else:
        return (
            f"nostrax {__version__} (installed, newer than PyPI)\n"
            f"nostrax {latest} (PyPI)"
        )
