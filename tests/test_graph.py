"""Tests for nostrax.graph."""

from xml.etree import ElementTree

from nostrax.graph import generate_dot, generate_graphml
from nostrax.models import UrlResult


RESULTS = [
    UrlResult(url="https://example.com/a", source="https://example.com", tag="a"),
    UrlResult(url="https://example.com/b", source="https://example.com", tag="a"),
    UrlResult(url="https://example.com/c", source="https://example.com/a", tag="a"),
    UrlResult(url="https://example.com/seed", source="", tag="sitemap"),
]


def test_dot_has_header_and_edges():
    dot = generate_dot(RESULTS)
    assert dot.startswith("digraph nostrax {")
    assert dot.rstrip().endswith("}")
    assert '"https://example.com" -> "https://example.com/a";' in dot
    assert '"https://example.com/a" -> "https://example.com/c";' in dot
    # sourceless node still appears, with no edge
    assert '"https://example.com/seed";' in dot
    assert "-> \"https://example.com/seed\"" not in dot


def test_dot_escapes_quotes():
    dot = generate_dot([UrlResult(url='https://x.test/a"b', source="https://x.test")])
    assert '\\"' in dot  # the embedded quote is escaped


def test_graphml_is_well_formed_xml():
    xml = generate_graphml(RESULTS)
    root = ElementTree.fromstring(xml)  # raises if malformed
    ns = "{http://graphml.graphdrawing.org/xmlns}"
    graph = root.find(f"{ns}graph")
    assert graph is not None
    nodes = graph.findall(f"{ns}node")
    edges = graph.findall(f"{ns}edge")
    # 5 unique URLs (example.com, /a, /b, /c, /seed), 3 edges
    assert len(nodes) == 5
    assert len(edges) == 3
