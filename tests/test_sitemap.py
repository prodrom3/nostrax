"""Tests for nostrax.sitemap."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from nostrax.sitemap import fetch_sitemap, _safe_parse_xml


SITEMAP_XML = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
    <url><loc>https://example.com/page1</loc></url>
    <url><loc>https://example.com/page2</loc></url>
    <url><loc>https://example.com/page3</loc></url>
</urlset>
"""

SITEMAP_INDEX_XML = """<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
    <sitemap><loc>https://example.com/sitemap1.xml</loc></sitemap>
</sitemapindex>
"""

CHILD_SITEMAP_XML = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
    <url><loc>https://example.com/child1</loc></url>
</urlset>
"""


def _make_mock_response(text, status=200):
    mock_resp = AsyncMock()
    mock_resp.status = status
    mock_resp.text = AsyncMock(return_value=text)
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)
    return mock_resp


@pytest.mark.asyncio
async def test_fetch_sitemap_basic():
    mock_session = AsyncMock()
    mock_session.get = MagicMock(return_value=_make_mock_response(SITEMAP_XML))

    urls = await fetch_sitemap(mock_session, "https://example.com/sitemap.xml")
    assert len(urls) == 3
    assert "https://example.com/page1" in urls


@pytest.mark.asyncio
async def test_fetch_sitemap_index():
    def get_side_effect(url, **kwargs):
        if "sitemap1.xml" in url:
            return _make_mock_response(CHILD_SITEMAP_XML)
        return _make_mock_response(SITEMAP_INDEX_XML)

    mock_session = AsyncMock()
    mock_session.get = MagicMock(side_effect=get_side_effect)

    urls = await fetch_sitemap(mock_session, "https://example.com/sitemap.xml")
    assert "https://example.com/child1" in urls


@pytest.mark.asyncio
async def test_fetch_sitemap_not_found():
    mock_session = AsyncMock()
    mock_session.get = MagicMock(return_value=_make_mock_response("", status=404))

    urls = await fetch_sitemap(mock_session, "https://example.com/sitemap.xml")
    assert urls == []


@pytest.mark.asyncio
async def test_fetch_sitemap_invalid_xml():
    mock_session = AsyncMock()
    mock_session.get = MagicMock(return_value=_make_mock_response("not xml at all"))

    urls = await fetch_sitemap(mock_session, "https://example.com/sitemap.xml")
    assert urls == []


@pytest.mark.asyncio
async def test_fetch_sitemap_network_error():
    import aiohttp

    mock_session = AsyncMock()
    mock_session.get = MagicMock(side_effect=aiohttp.ClientError("fail"))

    urls = await fetch_sitemap(mock_session, "https://example.com/sitemap.xml")
    assert urls == []


def test_safe_parse_rejects_xxe_doctype():
    xxe = '<?xml version="1.0"?><!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]><root>&xxe;</root>'
    assert _safe_parse_xml(xxe) is None


def test_safe_parse_rejects_entity():
    xxe = '<?xml version="1.0"?><!ENTITY test "value"><root/>'
    assert _safe_parse_xml(xxe) is None


def test_safe_parse_valid_xml():
    result = _safe_parse_xml('<root><child>text</child></root>')
    assert result is not None
    assert result.tag == "root"


@pytest.mark.asyncio
async def test_fetch_sitemap_circular_reference():
    """Circular sitemap references should not cause infinite recursion."""
    circular_index = """<?xml version="1.0" encoding="UTF-8"?>
    <sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
        <sitemap><loc>https://example.com/sitemap.xml</loc></sitemap>
    </sitemapindex>
    """
    mock_session = AsyncMock()
    mock_session.get = MagicMock(return_value=_make_mock_response(circular_index))

    urls = await fetch_sitemap(mock_session, "https://example.com/sitemap.xml")
    assert urls == []  # Circular ref detected, no URLs extracted


@pytest.mark.asyncio
async def test_fetch_sitemap_max_depth():
    """Deeply nested sitemap indexes should stop at max depth."""
    index = """<?xml version="1.0" encoding="UTF-8"?>
    <sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
        <sitemap><loc>https://example.com/deep.xml</loc></sitemap>
    </sitemapindex>
    """
    mock_session = AsyncMock()
    mock_session.get = MagicMock(return_value=_make_mock_response(index))

    # Force starting at depth 4 (limit is 5), so only 1 more level
    urls = await fetch_sitemap(
        mock_session, "https://example.com/sitemap.xml", _depth=4
    )
    # Should stop at depth 5, returning empty
    assert urls == []
