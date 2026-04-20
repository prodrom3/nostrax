"""Aiohttp resolver that re-applies the SSRF classifier at request time.

``validate_target_url`` runs once at CLI entry, resolves the target
hostname, and rejects unsafe addresses. Between that check and the
actual fetch, aiohttp resolves DNS again; nothing stops a malicious
authoritative server from returning a public address for the validation
lookup and a private one a few hundred milliseconds later (TTL=0 DNS
rebinding). This resolver closes that window by running every address
returned from DNS through the same ``_classify_unsafe_ip`` predicate.

Copyright (c) 2024 prodrom3 / radamic
Licensed under the MIT License.
"""

import ipaddress
import logging

from aiohttp.abc import AbstractResolver
from aiohttp.resolver import DefaultResolver

from nostrax.validation import _classify_unsafe_ip

logger = logging.getLogger(__name__)


class SafeResolver(AbstractResolver):
    """Wrap the default aiohttp resolver and drop unsafe addresses.

    Usage::

        connector = aiohttp.TCPConnector(resolver=SafeResolver(), ...)

    If every address for a hostname is classified unsafe the resolve()
    call raises ``OSError`` so aiohttp treats it as a connection failure
    rather than silently trying an address that was about to be
    rejected anyway.
    """

    def __init__(self) -> None:
        self._inner = DefaultResolver()

    async def resolve(
        self, host: str, port: int = 0, family: int = 0
    ) -> list[dict]:
        infos = await self._inner.resolve(host, port, family)
        safe: list[dict] = []
        for info in infos:
            addr = info.get("host", "")
            try:
                ip = ipaddress.ip_address(addr)
            except ValueError:
                continue
            reason = _classify_unsafe_ip(ip)
            if reason is not None:
                logger.warning(
                    "SafeResolver: refusing %s -> %s (%s)", host, addr, reason
                )
                continue
            safe.append(info)
        if not safe:
            raise OSError(
                f"Refused to connect to {host!r}: "
                f"all resolved addresses are unsafe SSRF targets"
            )
        return safe

    async def close(self) -> None:
        await self._inner.close()
