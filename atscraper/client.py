"""HTTP session for author.today: headers, CSRF, rate limiting, retries.

Etiquette rules from CLAUDE.md: single connection, 1-2 s delay with jitter
between requests, exponential backoff on 429/5xx, honest User-Agent.
"""

from __future__ import annotations

import logging
import random
import time
from types import TracebackType

import httpx

from . import __version__

logger = logging.getLogger(__name__)

BASE_URL = "https://author.today"
USER_AGENT = (
    f"atscraper/{__version__} "
    "(personal research script; contact: nkuibmi784@hotmail.com)"
)
MIN_DELAY_S = 1.5
JITTER_S = 0.7
MAX_RETRIES = 5
BACKOFF_BASE_S = 3.0
RETRY_STATUSES = {429, 500, 502, 503, 504}


class Client:
    """Single-connection, rate-limited session against author.today."""

    def __init__(self) -> None:
        self._http = httpx.Client(
            base_url=BASE_URL,
            headers={"User-Agent": USER_AGENT},
            timeout=30.0,
            follow_redirects=True,
        )
        self._csrf_token: str | None = None
        self._last_request_at = 0.0

    def __enter__(self) -> Client:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self._http.close()

    def set_csrf_token(self, token: str) -> None:
        self._csrf_token = token

    def get_work_page(self, work_id: str) -> httpx.Response:
        return self._get(f"/work/{work_id}")

    def get_comments_page(self, work_id: str, page: int) -> httpx.Response:
        return self._get(
            "/comment/load",
            params={"rootId": work_id, "rootType": 1, "page": page},
            ajax=True,
        )

    def get_thread(self, work_id: str, parent_id: str) -> httpx.Response:
        return self._get(
            "/comment/loadThread",
            params={"parentId": parent_id, "rootId": work_id, "rootType": 1},
            ajax=True,
        )

    def _get(
        self, url: str, params: dict | None = None, ajax: bool = False
    ) -> httpx.Response:
        headers: dict[str, str] = {}
        if ajax:
            headers["X-Requested-With"] = "XMLHttpRequest"
            if self._csrf_token:
                headers["RequestVerificationToken"] = self._csrf_token
        for attempt in range(MAX_RETRIES + 1):
            self._throttle()
            response = self._http.get(url, params=params, headers=headers)
            if response.status_code in RETRY_STATUSES and attempt < MAX_RETRIES:
                wait = BACKOFF_BASE_S * 2**attempt
                logger.warning(
                    "HTTP %d on %s, retry %d/%d in %.0f s",
                    response.status_code,
                    url,
                    attempt + 1,
                    MAX_RETRIES,
                    wait,
                )
                time.sleep(wait)
                continue
            response.raise_for_status()
            return response
        raise httpx.HTTPStatusError(
            f"giving up on {url} after {MAX_RETRIES} retries",
            request=response.request,
            response=response,
        )

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        delay = MIN_DELAY_S + random.uniform(0.0, JITTER_S)
        if elapsed < delay:
            time.sleep(delay - elapsed)
        self._last_request_at = time.monotonic()
