"""Input validation for CLI arguments.

Copyright (c) 2024 prodrom3 / radamic
Licensed under the MIT License.
Last updated: 2026-04-02
"""

import ipaddress
import logging
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


def validate_target_url(url: str) -> str | None:
    """Validate a target URL, rejecting unsafe schemes and private IPs.

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

    # Check for private/loopback IPs
    try:
        ip = ipaddress.ip_address(hostname)
        if ip.is_private or ip.is_loopback or ip.is_link_local:
            return f"Private/loopback IP not allowed: {ip}"
        # Block cloud metadata endpoint
        if str(ip) == "169.254.169.254":
            return "Cloud metadata endpoint not allowed."
    except ValueError:
        # Not an IP address - it's a domain name, check for localhost
        if hostname in ("localhost", "localhost.localdomain"):
            return "localhost not allowed as target."

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
