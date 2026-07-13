# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.0.0] - Unreleased

First accumulated release after the async rewrite. Nothing in this range
has been tagged or published; all changes landed on `main` directly and
are included in the first 2.0.0 artifact.

### Added

- **True resumable crawl.** The pending frontier is now persisted to
  `frontier.json` and the visited/completed set is recorded only *after*
  a successful fetch. A crawl interrupted with `--cache-dir` set continues
  from its un-crawled frontier on the next run - and retries pages that
  failed - instead of only reloading the results it had already collected.
- **Seed-list input.** `--input-file PATH` (`-` for stdin) reads one seed
  URL per line (blank lines and `#` comments ignored). Each seed is crawled
  independently - its own domain, scope, and robots.txt - and the results
  are merged and de-duplicated. A dead seed is skipped, not fatal. Library:
  `crawl_seeds` / `crawl_seeds_async`.
- **New output formats.** `--format jsonl` (one JSON record per line, for
  streaming into `jq -c` / log pipelines) and `--format dot` / `graphml`
  (a `source -> url` link graph for Graphviz, Gephi, yEd, or networkx).
- **Sitemap discovery from robots.txt.** `--sitemap` now also fetches the
  sitemaps advertised in robots.txt `Sitemap:` directives, not just the
  conventional `/sitemap.xml`.
- **Playwright fetcher example** (`examples/playwright_fetcher.py`) plus a
  `nostrax[playwright]` extra, for crawling JavaScript-rendered sites via
  the `Fetcher` protocol.
- **mypy type-checking** in CI (the package ships `py.typed`); a `lint`
  job now runs ruff over `nostrax/`, `tests/`, and `examples/`.
- Per-host rate limiting. `--rate-limit` (and the `rate_limit=` kwarg)
  now spaces requests per netloc instead of globally, so a multi-domain
  crawl asking for 1 req/s no longer caps the entire job at 1 req/s.
- Separated connect and read timeouts. CLI gains `--connect-timeout` and
  `--read-timeout`; Python API gains `connect_timeout=` and
  `read_timeout=` on `crawl` / `crawl_async`. `--timeout` remains the
  total budget.
- `MetricsSink` protocol in `nostrax.metrics` for observability hooks.
  Three events: `on_page_fetched`, `on_fetch_failed`, `on_robots_blocked`.
  `NullMetricsSink` ships as the default. Sink exceptions are isolated
  and logged, never kill the crawl.
- `Fetcher` and `Extractor` protocols in `nostrax.protocols` so callers
  can plug in a Playwright-backed fetcher, a caching fetcher, or a
  custom parser without vendoring the crawler.
- Graceful SIGINT handling. Ctrl+C flushes the visited-set cache and
  exits 130 with a single warning log; no traceback.
- `FetchError` is now raised when the starting URL cannot be fetched,
  instead of silently returning `[]`. CLI catches `NostraxError` and
  exits 1 with a clean log line.
- Extraction now covers `<img srcset>`, `<source srcset>`, and
  `<meta http-equiv="refresh">` targets. `<base href>` is honoured when
  resolving relative URLs.
- GitHub Actions CI matrix: Python 3.10-3.14 on Linux, plus 3.10 and
  3.13 on macOS and Windows.
- PEP 561 `py.typed` marker so downstream type checkers pick up the
  shipped annotations.
- **robots.txt `Crawl-delay` is honoured** under `--respect-robots`: the
  per-host minimum interval is raised to the delay the site declares
  (never lowered below an explicit `--rate-limit`). Fractional delays
  like `Crawl-delay: 0.5` are supported, which stdlib's parser silently
  drops.
- Ruff lint gate in CI (`[tool.ruff]` config + a dedicated `lint` job),
  plus a `ruff format --check` gate. The codebase was formatted with
  `ruff format`; that bulk commit is listed in `.git-blame-ignore-revs`
  so `git blame` skips it.
- Richer packaging metadata in `pyproject.toml`: trove classifiers,
  `project.urls` (Homepage/Repository/Issues/Changelog), and keywords.

### Changed

- Extraction makes a **single document-order pass** over all requested
  tags instead of one full tree traversal per tag. With `--all-tags`
  this is one walk instead of ten, and results now reflect document
  order across tag types.
- `normalize_url` is memoised (bounded LRU). It is called two-to-three
  times per URL on the crawl hot paths (scope check, visited check,
  final dedup); repeats are now dict lookups.

- DFS and BFS now share a single engine: a frontier queue
  (`LifoQueue` or `Queue`) plus a worker pool of `max_concurrent`
  tasks. `--strategy bfs` is no longer artificially serial.
- `--check-status` reuses the crawl's aiohttp session, DNS cache, and
  resolver instead of building a second one. DNS and TLS costs are
  paid once per host.
- Results cache opens the append handle once per crawl and flushes per
  write, replacing the per-URL open+write+close cycle.
- `.nostraxrc` values now apply to every flag the user did not set on
  the command line, including int/float/string flags with non-None
  defaults (`depth`, `timeout`, `max-urls`, ...). Previously these
  were silently ignored.
