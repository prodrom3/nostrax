"""Generate HTML reports from crawl results.

Copyright (c) 2024 prodrom3 / radamic
Licensed under the MIT License.
Last updated: 2026-04-02
"""

import html
import logging
from collections import Counter

from nostrax.models import UrlResult

logger = logging.getLogger(__name__)


def generate_html_report(
    results: list[UrlResult],
    target: str,
    statuses: dict[str, int | None] | None = None,
) -> str:
    """Generate a self-contained HTML report.

    Args:
        results: List of UrlResult objects.
        target: The original target URL.
        statuses: Optional URL -> HTTP status mapping.

    Returns:
        Complete HTML document as a string.
    """
    total = len(results)

    # Compute stats
    tag_counts = Counter(r.tag for r in results if r.tag)
    depth_counts = Counter(r.depth for r in results)
    source_counts = Counter(r.source for r in results if r.source)

    status_summary = ""
    if statuses:
        ok = sum(1 for s in statuses.values() if s and 200 <= s < 400)
        broken = sum(1 for s in statuses.values() if s and s >= 400)
        failed = sum(1 for s in statuses.values() if s is None)
        status_summary = f"""
        <div class="stat-card">
            <h3>Status</h3>
            <p class="ok">{ok} OK</p>
            <p class="broken">{broken} Broken</p>
            <p class="failed">{failed} Failed</p>
        </div>"""

    # Build table rows
    rows = []
    for r in results:
        status_val = statuses.get(r.url) if statuses else None
        status_class = ""
        status_text = "-"
        if status_val is not None:
            status_text = str(status_val)
            if 200 <= status_val < 400:
                status_class = "ok"
            elif status_val >= 400:
                status_class = "broken"
        elif statuses is not None:
            status_text = "ERR"
            status_class = "failed"

        resp_time = ""
        if r.response_time is not None:
            resp_time = f"{r.response_time:.0f}ms"

        rows.append(
            f'<tr>'
            f'<td><a href="{html.escape(r.url)}" target="_blank">{html.escape(r.url)}</a></td>'
            f'<td>{html.escape(r.source or "-")}</td>'
            f'<td>{html.escape(r.tag or "-")}</td>'
            f'<td>{r.depth}</td>'
            f'<td class="{status_class}">{status_text}</td>'
            f'<td>{resp_time}</td>'
            f'</tr>'
        )

    table_html = "\n".join(rows)

    top_sources = "\n".join(
        f"<li>{html.escape(src)} ({cnt})</li>"
        for src, cnt in source_counts.most_common(10)
    )

    tag_stats = "\n".join(
        f"<li>&lt;{html.escape(tag)}&gt; ({cnt})</li>"
        for tag, cnt in tag_counts.most_common()
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>nostrax Report - {html.escape(target)}</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, monospace;
         background: #0d1117; color: #c9d1d9; padding: 2rem; }}
  h1 {{ color: #58a6ff; margin-bottom: 0.5rem; }}
  h2 {{ color: #8b949e; margin: 1.5rem 0 0.5rem; }}
  h3 {{ color: #58a6ff; margin-bottom: 0.5rem; }}
  .target {{ color: #8b949e; margin-bottom: 1.5rem; }}
  .stats {{ display: flex; gap: 1rem; flex-wrap: wrap; margin-bottom: 1.5rem; }}
  .stat-card {{ background: #161b22; border: 1px solid #30363d; border-radius: 6px;
                padding: 1rem; min-width: 150px; }}
  .stat-card p {{ font-size: 1.2rem; font-weight: bold; }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 1rem;
           background: #161b22; border: 1px solid #30363d; border-radius: 6px; }}
  th {{ background: #21262d; color: #8b949e; text-align: left; padding: 0.5rem 1rem;
        font-weight: 600; border-bottom: 1px solid #30363d; }}
  td {{ padding: 0.4rem 1rem; border-bottom: 1px solid #21262d;
        font-size: 0.9rem; word-break: break-all; }}
  tr:hover {{ background: #1c2128; }}
  a {{ color: #58a6ff; text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
  .ok {{ color: #3fb950; }}
  .broken {{ color: #f85149; }}
  .failed {{ color: #d29922; }}
  ul {{ list-style: none; padding: 0; }}
  li {{ padding: 0.2rem 0; }}
  .filter {{ margin: 1rem 0; }}
  .filter input {{ background: #0d1117; border: 1px solid #30363d; color: #c9d1d9;
                   padding: 0.5rem; border-radius: 4px; width: 300px; }}
</style>
</head>
<body>
<h1>nostrax Report</h1>
<p class="target">Target: <a href="{html.escape(target)}">{html.escape(target)}</a></p>

<div class="stats">
    <div class="stat-card">
        <h3>Total URLs</h3>
        <p>{total}</p>
    </div>
    <div class="stat-card">
        <h3>Unique Sources</h3>
        <p>{len(source_counts)}</p>
    </div>
    <div class="stat-card">
        <h3>Max Depth</h3>
        <p>{max(depth_counts.keys()) if depth_counts else 0}</p>
    </div>
    {status_summary}
</div>

<h2>Tags</h2>
<ul>{tag_stats}</ul>

<h2>Top Sources</h2>
<ul>{top_sources}</ul>

<h2>URLs</h2>
<div class="filter">
    <input type="text" id="search" placeholder="Filter URLs..." oninput="filterTable()">
</div>
<table id="url-table">
<thead>
<tr>
    <th>URL</th>
    <th>Source</th>
    <th>Tag</th>
    <th>Depth</th>
    <th>Status</th>
    <th>Time</th>
</tr>
</thead>
<tbody>
{table_html}
</tbody>
</table>

<script>
function filterTable() {{
    const query = document.getElementById('search').value.toLowerCase();
    const rows = document.querySelectorAll('#url-table tbody tr');
    rows.forEach(row => {{
        const text = row.textContent.toLowerCase();
        row.style.display = text.includes(query) ? '' : 'none';
    }});
}}
</script>
</body>
</html>"""
