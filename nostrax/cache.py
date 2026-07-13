"""Disk-based crawl cache for resume support.

Copyright (c) 2024 prodrom3 / radamic
Licensed under the MIT License.
"""

import json
import logging
import os
from typing import IO

from nostrax.models import UrlResult
from nostrax.validation import is_path_within

logger = logging.getLogger(__name__)


class CrawlCache:
    """Persists crawl state to disk so interrupted crawls can resume."""

    def __init__(self, cache_dir: str) -> None:
        # Resolve to absolute path and ensure it's under cwd
        cache_dir = os.path.realpath(cache_dir)
        if not is_path_within(cache_dir, os.getcwd()):
            raise ValueError(
                f"Cache directory must be under current working directory: {cache_dir}"
            )
        self._dir = cache_dir
        self._visited_path = os.path.join(cache_dir, "visited.json")
        self._results_path = os.path.join(cache_dir, "results.jsonl")
        self._frontier_path = os.path.join(cache_dir, "frontier.json")
        self._visited: set[str] = set()
        self._results_fh: IO[str] | None = None

    def initialize(self) -> None:
        """Create cache directory, load existing state, open result handle."""
        os.makedirs(self._dir, exist_ok=True)

        if os.path.isfile(self._visited_path):
            try:
                with open(self._visited_path, encoding="utf-8") as f:
                    self._visited = set(json.load(f))
                logger.info("Resuming crawl: %d URLs already visited", len(self._visited))
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("Could not load visited cache: %s", e)
                self._visited = set()

        # Keep the results file open for the life of the crawl. Previously
        # save_result opened and closed once per URL, paying an open/close
        # syscall on every discovered link.
        self._results_fh = open(self._results_path, "a", encoding="utf-8")

    @property
    def visited(self) -> set[str]:
        return self._visited

    def mark_visited(self, url: str) -> None:
        """Mark a URL as visited and persist to disk."""
        self._visited.add(url)

    def save_result(self, result: UrlResult) -> None:
        """Append a result to the results file.

        Flushes after each write so a resumed crawl sees everything that
        was written before a process crash. fsync is intentionally skipped
        here because it dominates the per-URL cost; power-loss safety is
        provided only for the visited-set rewrite in :meth:`save_visited`.
        """
        if self._results_fh is None:
            raise RuntimeError("CrawlCache.save_result called before initialize() or after close()")
        self._results_fh.write(json.dumps(result.to_dict()) + "\n")
        self._results_fh.flush()

    def close(self) -> None:
        """Close the append handle. Safe to call multiple times."""
        if self._results_fh is not None:
            self._results_fh.close()
            self._results_fh = None

    def save_visited(self) -> None:
        """Persist the full visited set to disk atomically.

        Writes to a sibling .tmp file, fsyncs, then renames into place.
        A crash mid-write leaves either the previous file intact or the
        fully-written new file, never a truncated target.
        """
        tmp_path = self._visited_path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(list(self._visited), f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, self._visited_path)

    def save_frontier(self, items: list[tuple[str, int]]) -> None:
        """Persist the pending frontier (URLs discovered but not yet crawled).

        Written atomically like the visited set. On resume, these are
        re-enqueued so an interrupted crawl continues from where it stopped
        instead of only reloading the results it had already collected.
        """
        tmp_path = self._frontier_path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump([[url, depth] for url, depth in items], f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, self._frontier_path)

    def load_frontier(self) -> list[tuple[str, int]]:
        """Load a previously persisted pending frontier, or [] if none."""
        if not os.path.isfile(self._frontier_path):
            return []
        try:
            with open(self._frontier_path, encoding="utf-8") as f:
                data = json.load(f)
            return [(str(url), int(depth)) for url, depth in data]
        except (json.JSONDecodeError, OSError, ValueError, TypeError) as e:
            logger.warning("Could not load frontier cache: %s", e)
            return []

    def load_results(self) -> list[UrlResult]:
        """Load previously saved results from disk."""
        results: list[UrlResult] = []
        if not os.path.isfile(self._results_path):
            return results

        with open(self._results_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                    results.append(
                        UrlResult(
                            url=d["url"],
                            source=d.get("source", ""),
                            tag=d.get("tag", ""),
                            depth=d.get("depth", 0),
                            status=d.get("status"),
                            response_time=d.get("response_time_ms"),
                        )
                    )
                except (json.JSONDecodeError, KeyError) as e:
                    logger.warning("Skipping corrupt cache line: %s", e)
        return results

    def clear(self) -> None:
        """Delete all cache files. Closes any open result handle first."""
        self.close()
        for path in [self._visited_path, self._results_path, self._frontier_path]:
            if os.path.isfile(path):
                os.unlink(path)
        logger.info("Cache cleared: %s", self._dir)
