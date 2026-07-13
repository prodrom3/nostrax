"""Extract page-level content and metadata from HTML.

Where :mod:`nostrax.extractor` pulls the *links* out of a page, this module
pulls the page's own metadata - title, description, canonical URL, language,
Open Graph tags, and JSON-LD blocks - turning the crawler from a URL mapper
into a light scraper. Use it standalone via :func:`extract_content`, or drive
it over a whole crawl with ``crawl(..., collect_content=True)``.

Copyright (c) 2024 prodrom3 / radamic
Licensed under the MIT License.
"""

import json
import logging
from dataclasses import dataclass, field
from urllib.parse import urljoin

from bs4 import BeautifulSoup, SoupStrainer, Tag

logger = logging.getLogger(__name__)

# Only the elements that carry page metadata, so lxml can skip the body.
_CONTENT_TAGS = ["title", "meta", "link", "html", "script"]


@dataclass
class PageContent:
    """Metadata scraped from a single HTML page."""

    url: str
    title: str = ""
    description: str = ""
    canonical: str = ""
    lang: str = ""
    keywords: str = ""
    robots: str = ""
    og: dict[str, str] = field(default_factory=dict)
    jsonld: list = field(default_factory=list)
    status: int | None = None
    depth: int = 0

    def to_dict(self) -> dict:
        d: dict = {"url": self.url}
        for key in ("title", "description", "canonical", "lang", "keywords", "robots"):
            value = getattr(self, key)
            if value:
                d[key] = value
        if self.og:
            d["og"] = self.og
        if self.jsonld:
            d["jsonld"] = self.jsonld
        if self.status is not None:
            d["status"] = self.status
        if self.depth:
            d["depth"] = self.depth
        return d


def _attr(element: Tag | None, name: str) -> str:
    """Return a string attribute value, or '' (bs4 may return a list)."""
    if element is None:
        return ""
    value = element.get(name)
    return value.strip() if isinstance(value, str) else ""


def extract_content(html: str, url: str, *, depth: int = 0) -> PageContent:
    """Extract title, description, canonical, language, OG, and JSON-LD.

    ``url`` is the page's own URL, used both as the result key and to
    resolve a relative ``<link rel="canonical">``.
    """
    strainer = SoupStrainer(_CONTENT_TAGS)
    soup = BeautifulSoup(html, "lxml", parse_only=strainer)

    content = PageContent(url=url, depth=depth)

    title_el = soup.find("title")
    if title_el is not None:
        content.title = title_el.get_text(strip=True)

    html_el = soup.find("html")
    if isinstance(html_el, Tag):
        content.lang = _attr(html_el, "lang")

    for meta in soup.find_all("meta"):
        if not isinstance(meta, Tag):
            continue
        name = (_attr(meta, "name") or "").lower()
        prop = (_attr(meta, "property") or "").lower()
        value = _attr(meta, "content")
        if not value:
            continue
        if name == "description":
            content.description = content.description or value
        elif name == "keywords":
            content.keywords = content.keywords or value
        elif name == "robots":
            content.robots = content.robots or value
        elif prop.startswith("og:"):
            content.og.setdefault(prop, value)

    for link in soup.find_all("link"):
        if not isinstance(link, Tag):
            continue
        rel = link.get("rel")
        rel_values = rel if isinstance(rel, list) else [rel]
        if any(isinstance(r, str) and r.lower() == "canonical" for r in rel_values):
            href = _attr(link, "href")
            if href:
                content.canonical = urljoin(url, href)
                break

    for script in soup.find_all("script"):
        if not isinstance(script, Tag):
            continue
        if (_attr(script, "type") or "").lower() != "application/ld+json":
            continue
        text = script.get_text()
        if not text or not text.strip():
            continue
        try:
            content.jsonld.append(json.loads(text))
        except (json.JSONDecodeError, ValueError):
            logger.debug("Skipping unparseable JSON-LD on %s", url)

    return content
