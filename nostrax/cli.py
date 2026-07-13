"""Command-line interface for nostrax.

Copyright (c) 2024 prodrom3 / radamic
Licensed under the MIT License.
"""

import argparse
import asyncio
import logging
import os
import sys
from typing import cast

from nostrax import __version__
from nostrax.config import load_config, merge_config, user_provided_attrs
from nostrax.crawler import crawl_async, crawl_seeds_async
from nostrax.exceptions import NostraxError
from nostrax.extractor import TAG_ATTRS
from nostrax.validation import (
    is_path_within,
    validate_header_value,
    validate_proxy_url,
    validate_target_url,
)
from nostrax.filters import (
    filter_by_domain,
    filter_by_exclude,
    filter_by_pattern,
    filter_by_protocol,
)
from nostrax.models import UrlResult
from nostrax.output import write_content_output, write_output


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nostrax",
        description="Extract URLs and paths from web pages.",
    )
    parser.add_argument(
        "-V",
        "--version",
        action="version",
        version=f"nostrax {__version__}",
    )
    parser.add_argument(
        "--check-update",
        action="store_true",
        help="Check PyPI for a newer version and exit",
    )
    parser.add_argument(
        "-t",
        "--target",
        type=str,
        default=None,
        help="Target URL to extract from",
    )
    parser.add_argument(
        "--input-file",
        type=str,
        default=None,
        help="Read seed URLs from a file, one per line ('-' for stdin; "
        "blank lines and lines starting with # are ignored). Each seed "
        "is crawled independently and the results are merged.",
    )
    parser.add_argument(
        "-s",
        "--silent",
        action="store_true",
        help="Suppress all output (exit code only)",
    )
    parser.add_argument(
        "-d",
        "--depth",
        type=int,
        default=0,
        help="Recursion depth for crawling (default: 0, no recursion)",
    )
    parser.add_argument(
        "--all-tags",
        action="store_true",
        help="Extract URLs from all supported tags, not just <a>",
    )
    parser.add_argument(
        "--tags",
        type=str,
        default=None,
        help=f"Comma-separated list of tags to extract from (supported: {', '.join(sorted(TAG_ATTRS))})",
    )
    parser.add_argument(
        "--domain",
        type=str,
        choices=["all", "internal", "external"],
        default="all",
        help="Filter by domain: internal, external, or all (default: all)",
    )
    parser.add_argument(
        "--protocol",
        type=str,
        default=None,
        help="Comma-separated list of protocols to keep (e.g. https,http)",
    )
    parser.add_argument(
        "--pattern",
        type=str,
        default=None,
        help="Regex pattern to filter URLs (keep matches)",
    )
    parser.add_argument(
        "--exclude",
        type=str,
        default=None,
        help="Regex pattern to exclude URLs (remove matches)",
    )
    parser.add_argument(
        "--sort",
        action="store_true",
        help="Sort URLs alphabetically",
    )
    parser.add_argument(
        "-f",
        "--format",
        type=str,
        choices=["plain", "json", "jsonl", "csv", "html", "dot", "graphml"],
        default="plain",
        help="Output format (default: plain). jsonl = one JSON record per "
        "line; dot/graphml = source->url link graph.",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default=None,
        help="Write output to file instead of stdout",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=10,
        help="Total request timeout in seconds (default: 10)",
    )
    parser.add_argument(
        "--connect-timeout",
        type=float,
        default=None,
        help="Per-connection timeout in seconds. Defaults to --timeout when unset.",
    )
    parser.add_argument(
        "--read-timeout",
        type=float,
        default=None,
        help="Per-socket-read timeout in seconds. Defaults to --timeout when unset.",
    )
    parser.add_argument(
        "--user-agent",
        type=str,
        default="nostrax/1.0",
        help="Custom User-Agent string",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )
    parser.add_argument(
        "--no-dedup",
        action="store_true",
        help="Keep duplicate URLs",
    )
    parser.add_argument(
        "--max-concurrent",
        type=int,
        default=10,
        help="Max concurrent HTTP requests during crawling (default: 10)",
    )
    parser.add_argument(
        "--respect-robots",
        action="store_true",
        help="Check robots.txt before crawling pages",
    )
    parser.add_argument(
        "--max-urls",
        type=int,
        default=50000,
        help="Stop crawling after collecting this many URLs (default: 50000)",
    )
    parser.add_argument(
        "--rate-limit",
        type=float,
        default=0,
        help="Minimum seconds between requests per host (default: 0, no limit). "
        "With --proxy-file, enforced per (host, proxy).",
    )
    parser.add_argument(
        "--auto-throttle",
        action="store_true",
        help="Adapt the per-host delay to server latency and back off on "
        "failures (AutoThrottle). --rate-limit is the hard floor.",
    )
    parser.add_argument(
        "--auto-throttle-max-delay",
        type=float,
        default=60.0,
        help="Upper bound on the adaptive delay in seconds (default: 60)",
    )
    parser.add_argument(
        "--proxy",
        type=str,
        default=None,
        help="Proxy URL (e.g. http://proxy:8080)",
    )
    parser.add_argument(
        "--proxy-file",
        type=str,
        default=None,
        help="File of proxy URLs (one per line; # comments ignored) rotated "
        "round-robin per request to spread egress across IPs",
    )
    parser.add_argument(
        "--auth",
        type=str,
        default=None,
        help="HTTP basic auth as user:password",
    )
    parser.add_argument(
        "--sitemap",
        action="store_true",
        help="Also parse sitemap.xml for additional URLs",
    )
    parser.add_argument(
        "--check-status",
        action="store_true",
        help="Check HTTP status code of each discovered URL",
    )
    parser.add_argument(
        "--content",
        action="store_true",
        help="Scrape page metadata (title, description, canonical, language, "
        "Open Graph, JSON-LD) for each crawled page instead of URLs. "
        "Output as plain/json/jsonl/csv.",
    )
    parser.add_argument(
        "--metadata",
        action="store_true",
        help="Include source page, tag type, and depth in output",
    )
    parser.add_argument(
        "--progress",
        action="store_true",
        help="Show a progress bar during crawling (requires tqdm)",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=2,
        help="Number of retry attempts for failed requests (default: 2)",
    )
    parser.add_argument(
        "--scope",
        type=str,
        default=None,
        help="Restrict crawling to a URL path prefix (e.g. /docs/)",
    )
    parser.add_argument(
        "--strategy",
        type=str,
        choices=["dfs", "bfs"],
        default="dfs",
        help="Crawl strategy: dfs (depth-first) or bfs (breadth-first, default: dfs)",
    )
    parser.add_argument(
        "--cache-dir",
        type=str,
        default=None,
        help="Directory to cache crawl state for resume support",
    )
    parser.add_argument(
        "--no-config",
        action="store_true",
        help="Ignore .nostraxrc config file",
    )
    return parser


