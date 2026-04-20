<div align="center">

# nostrax

**Fast, async web crawler and URL extraction toolkit for mapping, analyzing, and auditing websites.**

[![CI](https://github.com/prodrom3/nostrax/actions/workflows/test.yml/badge.svg?branch=main)](https://github.com/prodrom3/nostrax/actions/workflows/test.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-2.0.0-orange.svg)](https://github.com/prodrom3/nostrax)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Async](https://img.shields.io/badge/async-aiohttp-blue.svg)](https://docs.aiohttp.org/)
[![Tests](https://img.shields.io/badge/tests-200%2B-brightgreen.svg)](tests/)
[![SemVer](https://img.shields.io/badge/semver-2.0.0-blue.svg)](https://semver.org/)

<img width="360" src="https://github.com/prodrom3/nostrax/assets/7604466/2872263b-788b-42f4-96d4-7670437b205a">

</div>

---

## Overview

**nostrax** is a production-grade, async web crawler and URL extraction toolkit for mapping, analyzing, and auditing websites at scale. Built on `aiohttp` and `lxml`, it pairs high-throughput concurrent crawling with security-hardened input handling for SEO, QA, security research, and infrastructure audit workflows in regulated environments.

It is designed to be embedded in CI pipelines, scheduled jobs, and internal tooling - with deterministic exit codes, structured output, standards-based logging, zero telemetry, and no outbound calls beyond the sites you explicitly target.

The name derives from "Nostos" - the Greek concept of a heroic return journey - reflecting the tool's purpose of mapping the digital landscape.

## Table of Contents

- [Why nostrax](#why-nostrax)
- [Features](#features)
- [Compatibility](#compatibility)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Common Workflows](#common-workflows)
- [Configuration](#configuration)
- [Python API](#python-api)
- [CLI Reference](#cli-reference)
- [Exit Codes](#exit-codes)
- [Observability](#observability)
- [Architecture](#architecture)
- [Security](#security)
- [Versioning and Stability](#versioning-and-stability)
- [Support](#support)
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
- **Unified DFS / BFS engine** sharing a bounded frontier and a worker pool, so `--strategy bfs` runs at the same concurrency as `--strategy dfs`
- **Full-jitter retry** for transient network failures, avoiding lockstep retry storms
- **Separated timeouts**: total, connect, and per-read budgets can be set independently
- **Content-Type aware** - skips non-HTML responses before downloading
- **Response size limits** prevent memory exhaustion (default 10 MB for pages, 1 MiB for robots.txt, 50 MiB for sitemaps)
- **Per-host rate limiting**: `--rate-limit` applies to each netloc independently, not globally
- **robots.txt support** with standards-compliant URL matching and redirects disabled
- **Scope control** to restrict crawling to a URL path prefix
- **Resume from disk** via on-disk cache with atomic rewrites of the visited set and a kept-open append handle for results
- **Graceful shutdown**: `SIGINT` (Ctrl+C) flushes the cache before exiting with code 130

### Extraction

- URL extraction from `<a>`, `<img>`, `<script>`, `<link>`, `<form>`, `<iframe>`, `<video>`, `<audio>`, `<source>`, and `<meta http-equiv="refresh">` tags
- **`<img srcset>` and `<source srcset>`** are fully unpacked (every candidate URL is emitted)
- **`<base href>` is honoured** when resolving relative URLs on the page
- **lxml C-based parser** with `SoupStrainer` for targeted parsing
- **URL normalization** - strips fragments, trailing slashes, sorts query params, lowercases host
- **Credential stripping** prevents leaking userinfo in output
- **Sitemap.xml parsing** with sitemap index support, through `defusedxml` to refuse XML-bomb / external-DTD payloads at parse time

### Filtering and Output

- Filter by domain (internal / external / all), protocol, regex include, regex exclude
- `--pattern` / `--exclude` regexes run through the `regex` package with a per-URL timeout, bounding worst-case ReDoS exposure
- Output formats: plain, JSON, CSV, self-contained HTML report
- Rich metadata per URL: source page, tag type, depth, response time, status
- Deduplication and sorting
- File output with path traversal protection

### Operations

- HTTP basic authentication
- HTTP, HTTPS, SOCKS4, SOCKS5 proxy support, **credentials redacted from logs**
- **Broken link checker** via concurrent HEAD requests on the same aiohttp session the crawl used (one DNS/TLS handshake per host, not two)
- **Progress bar** via optional `tqdm` dependency
- **Config file** via `.nostraxrc` (TOML format)
- **PyPI version check** via `--check-update`

## Compatibility

| Component | Supported |
|---|---|
| Python | 3.10, 3.11, 3.12, 3.13 |
| Operating systems | Linux, macOS, Windows |
| Architectures | x86_64, arm64 |
| Runtime dependencies | `aiohttp >= 3.9`, `beautifulsoup4 >= 4.12`, `lxml >= 5.0` |
| Optional dependencies | `tqdm >= 4.60` (progress bar) |
| Network | Outbound HTTP/HTTPS to target hosts; HTTP/HTTPS/SOCKS4/SOCKS5 proxy support |
| Packaging | PEP 517 / PEP 621 (`pyproject.toml`), installs via `pip` or any PEP 517 frontend |

No telemetry is collected. The process makes no network calls to third parties beyond the target host(s) and, when explicitly requested, a single PyPI lookup via `--check-update`.

## Installation

nostrax is not yet published to PyPI, so `pip install nostrax` and `pipx install nostrax` will not resolve. Install from source or directly from the Git repository using either `pip` (library or CLI) or `pipx` (isolated CLI).

### With pipx (recommended for CLI use)

`pipx` installs the `nostrax` command into an isolated virtual environment and puts it on your PATH, without polluting your system or project Python.

```bash
# from a local clone
git clone https://github.com/prodrom3/nostrax.git
cd nostrax
pipx install .

# or directly from GitHub
pipx install git+https://github.com/prodrom3/nostrax.git

# with the progress bar extra
pipx install "git+https://github.com/prodrom3/nostrax.git#egg=nostrax[progress]"

# upgrade later
pipx upgrade nostrax

# uninstall
pipx uninstall nostrax
```

### With pip (for embedding as a library)

```bash
git clone https://github.com/prodrom3/nostrax.git
cd nostrax
pip install .                        # library + CLI
pip install ".[progress]"            # with progress bar support
pip install -e ".[dev]"              # editable, with test tooling
```

Or directly from GitHub:

```bash
pip install "git+https://github.com/prodrom3/nostrax.git"
pip install "git+https://github.com/prodrom3/nostrax.git@v2.0.0"   # pin to a tag
```

### Verify the install

```bash
nostrax --version
nostrax --check-update
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
    # Raised when the starting URL could not be fetched
    # (network error, robots block, content-type mismatch, etc.)
    print(f"Crawl failed: {e}")
```

### Observability hooks

`crawl` and `crawl_async` accept a `metrics=` argument implementing the
`MetricsSink` Protocol. Pair this with your Prometheus / OpenTelemetry
/ Datadog client to stream crawl events:

```python
from nostrax import crawl
from nostrax.metrics import MetricsSink


class PrometheusSink:
    def on_page_fetched(self, url, depth, elapsed_ms, urls_found):
        PAGES_FETCHED.inc()
        FETCH_LATENCY_MS.observe(elapsed_ms)

    def on_fetch_failed(self, url, depth):
        PAGES_FAILED.inc()

    def on_robots_blocked(self, url):
        ROBOTS_BLOCKED.inc()


crawl("https://example.com", depth=2, metrics=PrometheusSink())
```

Sink methods are called synchronously on the event-loop thread, so
implementations must be cheap. Exceptions raised by a sink are
isolated: they are logged as warnings and do not abort the crawl.

### Pluggable fetcher and extractor

For Playwright-rendered pages, custom authentication flows, or a
caching fetcher, pass any callable that matches the `Fetcher` or
`Extractor` Protocol:

```python
from nostrax import crawl
from nostrax.protocols import Fetcher


async def playwright_fetcher(session, url, *, timeout, max_response_size,
                              retries, proxy, connect_timeout, read_timeout):
    # Render JS, return (html, elapsed_ms) or (None, elapsed_ms) on failure
    ...


urls = crawl("https://example.com", fetcher=playwright_fetcher)
```

## CLI Reference

```
usage: nostrax [-h] [-V] [--check-update] -t TARGET [-s] [-d DEPTH]
               [--all-tags] [--tags TAGS] [--domain {all,internal,external}]
               [--protocol PROTOCOL] [--pattern PATTERN] [--exclude EXCLUDE]
               [--sort] [-f {plain,json,csv,html}] [-o OUTPUT]
               [--timeout TIMEOUT] [--connect-timeout SECS] [--read-timeout SECS]
               [--user-agent USER_AGENT] [-v] [--no-dedup]
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
| `--timeout` | Total request timeout in seconds (default: 10) |
| `--connect-timeout` | Per-connection timeout in seconds (defaults to `--timeout`) |
| `--read-timeout` | Per-socket-read timeout in seconds (defaults to `--timeout`) |
| `--user-agent` | Custom User-Agent string |
| `-v, --verbose` | Enable verbose logging |
| `--no-dedup` | Keep duplicate URLs |
| `--max-concurrent` | Max concurrent HTTP requests (default: 10) |
| `--respect-robots` | Check robots.txt before crawling |
| `--max-urls` | Stop crawling after this many URLs (default: 50000) |
| `--rate-limit` | Minimum seconds between requests **per host** (default: 0) |
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

## Exit Codes

nostrax returns deterministic exit codes suitable for CI gates and orchestration:

| Code | Meaning |
|---|---|
| `0` | Success - crawl completed and output was produced |
| `1` | Failure - invalid input, network error, write failure, or no URLs discovered |
| `2` | Argument parsing error (`argparse` default) |

Combine with `--silent` to suppress stdout and rely on the exit code alone in pipelines.

## Observability

nostrax uses Python's standard `logging` module with module-level loggers under the `nostrax.*` namespace. No logging is configured by default when used as a library - callers control destinations, format, and levels.

```python
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logging.getLogger("nostrax").setLevel(logging.DEBUG)
```

From the CLI, use `-v` / `--verbose` to raise the default log level to `DEBUG`. Loggers are namespaced by module (`nostrax.crawler`, `nostrax.robots`, `nostrax.validation`, etc.) so operators can filter or route per-subsystem to JSON log aggregators, SIEM pipelines, or structured log processors of their choice.

## Architecture

```mermaid
flowchart TD
    CLI["cli.py<br/>argparse + validation + config merge"]
    Crawler["crawler.py<br/>unified frontier + worker pool"]
    Post["filters / normalize / output<br/>post-processing"]

    Frontier["LifoQueue (DFS) / Queue (BFS)<br/>bounded at max_urls * 2"]
    RateLimiter["PerHostRateLimiter<br/>per-netloc serialisation"]
    Fetcher["Fetcher protocol<br/>default: fetch_page"]
    Extractor["Extractor protocol<br/>default: extract_urls"]
    Robots["robots.py"]
    Cache["cache.py<br/>atomic visited + kept-open results"]
    Sitemap["sitemap.py<br/>defusedxml"]
    Status["status.py<br/>same aiohttp session"]

    Connector["aiohttp TCPConnector"]
    Resolver["SafeResolver<br/>re-applies SSRF classifier"]
    Metrics["MetricsSink<br/>on_page_fetched / failed / robots_blocked"]

    Filters["filter_by_domain / protocol<br/>regex with per-URL timeout"]
    Output["plain / json<br/>csv / html"]

    CLI --> Crawler
    CLI --> Post

    Crawler --> Frontier
    Crawler --> RateLimiter
    Crawler --> Fetcher
    Crawler --> Extractor
    Crawler --> Robots
    Crawler --> Cache
    Crawler --> Sitemap
    Crawler --> Status
    Crawler --> Metrics

    Fetcher --> Connector
    Status --> Connector
    Connector --> Resolver

    Post --> Filters
    Post --> Output
```

### Package layout

| Module | Purpose |
|---|---|
| `nostrax.cli` | Command-line interface, argument parsing, input validation |
| `nostrax.crawler` | Unified async crawl engine (frontier + worker pool), `PerHostRateLimiter` |
| `nostrax.extractor` | HTML parsing and URL extraction (lxml + SoupStrainer, `<base>`, `srcset`, meta-refresh) |
| `nostrax.filters` | Domain, protocol, and `regex`-backed timeout-bounded filters |
| `nostrax.output` | Output formatting (plain, JSON, CSV) |
| `nostrax.report` | HTML report generation |
| `nostrax.models` | `UrlResult` dataclass |
| `nostrax.normalize` | URL normalization |
| `nostrax.sitemap` | `sitemap.xml` parser through `defusedxml` |
| `nostrax.status` | Async HTTP status checker |
| `nostrax.robots` | `robots.txt` compliance |
| `nostrax.cache` | On-disk crawl cache with atomic visited save + kept-open results handle |
| `nostrax.config` | `.nostraxrc` loader |
| `nostrax.validation` | Input validation (SSRF classifier, bounds, headers, credential redaction) |
| `nostrax.resolver` | `SafeResolver` for aiohttp, applies the SSRF classifier to every DNS resolution |
| `nostrax.metrics` | `MetricsSink` protocol and `NullMetricsSink` default |
| `nostrax.protocols` | `Fetcher` and `Extractor` protocols for extensibility |
| `nostrax.updater` | PyPI version check |
| `nostrax.exceptions` | Custom exception hierarchy |

## Security

nostrax is hardened by default against common attack vectors in crawler and scraper tooling. Defenses are implemented as non-optional controls inside `nostrax.validation`, `nostrax.sitemap`, `nostrax.normalize`, and the request layer - they are not opt-in flags.

### Security controls

| Control | Mitigation |
|---|---|
| **SSRF prevention** | Target URL validation rejects `file://`, private IPs (RFC 1918), loopback, link-local, multicast, reserved, unspecified, IPv4-mapped IPv6 variants of the above, and cloud metadata endpoints (169.254.169.254). Domain-name targets are resolved via `socket.getaddrinfo` and every returned address is run through the same unsafe-IP classifier. A custom aiohttp resolver re-applies the classifier at connection time, so every DNS resolution during the crawl is re-validated and a TTL=0 DNS rebinding attack that flips the authoritative record between CLI validation and fetch cannot slip past the filter. |
| **XXE prevention** | Sitemap XML is parsed through `defusedxml`, which refuses `<!DOCTYPE>`, `<!ENTITY>`, external DTDs, and classic billion-laughs / entity-expansion payloads at parse time. A redundant string-level DOCTYPE/ENTITY rejection is kept as belt-and-suspenders in case the library is ever swapped or downgraded. |
| **Sitemap loop protection** | Max recursion depth of 5 with cycle detection on sitemap indexes |
| **Path traversal prevention** | Cache and output file paths are restricted to the working directory |
| **Header injection prevention** | `User-Agent` values are validated for CR/LF and length bounds |
| **Open redirect prevention** | HTTP redirect following is disabled on all fetches |
| **ReDoS mitigation** | User-supplied `--pattern` and `--exclude` regexes are parsed and matched via the `regex` package, whose engine is largely immune to catastrophic backtracking out of the box. Each per-URL match is additionally wrapped in a 0.5 s budget; if it expires the URL is skipped with a warning rather than allowed to consume the crawl. |
| **Response size limits** | Default 10 MB per-response cap prevents memory exhaustion |
| **Credential scrubbing** | `userinfo` (`user:pass@`) components are stripped during URL normalization |
| **Content-Type gating** | Non-HTML responses are skipped before download where possible |

### Supply chain

- All runtime dependencies are published, pinned-by-floor packages: `aiohttp`, `beautifulsoup4`, `defusedxml`, `lxml`, `packaging`, plus `tomli` on Python 3.10 (stdlib `tomllib` on 3.11+).
- No runtime code execution of scraped content - HTML is parsed, never rendered in a JavaScript engine.
- No outbound telemetry. The only optional outbound call outside of targets is `--check-update`, which queries PyPI on explicit user request.

### Responsible disclosure

See [SECURITY.md](SECURITY.md) for the full vulnerability reporting
policy. In short: do **not** file public issues for suspected
vulnerabilities; open a private GitHub security advisory or contact
the maintainers privately. Acknowledgement within 5 business days;
triage and remediation plan within 10.

## Versioning and Stability

nostrax follows [Semantic Versioning 2.0.0](https://semver.org/).

- **Major** (`X.0.0`) - backwards-incompatible changes to the public Python API (`nostrax.crawl`, `nostrax.crawl_async`, `nostrax.extract_urls`, `nostrax.normalize_url`, `nostrax.UrlResult`, `nostrax.NostraxError`) or to documented CLI flags and output schemas.
- **Minor** (`2.X.0`) - additive changes: new flags, new fields in structured output (JSON/CSV additive only), new optional parameters with safe defaults.
- **Patch** (`2.0.X`) - bug fixes, security fixes, documentation, dependency floor bumps that do not change behaviour.

The public surface is the symbols exported from `nostrax.__init__` and the CLI flags documented in this README. Anything under `nostrax._*` or any module not re-exported from the top-level package is considered internal and may change without notice.

Security-only patch releases are issued out-of-band for confirmed vulnerabilities with the corresponding advisory.

Per-release changes are tracked in [CHANGELOG.md](CHANGELOG.md).

## Support

| Channel | Purpose |
|---|---|
| [GitHub Issues](https://github.com/prodrom3/nostrax/issues) | Bug reports, feature requests, usage questions |
| [GitHub Discussions](https://github.com/prodrom3/nostrax/discussions) | Design discussion, Q&A, community workflows |
| [Security advisories](https://github.com/prodrom3/nostrax/security/advisories) | Private disclosure of suspected vulnerabilities |
| [Releases](https://github.com/prodrom3/nostrax/releases) | Release notes, changelog, upgrade guidance |

This project is maintained on a best-effort basis by the authors and community contributors under the MIT License. No commercial SLA is offered through this repository; organisations requiring a formal support arrangement should contact the maintainers directly.

## Development

### Run tests

```bash
pip install -e ".[dev]"
pytest                            # 150+ tests across 16 modules
pytest --cov=nostrax              # With coverage
pytest tests/test_crawler.py      # Single module
```

Tests use `pytest`, `pytest-asyncio`, `pytest-cov`, and `aioresponses` - all declared in the `dev` optional dependency group. The suite covers crawling, extraction, filtering, normalization, sitemap parsing, robots compliance, cache resume, CLI argument parsing, input validation (SSRF, path traversal, header injection, ReDoS), and output formatting.

### Code style

```bash
black nostrax tests               # Format
```

### Contributing

Contributions are welcome. Please:

1. Fork the repository and create a feature branch (`feature/my-feature`).
2. Add or update tests for your change - new code is expected to keep coverage steady or improve it.
3. Run `pytest` and `black nostrax tests` before opening a pull request.
4. Keep commits focused; prefer small, reviewable PRs over large ones.
5. Sign off or otherwise indicate you have the right to contribute the code under the MIT License.

Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/): `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`, `perf:`, `ci:`.

## Author

Created by [**prodrom3**](https://github.com/prodrom3) at [**radamic**](https://github.com/radamic).

## License

Released under the [MIT License](LICENSE). The MIT License imposes no restrictions on commercial use, modification, distribution, or private use, subject to inclusion of the copyright notice and license text. Third-party dependencies retain their own licenses; review them before redistributing bundled artifacts.

## Acknowledgments

Built on the work of the open-source community, particularly `aiohttp`, `beautifulsoup4`, and `lxml`.
