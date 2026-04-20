"""Command-line interface for nostrax.

Copyright (c) 2024 prodrom3 / radamic
Licensed under the MIT License.
"""

import argparse
import asyncio
import logging
import os
import sys

from nostrax import __version__
from nostrax.config import load_config, merge_config, user_provided_attrs
from nostrax.crawler import crawl_async
from nostrax.exceptions import NostraxError
from nostrax.extractor import TAG_ATTRS
from nostrax.validation import (
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
from nostrax.output import write_output


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nostrax",
        description="Extract URLs and paths from web pages.",
    )
    parser.add_argument(
        "-V", "--version",
        action="version",
        version=f"nostrax {__version__}",
    )
    parser.add_argument(
        "--check-update",
        action="store_true",
        help="Check PyPI for a newer version and exit",
    )
    parser.add_argument(
        "-t", "--target",
        type=str,
        default=None,
        help="Target URL to extract from",
    )
    parser.add_argument(
        "-s", "--silent",
        action="store_true",
        help="Suppress all output (exit code only)",
    )
    parser.add_argument(
        "-d", "--depth",
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
        "-f", "--format",
        type=str,
        choices=["plain", "json", "csv", "html"],
        default="plain",
        help="Output format (default: plain)",
    )
    parser.add_argument(
        "-o", "--output",
        type=str,
        default=None,
        help="Write output to file instead of stdout",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=10,
        help="Request timeout in seconds (default: 10)",
    )
    parser.add_argument(
        "--user-agent",
        type=str,
        default="nostrax/1.0",
        help="Custom User-Agent string",
    )
    parser.add_argument(
        "-v", "--verbose",
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
        help="Minimum seconds between requests (default: 0, no limit)",
    )
    parser.add_argument(
        "--proxy",
        type=str,
        default=None,
        help="Proxy URL (e.g. http://proxy:8080)",
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

    if args.target is None:
        parser.error("the following arguments are required: -t/--target")

    # Validate inputs
    err = validate_target_url(args.target)
    if err:
        parser.error(f"--target: {err}")
    if args.proxy:
        err = validate_proxy_url(args.proxy)
        if err:
            parser.error(f"--proxy: {err}")
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

    # Whether we need metadata from the crawler
    need_metadata = args.metadata or args.check_status or args.format == "html"

    # Crawl
    try:
        results = asyncio.run(
            crawl_async(
                args.target,
                depth=args.depth,
                tags=tags,
                deduplicate=not args.no_dedup,
                timeout=args.timeout,
                user_agent=args.user_agent,
                max_concurrent=args.max_concurrent,
                respect_robots=args.respect_robots,
                max_urls=args.max_urls,
                rate_limit=args.rate_limit,
                proxy=args.proxy,
                auth=auth,
                use_sitemap=args.sitemap,
                include_metadata=need_metadata,
                progress_callback=progress_callback,
                retries=args.retries,
                scope=args.scope,
                strategy=args.strategy,
                cache_dir=args.cache_dir,
            )
        )
    except NostraxError as e:
        logging.getLogger(__name__).error("%s", e)
        return 1
    finally:
        if pbar is not None:
            pbar.close()

    if not results:
        logging.getLogger(__name__).warning("No URLs found.")
        return 1

    # Extract plain URL list for filtering
    if need_metadata:
        url_list = [r.url for r in results]
    else:
        url_list = results

    # Apply filters
    url_list = filter_by_domain(url_list, args.target, mode=args.domain)
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
        results = [r for r in results if r.url in kept]

    if args.sort:
        if need_metadata:
            results.sort(key=lambda r: r.url)
        else:
            url_list.sort()

    # Check HTTP status codes
    statuses = None
    if args.check_status:
        from nostrax.status import check_statuses

        final_urls = [r.url for r in results] if need_metadata else url_list

        if not args.silent:
            sys.stderr.write(f"Checking status of {len(final_urls)} URLs...\n")

        statuses = asyncio.run(
            check_statuses(
                final_urls,
                timeout=args.timeout,
                max_concurrent=args.max_concurrent,
                user_agent=args.user_agent,
                auth=__import__("aiohttp").BasicAuth(auth[0], auth[1]) if auth else None,
                proxy=args.proxy,
            )
        )

    # Output
    if not args.silent:
        if args.format == "html":
            from nostrax.report import generate_html_report

            html_results = results if need_metadata else [UrlResult(url=u) for u in url_list]
            html_content = generate_html_report(html_results, args.target, statuses=statuses)

            if args.output:
                output_path = os.path.realpath(args.output)
                cwd = os.path.realpath(os.getcwd())
                if not output_path.startswith(cwd + os.sep) and output_path != cwd:
                    logging.getLogger(__name__).error(
                        "Refusing to write outside working directory: %s", args.output
                    )
                    return 1
                with open(output_path, "w", encoding="utf-8") as f:
                    f.write(html_content)
            else:
                sys.stdout.write(html_content)
        else:
            output_data = results if need_metadata else url_list
            write_output(
                output_data,
                fmt=args.format,
                output_file=args.output,
                include_metadata=args.metadata,
                statuses=statuses,
            )

    return 0


if __name__ == "__main__":
    sys.exit(main())