def _parse_auth(auth_str: str) -> tuple[str, str]:
    """Parse 'user:password' into a tuple."""
    if ":" not in auth_str:
        return (auth_str, "")
    user, _, password = auth_str.partition(":")
    return (user, password)


def _read_list_file(path: str) -> list[str]:
    """Read non-blank, non-comment lines from a file (or stdin when '-').

    One entry per line; blank lines and lines starting with '#' are skipped.
    Used for both the seed list (--input-file) and the proxy pool
    (--proxy-file).
    """
    if path == "-":
        text = sys.stdin.read()
    else:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    entries = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        entries.append(line)
    return entries


# Backwards-compatible alias; seed reading is just line reading.
_read_seeds = _read_list_file


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    # Handle --check-update before requiring --target
    if args.check_update:
        from nostrax.updater import check_update

        print(check_update())
        return 0

    # Load config file (unless --no-config). Config values apply only to
    # flags the user did not pass on argv; CLI wins over config.
    if not args.no_config:
        config = load_config()
        if config:
            provided = user_provided_attrs(parser, argv)
            merge_config(args, config, provided)

    # Assemble the seed list. --target and --input-file may be combined;
    # target (if any) is crawled first. Each seed is validated for SSRF and
    # unsafe seeds are skipped with a warning rather than aborting the run.
    seeds: list[str] = []
    if args.input_file:
        try:
            file_seeds = _read_seeds(args.input_file)
        except OSError as e:
            parser.error(f"--input-file: {e}")
        raw_seeds = ([args.target] if args.target else []) + file_seeds
        for s in raw_seeds:
            err = validate_target_url(s)
            if err:
                logging.getLogger(__name__).warning("Skipping seed %s: %s", s, err)
                continue
            if s not in seeds:
                seeds.append(s)
        if not seeds:
            parser.error("--input-file: no valid seed URLs found")
        if args.cache_dir:
            parser.error("--cache-dir cannot be combined with --input-file")
    else:
        if args.target is None:
            parser.error("the following arguments are required: -t/--target")
        err = validate_target_url(args.target)
        if err:
            parser.error(f"--target: {err}")
        seeds = [args.target]

    # Base URL used for internal/external domain filtering.
    filter_base = args.target or seeds[0]

    # Validate remaining inputs
    if args.proxy:
        err = validate_proxy_url(args.proxy)
        if err:
            parser.error(f"--proxy: {err}")

    # Assemble the proxy pool from --proxy-file (+ --proxy). Invalid proxies
    # are skipped with a warning; the pool is rotated across egress IPs.
    proxies: list[str] = []
    if args.proxy_file:
        try:
            raw_proxies = _read_list_file(args.proxy_file)
        except OSError as e:
            parser.error(f"--proxy-file: {e}")
        for p in ([args.proxy] if args.proxy else []) + raw_proxies:
            perr = validate_proxy_url(p)
            if perr:
                logging.getLogger(__name__).warning("Skipping proxy %s: %s", p, perr)
                continue
            if p not in proxies:
                proxies.append(p)
        if not proxies:
            parser.error("--proxy-file: no valid proxy URLs found")

    if args.auto_throttle_max_delay <= 0:
        parser.error("--auto-throttle-max-delay must be > 0")
    if args.content and args.format in ("html", "dot", "graphml"):
        parser.error("--content supports only plain, json, jsonl, or csv output")
    if args.depth < 0:
        parser.error("--depth must be >= 0")
    if args.timeout <= 0:
        parser.error("--timeout must be > 0")
    if args.max_concurrent <= 0:
        parser.error("--max-concurrent must be > 0")
    if args.max_urls <= 0:
        parser.error("--max-urls must be > 0")
    if args.rate_limit < 0:
        parser.error("--rate-limit must be >= 0")
    if args.retries < 0:
        parser.error("--retries must be >= 0")
    err = validate_header_value(args.user_agent, "--user-agent")
    if err:
        parser.error(err)

    # Set up logging
    level = logging.DEBUG if args.verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(levelname)s: %(message)s",
    )

    # Determine which tags to extract
    if args.all_tags:
        tags = set(TAG_ATTRS.keys())
    elif args.tags:
        tags = {t.strip() for t in args.tags.split(",")}
    else:
        tags = None  # defaults to {"a"}

    # Parse auth
    auth = _parse_auth(args.auth) if args.auth else None

    # Set up progress bar
    progress_callback = None
    pbar = None
    if args.progress and not args.silent:
        try:
            from tqdm import tqdm

            pbar = tqdm(desc="Crawling", unit=" pages", dynamic_ncols=True)

            def progress_callback(pages: int, urls_found: int) -> None:
                pbar.update(1)
                pbar.set_postfix(urls=urls_found)
        except ImportError:
            logging.getLogger(__name__).warning(
                "tqdm not installed, progress bar disabled. Install with: pip install tqdm"
            )

    # Formats that render a whole document (need the UrlResult metadata:
    # the graph formats need each result's source page to build edges).
    document_formats = {"html", "dot", "graphml"}
    need_metadata = args.metadata or args.check_status or args.format in document_formats

    # Crawl. crawl_async keywords are shared between the single-target and
    # multi-seed paths; only the seed source and cache/progress differ.
    crawl_kwargs = dict(
        depth=args.depth,
        tags=tags,
        deduplicate=not args.no_dedup,
        timeout=args.timeout,
        connect_timeout=args.connect_timeout,
        read_timeout=args.read_timeout,
        user_agent=args.user_agent,
        max_concurrent=args.max_concurrent,
        respect_robots=args.respect_robots,
        max_urls=args.max_urls,
        rate_limit=args.rate_limit,
        proxy=args.proxy,
        proxies=proxies or None,
        auto_throttle=args.auto_throttle,
        auto_throttle_max_delay=args.auto_throttle_max_delay,
        auth=auth,
        use_sitemap=args.sitemap,
        include_metadata=need_metadata,
        collect_content=args.content,
        retries=args.retries,
        scope=args.scope,
        strategy=args.strategy,
        check_status=args.check_status,
    )
    try:
        if len(seeds) > 1 or args.input_file:
            results = asyncio.run(
                crawl_seeds_async(seeds, progress_callback=progress_callback, **crawl_kwargs)
            )
        else:
            results = asyncio.run(
                crawl_async(
                    seeds[0],
                    progress_callback=progress_callback,
                    cache_dir=args.cache_dir,
                    **crawl_kwargs,
                )
            )
    except NostraxError as e:
        logging.getLogger(__name__).error("%s", e)
        return 1
    except KeyboardInterrupt:
        # crawl_async's try/finally flushes the visited cache on the way
        # out, so a resume picks up from where we stopped. Exit 130 is
        # the Unix convention for a process terminated by SIGINT.
        logging.getLogger(__name__).warning(
            "Interrupted; partial state saved to cache (if --cache-dir was set)."
        )
        return 130
    finally:
        if pbar is not None:
            pbar.close()

    if not results:
        logging.getLogger(__name__).warning("No URLs found.")
        return 1

    # Content mode returns PageContent; filter by page URL and write via the
    # dedicated content formatter, then we are done.
    if args.content:
        pages = cast("list", results)
        page_urls = [p.url for p in pages]
        page_urls = filter_by_domain(page_urls, filter_base, mode=args.domain)
        if args.protocol:
            protocols = {p.strip() for p in args.protocol.split(",")}
            page_urls = filter_by_protocol(page_urls, protocols)
        if args.pattern:
            page_urls = filter_by_pattern(page_urls, args.pattern)
        if args.exclude:
            page_urls = filter_by_exclude(page_urls, args.exclude)
        kept = set(page_urls)
        pages = [p for p in pages if p.url in kept]
        if args.sort:
            pages.sort(key=lambda p: p.url)
        if not args.silent:
            content_fmt = args.format if args.format in ("json", "jsonl", "csv") else "plain"
            write_content_output(pages, fmt=content_fmt, output_file=args.output)
        return 0

    # Split the crawl output into cleanly-typed views: a UrlResult list when
    # metadata was requested, and a plain URL list for filtering either way.
    if need_metadata:
        meta_results = cast("list[UrlResult]", results)
        url_list: list[str] = [r.url for r in meta_results]
    else:
        meta_results = []
        url_list = cast("list[str]", results)

    # Apply filters
    url_list = filter_by_domain(url_list, filter_base, mode=args.domain)
    if args.protocol:
        protocols = {p.strip() for p in args.protocol.split(",")}
        url_list = filter_by_protocol(url_list, protocols)
    if args.pattern:
        url_list = filter_by_pattern(url_list, args.pattern)
    if args.exclude:
        url_list = filter_by_exclude(url_list, args.exclude)

    # If metadata mode, filter UrlResult list to match filtered URL list
    if need_metadata:
        kept = set(url_list)
        meta_results = [r for r in meta_results if r.url in kept]

    if args.sort:
        if need_metadata:
            meta_results.sort(key=lambda r: r.url)
        else:
            url_list.sort()

    # Status codes are attached by crawl_async (check_status=True) on the
    # same aiohttp session used for the crawl, so we just read them back
    # off the UrlResult objects here.
    statuses: dict[str, int | None] | None = None
    if args.check_status and need_metadata:
        statuses = {r.url: r.status for r in meta_results}

    # Output
    if not args.silent:
        if args.format in document_formats:
            doc_results = meta_results if need_metadata else [UrlResult(url=u) for u in url_list]
            if args.format == "html":
                from nostrax.report import generate_html_report

                content = generate_html_report(
                    doc_results, args.target or ", ".join(seeds), statuses=statuses
                )
            elif args.format == "dot":
                from nostrax.graph import generate_dot

                content = generate_dot(doc_results)
            else:  # graphml
                from nostrax.graph import generate_graphml

                content = generate_graphml(doc_results)

            if not _write_document(content, args.output):
                return 1
        else:
            output_data: list[str] | list[UrlResult] = meta_results if need_metadata else url_list
            write_output(
                output_data,
                fmt=args.format,
                output_file=args.output,
                include_metadata=args.metadata,
                statuses=statuses,
            )

    return 0


def _write_document(content: str, output_file: str | None) -> bool:
    """Write a whole-document format to a file (cwd-confined) or stdout.

    Returns False if a requested file path escapes the working directory.
    """
    if output_file:
        output_path = os.path.realpath(output_file)
        if not is_path_within(output_path, os.getcwd()):
            logging.getLogger(__name__).error(
                "Refusing to write outside working directory: %s", output_file
            )
            return False
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)
    else:
        sys.stdout.write(content)
    return True


if __name__ == "__main__":
    sys.exit(main())
