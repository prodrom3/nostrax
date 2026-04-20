"""Robots.txt checker for respecting crawl rules.

Copyright (c) 2024 prodrom3 / radamic
Licensed under the MIT License.
"""

import logging
from urllib.parse import urlparse, urljoin
from urllib.robotparser import RobotFileParser

import aiohttp

logger = logging.getLogger(__name__)

MAX_ROBOTS_SIZE = 1 * 1024 * 1024  # 1 MiB; Google's published cap is 500 KB.


class RobotsChecker:
    """Fetches and checks robots.txt rules for a target site."""

    def __init__(self, user_agent: str = "*") -> None:
        self._user_agent = user_agent
        self._parser = RobotFileParser()
        self._loaded = False

    async def load(
        self,
        session: aiohttp.ClientSession,
        url: str,
        *,
        timeout: int = 10,
    ) -> None:
        """Fetch and parse the robots.txt for the given URL's domain."""
        parsed = urlparse(url)
        robots_url = urljoin(f"{parsed.scheme}://{parsed.netloc}", "/robots.txt")

        try:
            async with session.get(
                robots_url,
                timeout=aiohttp.ClientTimeout(total=timeout),
                allow_redirects=False,
            ) as response:
                if response.status != 200:
                    logger.info(
                        "No robots.txt at %s (status %d), allowing all",
                        robots_url,
                        response.status,
                    )
                    self._loaded = False
                    return
                body = await response.content.read(MAX_ROBOTS_SIZE + 1)
                if len(body) > MAX_ROBOTS_SIZE:
                    logger.warning(
                        "robots.txt at %s exceeds %d bytes, ignoring",
                        robots_url, MAX_ROBOTS_SIZE,
                    )
                    self._loaded = False
                    return
                text = body.decode("utf-8", errors="replace")
                self._parser.parse(text.splitlines())
                self._loaded = True
                logger.info("Loaded robots.txt from %s", robots_url)
        except (aiohttp.ClientError, TimeoutError) as e:
            logger.warning("Could not fetch robots.txt from %s: %s", robots_url, e)
            self._loaded = False

    def is_allowed(self, url: str) -> bool:
        """Check whether the given URL is allowed by robots.txt.

        Returns True if robots.txt was not loaded (permissive fallback).
        """
        if not self._loaded:
            return True
        return self._parser.can_fetch(self._user_agent, url)
