"""URL normalization for improved deduplication.

Copyright (c) 2024 prodrom3 / radamic
Licensed under the MIT License.
"""

from urllib.parse import urlparse, urlunparse, urlencode, parse_qsl


def normalize_url(url: str) -> str:
    """Normalize a URL to improve deduplication.

    - Lowercases scheme and host
    - Removes default ports (80 for http, 443 for https)
    - Removes fragments (#section)
    - Removes trailing slashes from paths (except root "/")
    - Sorts query parameters
    - Removes empty query strings
    """
    parsed = urlparse(url)

    # Lowercase scheme and host
    scheme = parsed.scheme.lower()
    netloc = parsed.hostname or ""
    if parsed.port:
        default_ports = {"http": 80, "https": 443}
        if parsed.port != default_ports.get(scheme):
            netloc = f"{netloc}:{parsed.port}"

    # Strip credentials from URLs to prevent leaking them in output
    # (userinfo is intentionally dropped)

    # Normalize path - remove trailing slash except for root
    path = parsed.path
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    if not path:
        path = "/"

    # Sort query parameters and remove empty
    query_params = parse_qsl(parsed.query, keep_blank_values=False)
    query_params.sort()
    query = urlencode(query_params)

    # Drop fragment entirely
    return urlunparse((scheme, netloc, path, parsed.params, query, ""))