- `--pattern` and `--exclude` regexes now run through the `regex`
  package with a 0.5 s per-URL timeout, bounding worst-case ReDoS
  exposure on every supported Python version.
- Sitemap XML is parsed through `defusedxml`.
- `updater.parse_version` uses `packaging.version.Version` so
  `--check-update` handles PEP 440 pre-release, dev, and local
  versions correctly.
- `__version__` is resolved at import time via `importlib.metadata`
  so the package and `pyproject.toml` can never drift.

### Fixed

- **Deterministic 4xx no longer retried**: `fetch_page` inspects the
  status directly and retries only transient failures (408, 429, 5xx).
  Previously `raise_for_status` turned every 404/403/410 into a
  `ClientError` that burned the full retry budget with backoff sleeps on
  a result that could never change.
- **IPv6 hosts normalise correctly**: `normalize_url` keeps the bracket
  form, so `http://[::1]:8080/x` no longer collapses to the malformed
  `http://::1:8080/x` and dedup/scope checks work for IPv6 URLs.
- **Case-insensitive scheme filtering**: `JavaScript:` / `MAILTO:`
  (any case) and `vbscript:` pseudo-URLs are now dropped like their
  lowercase forms instead of leaking into results.
- **Lenient `<meta http-equiv="refresh">` parsing**: whitespace around
  the `url=` separator (`content="5; url = /x"`) is now tolerated.
- **Path containment hardened**: file/cache write confinement uses
  `os.path.commonpath` on case-normalised, fully-resolved paths, fixing
  the `/base` vs `/base-evil` prefix ambiguity and correctly handling
  case-insensitive filesystems and separate Windows drives.
- **DNS rebinding TOCTOU**: a custom aiohttp resolver
  (`SafeResolver`) re-applies the SSRF classifier on every DNS
  resolution, closing the window between CLI-time validation and
  connect-time resolution.
- **SSRF validation**: domain-name targets are resolved via
  `socket.getaddrinfo` and every returned address is run through the
  unsafe-IP classifier (loopback, link-local, private, reserved,
  multicast, unspecified, IPv4-mapped IPv6, cloud metadata).
- **Visited-set save is atomic**: writes to `visited.json.tmp`,
  fsyncs, then `os.replace`s over the target. A crash mid-rewrite
  can no longer truncate the resume state.
- **Retry backoff is full-jitter** (`random.uniform(0, 2**attempt)`),
  replacing lockstep retry storms on rate-limited targets.
- **Body decoding**: use `response.charset` instead of
  `response.get_encoding()` (the latter raises when a response has
  no charset in Content-Type and the body was read via
  `content.read()` for the size-cap guard).
- **`format_urls` is now a pure formatter**: it no longer mutates
  caller-supplied `UrlResult` objects to attach status codes.
- **Cache resume**: `status` and `response_time` fields are now
  restored from `results.jsonl`, not silently dropped.
- **`--proxy` actually works**: the flag was validated but never
  passed to any aiohttp call. Now threaded through `fetch_page`,
  `RobotsChecker.load`, `fetch_sitemap`, and `check_url_status`.
- **Proxy credentials redacted** from any debug log that surfaces
  the proxy URL.
- **Config file bug**: `merge_config` keyed the override check on
  `None`/`False`, so int/float/string defaults locked out config
  values. Now driven by argparse-argv diffing.
- **`progress_callback` type hint** narrowed from `object | None`
  to `Callable[[int, int], None] | None`.
- **Frontier queue bounded** at `max(max_urls * 2, max_concurrent * 2)`
  so pathological fan-out pages can no longer balloon memory before
  the max-urls check fires.
- **Custom `Extractor`** returning `list[str]` when the crawler
  requires `list[UrlResult]` now fails with a clear `TypeError`
  rather than a deep `AttributeError`.

### Security

- SSRF hostname resolution plus `SafeResolver` at the connector
  layer (see Fixed).
- Sitemap parsing hardened via `defusedxml` (refuses external DTDs,
  entity expansion, and DOCTYPE declarations).
- `robots.txt` and `sitemap.xml` fetches now pin
  `allow_redirects=False` and cap the body size (1 MiB and 50 MiB
  respectively).
- Bounded regex matcher via the `regex` package with a per-URL
  timeout replaces the stdlib `re` backstop that had become a no-op
  on CPython 3.14+.
- Proxy credentials never land in logs.

### Removed

- `requirements.txt`. Runtime dependencies live in `pyproject.toml`
  only.
- `aiohttp.TCPConnector(enable_cleanup_closed=True)`: the upstream
  CPython bug it worked around is fixed and the flag emits a
  `DeprecationWarning` on Python 3.14+.
- `_parse_simple` config fallback: `tomli` is declared as a
  conditional dependency on Python 3.10 so `tomllib`-or-`tomli` is
  always available.

## [1.x]

Legacy synchronous releases. See git history before the 2.0.0 rewrite
(`4e7e9ad feat: rewrite nostrax as async package with full feature set`).
