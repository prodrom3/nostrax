# nostrax

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-2.0.0-orange.svg)](https://github.com/prodrom3/nostrax)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

A fast, async tool for extracting URLs and paths from web pages. Inspired by "Nostos", the Greek concept of a heroic return journey, this tool aids in the digital exploration and mapping of the web.

<p align="center">
  <img width="460" height="460" src="https://github.com/prodrom3/nostrax/assets/7604466/2872263b-788b-42f4-96d4-7670437b205a)">
</p>

## Features

- **URL and Path Extraction** - extract URLs from `<a>`, `<img>`, `<script>`, `<link>`, `<form>`, `<iframe>`, `<video>`, `<audio>`, and `<source>` tags
- **Async Crawling** - concurrent HTTP requests via aiohttp with connection pooling and DNS caching
- **Recursive Crawling** - follow internal links to a configurable depth (DFS or BFS strategy)
- **Retry with Backoff** - transient failures are retried with exponential backoff
- **Content-Type Aware** - skips non-HTML responses (images, PDFs, binaries) without downloading
- **URL Normalization** - strips fragments, trailing slashes, sorts query params for better dedup
- **Rate Limiting** - configurable delay between requests for polite crawling
- **Scope Control** - restrict crawling to a URL path prefix
- **Sitemap Parsing** - extract URLs directly from sitemap.xml (including sitemap indexes)
- **Broken Link Checker** - check HTTP status codes for all discovered URLs
- **Response Time Tracking** - measure how long each URL takes to respond
- **Smart Filtering** - filter by domain, protocol, regex include/exclude patterns
- **Rich Metadata** - include source page, tag type, depth, and response time in output
- **Multiple Output Formats** - plain text, JSON, CSV, or self-contained HTML report
- **Config File** - save common options in `.nostraxrc` (TOML format)
- **Cache/Resume** - save crawl state to disk and resume interrupted crawls
- **Proxy Support** - route requests through an HTTP proxy
- **HTTP Authentication** - basic auth for crawling protected pages
- **robots.txt Support** - optionally respect crawl rules
- **Progress Bar** - visual progress during long crawls (via tqdm)
- **Silent Mode** - suppress output for scripting and integration

## Installation

```bash
git clone https://github.com/prodrom3/nostrax.git
cd nostrax
pip install .
```

For development (includes pytest and test utilities):

```bash
pip install -e ".[dev]"
```

For progress bar support:

```bash
pip install "nostrax[progress]"
```

## Usage

### Basic extraction

```bash
nostrax -t https://example.com
```

### Recursive crawl (depth 2, internal links only)

```bash
nostrax -t https://example.com -d 2 --domain internal
<<<<<<< HEAD
=======
```

### Breadth-first crawl scoped to /docs/

```bash
nostrax -t https://example.com -d 3 --strategy bfs --scope /docs/
```

### Rate-limited crawl with retries and robots.txt

```bash
nostrax -t https://example.com -d 3 --rate-limit 0.5 --retries 3 --respect-robots
```

### Broken link checker with HTML report

```bash
nostrax -t https://example.com -d 1 --check-status -f html -o report.html
```

### Resume an interrupted crawl

```bash
nostrax -t https://example.com -d 5 --cache-dir .crawl_cache
# If interrupted, re-run the same command to resume
```

### Extract from sitemap.xml

```bash
nostrax -t https://example.com --sitemap --sort
```

### Rich metadata JSON output

```bash
nostrax -t https://example.com -d 1 --metadata -f json
```

Output includes source page, tag type, depth, and response time:
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

### Crawl through a proxy with authentication

```bash
nostrax -t https://internal.example.com --proxy http://proxy:8080 --auth user:password
```

### Exclude URLs matching a pattern

```bash
nostrax -t https://example.com --exclude "\.(jpg|png|gif)$"
```

### Config file

Create a `.nostraxrc` file in your project or home directory:

```toml
depth = 2
rate_limit = 0.5
respect_robots = true
user_agent = "mybot/1.0"
max_concurrent = 20
scope = "/docs/"
```

All options can be set in the config file. CLI arguments override config values.

### All options

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

options:
  -V, --version         Show version and exit
  --check-update        Check PyPI for a newer version and exit
  -t, --target          Target URL to extract from
  -s, --silent          Suppress all output (exit code only)
  -d, --depth           Recursion depth for crawling (default: 0)
  --all-tags            Extract URLs from all supported tags
  --tags                Comma-separated list of tags to extract from
  --domain              Filter: all, internal, or external (default: all)
  --protocol            Comma-separated protocols to keep (e.g. https,http)
  --pattern             Regex pattern to filter URLs (keep matches)
  --exclude             Regex pattern to exclude URLs (remove matches)
  --sort                Sort URLs alphabetically
  -f, --format          Output format: plain, json, csv, or html (default: plain)
  -o, --output          Write output to file instead of stdout
  --timeout             Request timeout in seconds (default: 10)
  --user-agent          Custom User-Agent string
  -v, --verbose         Enable verbose logging
  --no-dedup            Keep duplicate URLs
  --max-concurrent      Max concurrent HTTP requests (default: 10)
  --respect-robots      Check robots.txt before crawling
  --max-urls            Stop crawling after this many URLs (default: 50000)
  --rate-limit          Minimum seconds between requests (default: 0)
  --proxy               Proxy URL (e.g. http://proxy:8080)
  --auth                HTTP basic auth as user:password
  --sitemap             Also parse sitemap.xml for additional URLs
  --check-status        Check HTTP status code of each discovered URL
  --metadata            Include source page, tag type, and depth in output
  --progress            Show a progress bar during crawling (requires tqdm)
  --retries             Number of retry attempts for failed requests (default: 2)
  --scope               Restrict crawling to a URL path prefix (e.g. /docs/)
  --strategy            Crawl strategy: dfs or bfs (default: dfs)
  --cache-dir           Directory to cache crawl state for resume support
  --no-config           Ignore .nostraxrc config file
```

### Python API

```python
from nostrax import crawl, extract_urls, UrlResult, normalize_url

# Simple sync crawl
urls = crawl("https://example.com", depth=1)

# With metadata and response time
results = crawl("https://example.com", depth=1, include_metadata=True)
for r in results:
    time_str = f"{r.response_time:.0f}ms" if r.response_time else "n/a"
    print(f"{r.url} ({time_str}, from {r.source})")

# BFS crawl scoped to /docs/, with resume
urls = crawl(
    "https://example.com",
    depth=3,
    strategy="bfs",
    scope="/docs/",
    cache_dir=".crawl_cache",
)

# Async crawl with rate limiting and retries
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

# URL normalization
assert normalize_url("https://Example.COM/page/") == "https://example.com/page"
assert normalize_url("https://example.com/page#top") == "https://example.com/page"
```

## Running Tests

```bash
pip install -e ".[dev]"
pytest
>>>>>>> 1de86f70cfb3ede799c9f714a1d5d8142c72890e
```

### Breadth-first crawl scoped to /docs/

```bash
nostrax -t https://example.com -d 3 --strategy bfs --scope /docs/
```

### Rate-limited crawl with retries and robots.txt

```bash
nostrax -t https://example.com -d 3 --rate-limit 0.5 --retries 3 --respect-robots
```

### Broken link checker with HTML report

```bash
nostrax -t https://example.com -d 1 --check-status -f html -o report.html
```

### Resume an interrupted crawl

```bash
nostrax -t https://example.com -d 5 --cache-dir .crawl_cache
# If interrupted, re-run the same command to resume
```

### Extract from sitemap.xml

```bash
nostrax -t https://example.com --sitemap --sort
```

### Rich metadata JSON output

```bash
nostrax -t https://example.com -d 1 --metadata -f json
```

Output includes source page, tag type, depth, and response time:
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

### Crawl through a proxy with authentication

```bash
nostrax -t https://internal.example.com --proxy http://proxy:8080 --auth user:password
```

### Exclude URLs matching a pattern

```bash
nostrax -t https://example.com --exclude "\.(jpg|png|gif)$"
```

### Config file

Create a `.nostraxrc` file in your project or home directory:

```toml
depth = 2
rate_limit = 0.5
respect_robots = true
user_agent = "mybot/1.0"
max_concurrent = 20
scope = "/docs/"
```

All options can be set in the config file. CLI arguments override config values.

### All options

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

options:
  -V, --version         Show version and exit
  --check-update        Check PyPI for a newer version and exit
  -t, --target          Target URL to extract from
  -s, --silent          Suppress all output (exit code only)
  -d, --depth           Recursion depth for crawling (default: 0)
  --all-tags            Extract URLs from all supported tags
  --tags                Comma-separated list of tags to extract from
  --domain              Filter: all, internal, or external (default: all)
  --protocol            Comma-separated protocols to keep (e.g. https,http)
  --pattern             Regex pattern to filter URLs (keep matches)
  --exclude             Regex pattern to exclude URLs (remove matches)
  --sort                Sort URLs alphabetically
  -f, --format          Output format: plain, json, csv, or html (default: plain)
  -o, --output          Write output to file instead of stdout
  --timeout             Request timeout in seconds (default: 10)
  --user-agent          Custom User-Agent string
  -v, --verbose         Enable verbose logging
  --no-dedup            Keep duplicate URLs
  --max-concurrent      Max concurrent HTTP requests (default: 10)
  --respect-robots      Check robots.txt before crawling
  --max-urls            Stop crawling after this many URLs (default: 50000)
  --rate-limit          Minimum seconds between requests (default: 0)
  --proxy               Proxy URL (e.g. http://proxy:8080)
  --auth                HTTP basic auth as user:password
  --sitemap             Also parse sitemap.xml for additional URLs
  --check-status        Check HTTP status code of each discovered URL
  --metadata            Include source page, tag type, and depth in output
  --progress            Show a progress bar during crawling (requires tqdm)
  --retries             Number of retry attempts for failed requests (default: 2)
  --scope               Restrict crawling to a URL path prefix (e.g. /docs/)
  --strategy            Crawl strategy: dfs or bfs (default: dfs)
  --cache-dir           Directory to cache crawl state for resume support
  --no-config           Ignore .nostraxrc config file
```

### Python API

```python
from nostrax import crawl, extract_urls, UrlResult, normalize_url

# Simple sync crawl
urls = crawl("https://example.com", depth=1)

# With metadata and response time
results = crawl("https://example.com", depth=1, include_metadata=True)
for r in results:
    time_str = f"{r.response_time:.0f}ms" if r.response_time else "n/a"
    print(f"{r.url} ({time_str}, from {r.source})")

# BFS crawl scoped to /docs/, with resume
urls = crawl(
    "https://example.com",
    depth=3,
    strategy="bfs",
    scope="/docs/",
    cache_dir=".crawl_cache",
)

# Async crawl with rate limiting and retries
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

# URL normalization
assert normalize_url("https://Example.COM/page/") == "https://example.com/page"
assert normalize_url("https://example.com/page#top") == "https://example.com/page"
```

## Running Tests

```bash
pip install -e ".[dev]"
pytest
```

## Author

Created by [prodrom3](https://github.com/prodrom3) at [radamic](https://github.com/radamic).

## Contributing

Contributions are welcome. Please fork this repository, commit your changes, and submit a pull request.

## License

nostrax is under the MIT License. See the LICENSE file for more details.

## Acknowledgments

Thanks to all the contributors who make this project possible.
Gratitude to the open-source community for continuous support.
