"""HTTP with a disk cache, retries, and the quirks these hosts actually have.

Two things learned the hard way and encoded here rather than rediscovered:

* ``data-api.polymarket.com`` returns 403 to a bare Python user agent.  A
  browser-ish UA works; curl works regardless, so it is the fallback.
* Every response is cached on disk, keyed by URL.  These analyses take
  thousands of requests and get re-run repeatedly while tuning thresholds;
  re-fetching each time is slow, rude to the host, and makes results
  irreproducible because the tape moves under you.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Iterable, Sequence

try:
    import requests
except ImportError:  # pragma: no cover - requests is near-universal
    requests = None  # type: ignore

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

HEADERS = {
    "User-Agent": UA,
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
}


class Fetcher:
    """Cached JSON GET with a curl fallback."""

    def __init__(self, cache_dir: str = ".polycache", timeout: int = 30,
                 retries: int = 3, use_cache: bool = True):
        self.cache_dir = cache_dir
        self.timeout = timeout
        self.retries = retries
        self.use_cache = use_cache
        self.stats = {"hit": 0, "miss": 0, "curl": 0, "fail": 0}
        if use_cache:
            os.makedirs(cache_dir, exist_ok=True)
        self._session = requests.Session() if requests is not None else None
        if self._session is not None:
            self._session.headers.update(HEADERS)

    # ------------------------------------------------------------- cache
    def _path(self, url: str) -> str:
        h = hashlib.sha256(url.encode()).hexdigest()[:24]
        return os.path.join(self.cache_dir, f"{h}.json")

    def _read_cache(self, url: str) -> Any | None:
        if not self.use_cache:
            return None
        p = self._path(url)
        if not os.path.exists(p):
            return None
        try:
            with open(p) as fh:
                return json.load(fh)
        except (OSError, json.JSONDecodeError):
            return None

    def _write_cache(self, url: str, data: Any) -> None:
        if not self.use_cache:
            return
        try:
            tmp = self._path(url) + ".tmp"
            with open(tmp, "w") as fh:
                json.dump(data, fh)
            os.replace(tmp, self._path(url))
        except OSError:
            pass

    # -------------------------------------------------------------- get
    def get(self, url: str) -> Any | None:
        cached = self._read_cache(url)
        if cached is not None:
            self.stats["hit"] += 1
            return cached

        self.stats["miss"] += 1
        data = self._get_requests(url)
        if data is None:
            data = self._get_curl(url)
        if data is None:
            self.stats["fail"] += 1
            return None
        self._write_cache(url, data)
        return data

    def _get_requests(self, url: str) -> Any | None:
        if self._session is None:
            return None
        for attempt in range(self.retries):
            try:
                r = self._session.get(url, timeout=self.timeout)
                if r.status_code == 200:
                    return r.json()
                if r.status_code in (403, 405):
                    return None          # fall through to curl
                if r.status_code == 429:
                    time.sleep(2 ** attempt)
                    continue
                if 500 <= r.status_code < 600:
                    time.sleep(2 ** attempt)
                    continue
                return None
            except Exception:
                time.sleep(2 ** attempt)
        return None

    def _get_curl(self, url: str) -> Any | None:
        for attempt in range(self.retries):
            try:
                out = subprocess.run(
                    ["curl", "-sS", "--compressed", "--max-time", str(self.timeout),
                     "-H", f"User-Agent: {UA}", "-H", "Accept: application/json", url],
                    capture_output=True, text=True, timeout=self.timeout + 10,
                )
                if out.returncode == 0 and out.stdout.strip():
                    self.stats["curl"] += 1
                    return json.loads(out.stdout)
            except (subprocess.SubprocessError, json.JSONDecodeError, OSError):
                pass
            time.sleep(2 ** attempt)
        return None

    def map(self, urls: Sequence[str], workers: int = 12) -> list[Any | None]:
        """Fetch many URLs concurrently, preserving order."""
        if not urls:
            return []
        with ThreadPoolExecutor(max_workers=workers) as pool:
            return list(pool.map(self.get, urls))

    def paginate(
        self,
        make_url: Callable[[int], str],
        page_size: int,
        max_pages: int,
        stop_when_short: bool = True,
    ) -> list[dict]:
        """Walk offset-paginated endpoints until they run dry.

        Sequential by necessity: we cannot know a page is the last one until
        it comes back short.
        """
        rows: list[dict] = []
        for page in range(max_pages):
            batch = self.get(make_url(page * page_size))
            if not batch or not isinstance(batch, list):
                break
            rows.extend(batch)
            if stop_when_short and len(batch) < page_size:
                break
        return rows
