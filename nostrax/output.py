"""Format and write extracted URLs.

Copyright (c) 2024 prodrom3 / radamic
Licensed under the MIT License.
"""

import csv
import io
import json
import logging
import os
import sys
from dataclasses import replace
from typing import TYPE_CHECKING, cast

from nostrax.models import UrlResult
from nostrax.validation import is_path_within

if TYPE_CHECKING:
    from nostrax.content import PageContent

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
        fmt: One of "plain", "json", "jsonl", "csv".
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
        results = [UrlResult(url=u) for u in cast("list[str]", urls)]
    else:
        results = [replace(r) for r in cast("list[UrlResult]", urls)]

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

    elif fmt == "jsonl":
        # One JSON value per line (JSON Lines). Streams cleanly into jq -c,
        # log pipelines, and append-only sinks without loading the whole
        # array. Objects when metadata/status is present, bare URL strings
        # otherwise - mirroring the "json" format's shape line by line.
        if include_metadata or statuses:
            return "\n".join(json.dumps(r.to_dict()) for r in results)
        return "\n".join(json.dumps(r.url) for r in results)

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
            row_writer = csv.writer(buf)
            row_writer.writerow(["url"])
            for r in results:
                row_writer.writerow([r.url])
        return buf.getvalue().rstrip("\n")

    else:
        raise ValueError(f"Unknown format: {fmt!r}")


def format_content(pages: "list[PageContent]", fmt: str = "plain") -> str:
    """Format scraped page content as plain, json, jsonl, or csv."""
    if fmt == "json":
        return json.dumps([p.to_dict() for p in pages], indent=2)
    if fmt == "jsonl":
        return "\n".join(json.dumps(p.to_dict()) for p in pages)
    if fmt == "csv":
        buf = io.StringIO()
        fields = ["url", "title", "description", "canonical", "lang", "keywords", "robots"]
        writer = csv.DictWriter(buf, fieldnames=fields)
        writer.writeheader()
        for p in pages:
            writer.writerow({f: getattr(p, f) for f in fields})
        return buf.getvalue().rstrip("\n")
    if fmt == "plain":
        lines = []
        for p in pages:
            lines.append(f"{p.url}\t{p.title}" if p.title else p.url)
        return "\n".join(lines)
    raise ValueError(f"Unsupported content format: {fmt!r}")


def write_content_output(
    pages: "list[PageContent]",
    fmt: str = "plain",
    output_file: str | None = None,
) -> None:
    """Format scraped page content and write to stdout or a cwd-confined file."""
    formatted = format_content(pages, fmt)
    if not formatted:
        return
    if output_file:
        output_path = os.path.realpath(output_file)
        if not is_path_within(output_path, os.getcwd()):
            logger.error("Refusing to write outside working directory: %s", output_file)
            return
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(formatted + "\n")
    else:
        sys.stdout.write(formatted + "\n")


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
        urls,
        fmt,
        include_metadata=include_metadata,
        statuses=statuses,
    )
    if not formatted:
        return

    if output_file:
        output_path = os.path.realpath(output_file)
        if not is_path_within(output_path, os.getcwd()):
            logger.error("Refusing to write outside working directory: %s", output_file)
            return
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(formatted + "\n")
    else:
        sys.stdout.write(formatted + "\n")
