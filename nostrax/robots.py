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


def _extract_crawl_delay(lines: list[str], user_agent: str) -> float | None:
    """Parse the applicable Crawl-delay for ``user_agent`` from robots.txt.

    Written by hand because stdlib ``RobotFileParser`` accepts only integer
    delays (it gates on ``str.isdigit``), silently dropping the very common
    fractional form ``Crawl-delay: 0.5``. Consecutive ``User-agent`` lines
    share one group; a more specific agent match wins over ``*``.
    """
    groups: list[tuple[list[str], float | None]] = []
    agents: list[str] = []
    delay: float | None = None
    in_rules = False

    for raw in lines:
        line = raw.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip().lower()
        val = val.strip()
        if key == "user-agent":
            if in_rules:  # a new group begins after the previous group's rules
                groups.append((agents, delay))
                agents, delay, in_rules = [], None, False
            agents.append(val.lower())
        elif key == "crawl-delay":
            in_rules = True
            try:
                delay = float(val)
            except ValueError:
                pass
        else:
            in_rules = True
    if agents:
        groups.append((agents, delay))

    ua = user_agent.lower()
    best: tuple[int, float] | None = None  # (specificity, delay)
    for group_agents, group_delay in groups:
        if group_delay is None:
            continue
        for agent in group_agents:
            if agent == "*":
                spec = 0
            elif agent and agent in ua:
                spec = 1
            else:
                continue
            if best is None or spec > best[0]:
                best = (spec, group_delay)
            break
    return best[1] if best else None


class RobotsChecker:
    """Fetches and checks robots.txt rules for a target site."""

    def __init__(self, user_agent: str = "*") -> None:
        self._user_agent = user_agent
        self._parser = RobotFileParser()
        self._loaded = False
        self._crawl_delay: float | None = None

    async def load(
        self,
        session: aiohttp.ClientSession,
        url: str,
        *,
        timeout: int = 10,
        proxy: str | None = None,
        connect_timeout: float | None = None,
        read_timeout: float | None = None,
    ) -> None:
        """Fetch and parse the robots.txt for the given URL's domain."""
        parsed = urlparse(url)
        robots_url = urljoin(f"{parsed.scheme}://{parsed.netloc}", "/robots.txt")

        client_timeout = aiohttp.ClientTimeout(
            total=timeout, connect=connect_timeout, sock_read=read_timeout
        )
        try:
            async with session.get(
                robots_url,
                timeout=client_timeout,
                allow_redirects=False,
                proxy=proxy,
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
                lines = text.splitlines()
                self._parser.parse(lines)
                self._crawl_delay = _extract_crawl_delay(lines, self._user_agent)
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

    def sitemaps(self) -> list[str]:
        """Return the ``Sitemap:`` URLs declared in robots.txt, if any.

        robots.txt is the standard place sites advertise sitemaps that are
        not at the conventional ``/sitemap.xml`` path. Empty list when no
        robots.txt was loaded or none were declared.
        """
        if not self._loaded:
            return []
        return list(self._parser.site_maps() or [])

    def crawl_delay(self) -> float | None:
        """Return the robots.txt Crawl-delay for our user agent, if any.

        ``None`` when no robots.txt was loaded or the site declares no
        delay for this agent. The crawler uses this to raise its per-host
        minimum interval so a polite crawl honours the site's stated rate.
        Fractional delays are supported (stdlib's parser drops them).
        """
        if not self._loaded:
            return None
        return self._crawl_delay
