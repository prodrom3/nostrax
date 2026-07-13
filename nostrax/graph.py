"""Export crawl results as a link graph (Graphviz DOT or GraphML).

Every :class:`~nostrax.models.UrlResult` records the page it was found on
(``source``) and the URL it points at (``url``), which is a directed edge
``source -> url``. These helpers turn a result list into a graph document
that Graphviz, Gephi, yEd, networkx, or similar tooling can render.

Copyright (c) 2024 prodrom3 / radamic
Licensed under the MIT License.
"""

import html as _html
import logging

from nostrax.models import UrlResult

logger = logging.getLogger(__name__)


def _nodes_and_edges(
    results: list[UrlResult],
) -> tuple[dict[str, str], list[tuple[str, str]]]:
    """Return (url -> node-id) and a list of (source_url, target_url) edges.

    Every result URL becomes a node; an edge is emitted only when the result
    carries a real ``source`` page (sitemap-sourced entries and seeds have
    none and appear as edge-less nodes).
    """
    nodes: dict[str, str] = {}

    def node_id(url: str) -> str:
        if url not in nodes:
            nodes[url] = f"n{len(nodes)}"
        return nodes[url]

    edges: list[tuple[str, str]] = []
    for r in results:
        node_id(r.url)
        if r.source:
            node_id(r.source)
            edges.append((r.source, r.url))
    return nodes, edges


def _dot_escape(value: str) -> str:
    """Escape a string for a double-quoted Graphviz DOT identifier."""
    return value.replace("\\", "\\\\").replace('"', '\\"')


def generate_dot(results: list[UrlResult]) -> str:
    """Render the crawl's link graph as a Graphviz DOT document."""
    nodes, edges = _nodes_and_edges(results)
    lines = [
        "digraph nostrax {",
        "  rankdir=LR;",
        "  node [shape=box, fontsize=10];",
    ]
    for url in nodes:
        lines.append(f'  "{_dot_escape(url)}";')
    for source, target in edges:
        lines.append(f'  "{_dot_escape(source)}" -> "{_dot_escape(target)}";')
    lines.append("}")
    return "\n".join(lines)


def generate_graphml(results: list[UrlResult]) -> str:
    """Render the crawl's link graph as a GraphML document."""
    nodes, edges = _nodes_and_edges(results)
    out = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<graphml xmlns="http://graphml.graphdrawing.org/xmlns">',
        '  <key id="url" for="node" attr.name="url" attr.type="string"/>',
        '  <graph edgedefault="directed">',
    ]
    for url, node_id in nodes.items():
        out.append(
            f'    <node id="{node_id}">'
            f'<data key="url">{_html.escape(url)}</data></node>'
        )
    for i, (source, target) in enumerate(edges):
        out.append(
            f'    <edge id="e{i}" source="{nodes[source]}" '
            f'target="{nodes[target]}"/>'
        )
    out.append("  </graph>")
    out.append("</graphml>")
    return "\n".join(out)
