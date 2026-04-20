"""Input validation for CLI arguments.

Copyright (c) 2024 prodrom3 / radamic
Licensed under the MIT License.
"""

import ipaddress
import logging
import socket
from urllib.parse import urlparse, urlunparse

logger = logging.getLogger(__name__)


def redact_credentials(url: str | None) -> str:
    """Return a copy of ``url`` with any userinfo replaced by ``***``.

    Intended for any code path that logs or surfaces a URL that may
    contain credentials (proxies, authenticated targets). Returns the
    input unchanged when there is no userinfo, and an empty string when
    ``url`` is falsy.
    """
    if not url:
        return ""
    parsed = urlparse(url)
    if not parsed.username and not parsed.password:
        return url
    host = parsed.hostname or ""
    if parsed.port:
        host = f"{host}:{parsed.port}"
    netloc = f"***@{host}" if host else "***"
    return urlunparse(
        (parsed.scheme, netloc, parsed.path, parsed.params, parsed.query, parsed.fragment)
    )

_UnsafeIP = ipaddress.IPv4Address | ipaddress.IPv6Address


def _classify_unsafe_ip(ip: _UnsafeIP) -> str | None:
    """Return a reason string if the address is an unsafe SSRF target, else None."""
    # Unwrap IPv4-mapped IPv6 (e.g. ::ffff:127.0.0.1) and recurse.
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        return _classify_unsafe_ip(ip.ipv4_mapped)

    if ip.is_loopback:
        return f"loopback IP not allowed: {ip}"
    if ip.is_link_local:
        return f"link-local IP not allowed: {ip}"
    if ip.is_private:
        return f"private IP not allowed: {ip}"
    if ip.is_unspecified:
        return f"unspecified IP not allowed: {ip}"
    if ip.is_multicast:
        return f"multicast IP not allowed: {ip}"
    if ip.is_reserved:
        return f"reserved IP not allowed: {ip}"
    # Explicit defence-in-depth against AWS/GCP/Azure IMDS even though
    # 169.254.169.254 is already caught by is_link_local.
    if str(ip) == "169.254.169.254":
        return "cloud metadata endpoint not allowed"
    return None


def validate_target_url(url: str) -> str | None:
    """Validate a target URL, rejecting unsafe schemes and addresses.

    When the hostname is a domain name, resolve it and reject if any
    returned address is unsafe (loopback, private, link-local, reserved,
    multicast, unspecified, or the cloud metadata endpoint). This closes
    the common SSRF hole where a name like ``evil.com`` resolves to an
    internal IP at fetch time.

    This check runs at CLI entry; aiohttp still re-resolves DNS at
    connection time, so the crawler additionally installs
    :class:`nostrax.resolver.SafeResolver` on its TCPConnector to
    re-apply the same classifier at every resolution, closing the TTL=0
    DNS rebinding window between validation and fetch.

    Returns an error message string, or None if valid.
    """
    parsed = urlparse(url)

    if parsed.scheme not in ("http", "https"):
        return f"Invalid scheme: {parsed.scheme!r}. Only http and https are allowed."

    if not parsed.netloc:
        return "URL must have a hostname."

    hostname = parsed.hostname or ""
    if not hostname:
        return "URL must have a hostname."

    if hostname in ("localhost", "localhost.localdomain"):
        return "localhost not allowed as target."

    try:
        ip = ipaddress.ip_address(hostname)
    except ValueError:
        ip = None

    if ip is not None:
        reason = _classify_unsafe_ip(ip)
        if reason:
            return reason.capitalize()
        return None

    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror as e:
        return f"Could not resolve hostname {hostname!r}: {e}"

    for info in infos:
        addr = info[4][0]
        try:
            resolved = ipaddress.ip_address(addr)
        except ValueError:
            continue
        reason = _classify_unsafe_ip(resolved)
        if reason:
            return f"{hostname} resolves to unsafe address: {reason}"

    return None


def validate_proxy_url(url: str) -> str | None:
    """Validate a proxy URL format.

    Returns an error message string, or None if valid.
    """
    parsed = urlparse(url)

    if parsed.scheme not in ("http", "https", "socks4", "socks5"):
        return f"Invalid proxy scheme: {parsed.scheme!r}. Use http, https, socks4, or socks5."

    if not parsed.hostname:
        return "Proxy URL must have a hostname."

    return None


def validate_positive_int(value: int, name: str) -> str | None:
    """Validate that an integer is positive. Returns error or None."""
    if value < 0:
        return f"{name} must be >= 0, got {value}"
    return None


def validate_header_value(value: str, name: str) -> str | None:
    """Validate an HTTP header value has no injection characters."""
    if "\r" in value or "\n" in value:
        return f"{name} must not contain line breaks."
    if len(value) > 500:
        return f"{name} too long (max 500 characters)."
    return None
