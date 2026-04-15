<div align="center">

# nostrax

**Fast, async web crawler and URL extraction toolkit for mapping, analyzing, and auditing websites.**

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-2.0.0-orange.svg)](https://github.com/prodrom3/nostrax)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Async](https://img.shields.io/badge/async-aiohttp-blue.svg)](https://docs.aiohttp.org/)
[![Tests](https://img.shields.io/badge/tests-100%2B-brightgreen.svg)](tests/)

<img width="360" src="https://github.com/prodrom3/nostrax/assets/7604466/2872263b-788b-42f4-96d4-7670437b205a">

</div>

---

## Overview

**nostrax** is a production-grade, async web crawler and URL extraction toolkit designed for mapping, analyzing, and auditing websites. Built on `aiohttp` and `lxml`, it combines high-throughput concurrent crawling with security-hardened input handling to serve SEO, QA, security research, and infrastructure auditing workflows.

The name derives from "Nostos" - the Greek concept of a heroic return journey - reflecting the tool's purpose of mapping the digital landscape.

## Table of Contents

- [Why nostrax](#why-nostrax)
- [Features](#features)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Common Workflows](#common-workflows)
- [Configuration](#configuration)
- [Python API](#python-api)
- [CLI Reference](#cli-reference)
- [Architecture](#architecture)
- [Security](#security)
- [Development](#development)
- [License](#license)

## Why nostrax

| Need | Solution |
|---|---|
| Crawl a large site quickly | Async I/O with connection pooling and DNS caching |
| Audit for broken links | `--check-status` reports HTTP status codes for every URL |
| Map a specific section of a site | `--scope` restricts crawling to a URL path prefix |
| Resume interrupted crawls | `--cache-dir` persists state to disk |
| Comply with robots.txt | `--respect-robots` with a standards-compliant parser |
| Respect rate limits | `--rate-limit` enforces minimum delay between requests |
| Integrate with CI/CD | JSON/CSV output, exit codes, silent mode |
| Generate stakeholder reports | Self-contained HTML reports with filterable tables |
| Crawl behind a proxy | Proxy and HTTP basic auth support |

## Features

### Crawling Engine

- **Async I/O** via `aiohttp` with shared session, connection pooling, and DNS caching
- **DFS and BFS** traversal strategies
- **Exponential backoff retry** for transient network failures
- **Content-Type aware** - skips non-HTML responses before downloading
- **Response size limits** prevent memory exhaustion (default 10 MB)
- **Rate limiting** with configurable per-request delay
- **robots.txt support** with standards-compliant URL matching
- **Scope control** to restrict crawling to a URL path prefix
- **Resume from disk** via on-disk cache of visited URLs and results

### Extraction

- URL extraction from `<a>`, `<img>`, `<script>`, `<link>`, `<form>`, `<iframe>`, `<video>`, `<audio>`, and `<source>` tags
- **lxml C-based parser** with `SoupStrainer` for targeted parsing
- **URL normalization** - strips fragments, trailing slashes, sorts query params, lowercases host
- **Credential stripping** prevents leaking userinfo in output
- **Sitemap.xml parsing** with sitemap index support and XXE protection

### Filtering and Output

- Filter by domain (internal / external / all), protocol, regex include, regex exclude
- Output formats: plain, JSON, CSV, self-contained HTML report
- Rich metadata per URL: source page, tag type, depth, response time
- Deduplication and sorting
- File output with path traversal protection

### Operations

- HTTP basic authentication
- HTTP, HTTPS, SOCKS4, SOCKS5 proxy support
- **Broken link checker** via concurrent HEAD requests
- **Progress bar** via optional `tqdm` dependency
- **Config file** via `.nostraxrc` (TOML format)
- **PyPI version check** via `--check-update`

## Installation

Install from source:

```bash
git clone https://github.com/prodrom3/nostrax.git
cd nostrax
pip install .
```

With optional dependencies:

```bash
pip install "nostrax[progress]"      # Progress bar support
pip install -e ".[dev]"              # Development and testing
```

Requires Python 3.10 or newer.

## Quick Start

Extract all links from a single page:

```bash
nostrax -t https://example.com
```

Crawl internal links two levels deep and save to JSON:

```bash
nostrax -t https://example.com -d 2 --domain internal -f json -o results.json
```

Audit a site for broken links and generate an HTML report:

```bash
nostrax -t https://example.com -d 1 --check-status -f html -o audit.html
```

## Common Workflows

### SEO / Content Audit

Crawl internal links with a sitemap seed, sorted, with response timings:

```bash
nostrax -t https://example.com -d 3 \
  --domain internal --sitemap \
  --metadata --sort \
  -f html -o audit.html
```

### Broken Link Detection

Check every discovered URL's HTTP status:

```bash
nostrax -t https://example.com -d 2 --check-status -f json -o links.json
```

### Polite Crawling

Rate-limited, robots-respecting crawl suitable for production targets:

```bash
nostrax -t https://example.com -d 3 \
  --rate-limit 1.0 --retries 3 \
  --respect-robots \
  --user-agent "MyBot/1.0 (+https://mysite.com/bot)"
```

### Documentation Coverage

Crawl only the `/docs/` section of a site using BFS:

```bash
nostrax -t https://example.com -d 5 \
  --strategy bfs --scope /docs/ \
  -f csv -o docs-coverage.csv
```

### Resumable Large Crawl

Save state to disk so interrupted crawls can resume:

```bash
nostrax -t https://example.com -d 5 --cache-dir .crawl_cache
# If interrupted (Ctrl+C, crash, timeout), re-run the same command to resume.
```

### Behind a Corporate Proxy

```bash
nostrax -t https://internal.example.com \
  --proxy http://corporate-proxy:8080 \
  --auth username:password
```

### Asset Discovery

Extract all static assets, excluding images:

```bash
nostrax -t https://example.com --all-tags --exclude "\.(jpg|png|gif|svg)$"
```

## Configuration

Persist common options in `.nostraxrc` (TOML format) in the current directory or home folder. CLI arguments override config values.

```toml
# .nostraxrc
depth = 2
rate_limit = 0.5
respect_robots = true
user_agent = "mybot/1.0"
max_concurrent = 20
scope = "/docs/"
retries = 3
```

Bypass the config file with `--no-config`.

## Python API

### Basic crawl

```python
from nostrax import crawl

urls = crawl("https://example.com", depth=1)
```

### Crawl with metadata

```python
from nostrax import crawl

results = crawl("https://example.com", depth=1, include_metadata=True)
for r in results:
    time_str = f"{r.response_time:.0f}ms" if r.response_time else "n/a"
    print(f"{r.url} ({time_str}, from {r.source}, tag={r.tag})")
```

### Advanced: BFS crawl with resume

```python
from nostrax import crawl

urls = crawl(
    "https://example.com",
    depth=3,
    strategy="bfs",
    scope="/docs/",
    cache_dir=".crawl_cache",
    respect_robots=True,
    rate_limit=0.5,
)
```

### Async usage

```python
import asyncio
from nostrax import crawl_async

urls = asyncio.run(crawl_async(
    "https://example.com",
    depth=2,
    max_concurrent=20,
    rate_limit=0.5,
    retries=3,
    respect_robots=True,
))
```

### URL normalization

```python
from nostrax import normalize_url

assert normalize_url("https://Example.COM/page/") == "https://example.com/page"
assert normalize_url("https://example.com/page#top") == "https://example.com/page"
assert normalize_url("https://user:pass@example.com/") == "https://example.com/"
```

### Exception handling

```python
from nostrax import crawl, NostraxError

try:
    urls = crawl("https://example.com")
except NostraxError as e:
    print(f"Crawl failed: {e}")
```

## CLI Reference

```
usage: nostrax [-h] [-V] [--check-update] -t TARGET [-s] [-d DEPTH]
               [--all-tags] [--tags TAGS] [--domain {all,internal,external}]
               [--protocol PROTOCOL] [--pattern PATTERN] [--exclude EXCLUDE]
               [--sort] [-f {plain,json,csv,html}] [-o OUTPUT]
               [--timeout TIMEOUT] [--user-agent USER_AGENT] [-v] [--no-dedup]
               [--max-concurrent N] [--respect-robots] [--max-urls N]
               [--rate-limit SECS] [--proxy URL] [--auth USER:PASS]
               [--sitemap] [--check-status] [--metadata] [--progress]
               [--retries N] [--scope PATH] [--strategy {dfs,bfs}]
               [--cache-dir DIR] [--no-config]
```

### Options

| Flag | Description |
|---|---|
| `-V, --version` | Show version and exit |
| `--check-update` | Check PyPI for a newer version and exit |
| `-t, --target` | Target URL to extract from (required) |
| `-s, --silent` | Suppress all output (exit code only) |
| `-d, --depth` | Recursion depth for crawling (default: 0) |
| `--all-tags` | Extract URLs from all supported tags |
| `--tags` | Comma-separated list of HTML tags to extract from |
| `--domain` | Filter by domain: `all`, `internal`, or `external` |
| `--protocol` | Comma-separated protocols to keep |
| `--pattern` | Regex pattern to filter URLs (keep matches) |
| `--exclude` | Regex pattern to exclude URLs (remove matches) |
| `--sort` | Sort URLs alphabetically |
| `-f, --format` | Output format: `plain`, `json`, `csv`, or `html` |
| `-o, --output` | Write output to file instead of stdout |
| `--timeout` | Request timeout in seconds (default: 10) |
| `--user-agent` | Custom User-Agent string |
| `-v, --verbose` | Enable verbose logging |
| `--no-dedup` | Keep duplicate URLs |
| `--max-concurrent` | Max concurrent HTTP requests (default: 10) |
| `--respect-robots` | Check robots.txt before crawling |
| `--max-urls` | Stop crawling after this many URLs (default: 50000) |
| `--rate-limit` | Minimum seconds between requests (default: 0) |
| `--proxy` | Proxy URL (`http`, `https`, `socks4`, `socks5`) |
| `--auth` | HTTP basic auth as `user:password` |
| `--sitemap` | Also parse `sitemap.xml` for additional URLs |
| `--check-status` | Check HTTP status code of each discovered URL |
| `--metadata` | Include source page, tag type, and depth in output |
| `--progress` | Show a progress bar (requires `tqdm`) |
| `--retries` | Retry attempts for failed requests (default: 2) |
| `--scope` | Restrict crawling to a URL path prefix |
| `--strategy` | Crawl strategy: `dfs` or `bfs` (default: dfs) |
| `--cache-dir` | Directory to cache crawl state for resume support |
| `--no-config` | Ignore `.nostraxrc` config file |

### Output example

JSON output with `--metadata`:

```json
[
  {
    "url": "https://example.com/about",
    "source": "https://example.com",
    "tag": "a",
    "depth": 0,
    "response_time_ms": 142.3
  }
]
```

## Architecture

```mermaid
flowchart TD
    CLI["cli.py<br/>argparse + validation + config merge"]
    Crawler["crawler.py<br/>async DFS / BFS"]
    Post["filters / normalize / output<br/>post-processing"]

    Fetch["fetch_page"]
    Extract["extract_urls<br/>lxml + SoupStrainer"]
    Robots["robots.py"]
    Cache["cache.py"]
    Sitemap["sitemap.py"]
    Status["status.py"]

    Filters["domain / protocol<br/>regex / dedup"]
    Output["plain / json<br/>csv / html"]

    CLI --> Crawler
    CLI --> Post

    Crawler --> Fetch
    Crawler --> Extract
    Crawler --> Robots
    Crawler --> Cache
    Crawler --> Sitemap
    Crawler --> Status

    Post --> Filters
    Post --> Output
```

### Package layout

| Module | Purpose |
|---|---|
| `nostrax.cli` | Command-line interface, argument parsing, input validation |
| `nostrax.crawler` | Async recursive crawler (DFS / BFS) |
| `nostrax.extractor` | HTML parsing and URL extraction (lxml + SoupStrainer) |
| `nostrax.filters` | Domain, protocol, and regex filters |
| `nostrax.output` | Output formatting (plain, JSON, CSV) |
| `nostrax.report` | HTML report generation |
| `nostrax.models` | `UrlResult` dataclass |
| `nostrax.normalize` | URL normalization |
| `nostrax.sitemap` | `sitemap.xml` parser with XXE protection |
| `nostrax.status` | Async HTTP status checker |
| `nostrax.robots` | `robots.txt` compliance |
| `nostrax.cache` | On-disk crawl cache for resume |
| `nostrax.config` | `.nostraxrc` loader |
| `nostrax.validation` | Input validation (SSRF, bounds, headers) |
| `nostrax.updater` | PyPI version check |
| `nostrax.exceptions` | Custom exception hierarchy |

## Security

nostrax is hardened against common web-scraping attack vectors:

- **SSRF prevention** - target URL validation rejects `file://`, private IPs, loopback, localhost, and cloud metadata endpoints (169.254.169.254)
- **XXE prevention** - sitemap parser rejects XML with `<!DOCTYPE>` or `<!ENTITY>` declarations
- **Sitemap loop protection** - max recursion depth of 5 with cycle detection
- **Path traversal prevention** - cache and output files restricted to the working directory
- **Header injection prevention** - User-Agent validated for newlines and length
- **Open redirect prevention** - redirects disabled on all HTTP requests
- **ReDoS mitigation** - regex patterns validated, catastrophic backtracking caught
- **Response size limits** - default 10 MB cap prevents memory exhaustion
- **Credential scrubbing** - userinfo stripped from normalized URLs

To report a security vulnerability, please open a private security advisory on GitHub.

## Development

### Run tests

```bash
pip install -e ".[dev]"
pytest
pytest --cov=nostrax              # With coverage
pytest tests/test_crawler.py      # Single module
```

### Code style

```bash
black nostrax tests               # Format
```

### Contributing

Contributions are welcome. Please:

1. Fork the repository
2. Create a feature branch (`feature/my-feature`)
3. Add tests for your changes
4. Ensure `pytest` passes
5. Submit a pull request

Follow [Conventional Commits](https://www.conventionalcommits.org/) for commit messages: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`.

## Author

Created by [**prodrom3**](https://github.com/prodrom3) at [**radamic**](https://github.com/radamic).

## License

Released under the [MIT License](LICENSE).

## Acknowledgments

Built on the work of the open-source community, particularly `aiohttp`, `beautifulsoup4`, and `lxml`.
