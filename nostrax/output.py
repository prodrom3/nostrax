"""Format and write extracted URLs.

Copyright (c) 2024 prodrom3 / radamic
Licensed under the MIT License.
Last updated: 2026-04-02
"""

import csv
import io
import json
import logging
import os
import sys
from dataclasses import replace

from nostrax.models import UrlResult

logger = logging.getLogger(__name__)


def format_urls(
    urls: list[str] | list[UrlResult],
    fmt: str = "plain",
    *,
    include_metadata: bool = False,
    statuses: dict[str, int | None] | None = None,
) -> str:
    """Format a list of URLs in the given format.

    Args:
        urls: List of URL strings or UrlResult objects.
        fmt: One of "plain", "json", "csv".
        include_metadata: Include source/tag/depth in output.
        statuses: Optional dict of URL -> HTTP status code.

    Returns:
        Formatted string.
    """
    # Normalise to a fresh list of UrlResult copies. format_urls is a
    # pure formatter; it must not mutate the caller's objects, so we
    # always work on shallow copies here.
    results: list[UrlResult]
    if urls and isinstance(urls[0], str):
        results = [UrlResult(url=u) for u in urls]
    else:
        results = [replace(r) for r in urls]  # type: ignore[arg-type]

    if statuses:
        for r in results:
            if r.url in statuses:
                r.status = statuses[r.url]

    if fmt == "plain":
        lines = []
        for r in results:
            line = r.url
            if include_metadata or statuses:
                parts = []
                if statuses and r.status is not None:
                    parts.append(f"[{r.status}]")
                if include_metadata and r.source:
                    parts.append(f"from={r.source}")
                if include_metadata and r.tag:
                    parts.append(f"tag={r.tag}")
                if include_metadata and r.depth:
                    parts.append(f"depth={r.depth}")
                if parts:
                    line += "  " + " ".join(parts)
            lines.append(line)
        return "\n".join(lines)

    elif fmt == "json":
        if include_metadata or statuses:
            return json.dumps([r.to_dict() for r in results], indent=2)
        return json.dumps([r.url for r in results], indent=2)

    elif fmt == "csv":
        buf = io.StringIO()
        if include_metadata or statuses:
            fields = ["url"]
            if include_metadata:
                fields.extend(["source", "tag", "depth"])
            if statuses:
                fields.append("status")
            writer = csv.DictWriter(buf, fieldnames=fields)
            writer.writeheader()
            for r in results:
                row: dict = {"url": r.url}
                if include_metadata:
                    row["source"] = r.source
                    row["tag"] = r.tag
                    row["depth"] = r.depth
                if statuses:
                    row["status"] = r.status
                writer.writerow(row)
        else:
            writer = csv.writer(buf)
            writer.writerow(["url"])
            for r in results:
                writer.writerow([r.url])
        return buf.getvalue().rstrip("\n")

    else:
        raise ValueError(f"Unknown format: {fmt!r}")


def write_output(
    urls: list[str] | list[UrlResult],
    fmt: str = "plain",
    output_file: str | None = None,
    *,
    include_metadata: bool = False,
    statuses: dict[str, int | None] | None = None,
) -> None:
    """Format URLs and write to stdout or a file."""
    formatted = format_urls(
        urls, fmt,
        include_metadata=include_metadata,
        statuses=statuses,
    )
    if not formatted:
        return

    if output_file:
        output_path = os.path.realpath(output_file)
        cwd = os.path.realpath(os.getcwd())
        if not output_path.startswith(cwd + os.sep) and output_path != cwd:
            logger.error(
                "Refusing to write outside working directory: %s", output_file
            )
            return
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(formatted + "\n")
    else:
        sys.stdout.write(formatted + "\n")
