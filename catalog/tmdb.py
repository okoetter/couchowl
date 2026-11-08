"""Small client for the TMDB API (v3) and the TMDB image server.

Only the server talks to TMDB; browsers never do (see docs/KONZEPT.md, "Datenschutz").
The read access token is sent as a Bearer header, so it never appears in URLs or logs.
"""

import logging
import threading
import time

import httpx
from django.conf import settings

logger = logging.getLogger(__name__)

API_URL = "https://api.themoviedb.org/3"
IMAGE_URL = "https://image.tmdb.org/t/p"

# Images larger than this are rejected (posters are usually 10-100 KB)
MAX_IMAGE_BYTES = 5 * 1024 * 1024
# How often a request is retried when TMDB answers "429 Too Many Requests"
MAX_RETRIES = 2
MAX_RETRY_WAIT_SECONDS = 10
# TMDB allows up to 20 items in append_to_response
MAX_APPENDED_SEASONS = 20
# Extra data in every details request (no additional requests needed)
DETAILS_APPENDED = "translations,watch/providers"


class TMDBError(Exception):
    """TMDB is unreachable or answered with an error."""


class TMDBNotConfigured(TMDBError):
    """TMDB_API_TOKEN is not set."""


class TMDBNotFound(TMDBError):
    """The requested movie, show or image does not exist (HTTP 404)."""


class TMDBClient:
    """Sends requests to TMDB, at most `requests_per_second` per process.

    TMDB allows roughly 40 requests per second per IP address. We stay well below that
    and additionally wait and retry when TMDB answers "429 Too Many Requests".
    `transport` lets tests replace the network with canned responses.
    """

    def __init__(self, token, *, transport=None, requests_per_second=20):
        self._api = httpx.Client(
            base_url=API_URL,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=10,
            transport=transport,
        )
        # The image server needs no token; don't send it there
        self._images = httpx.Client(base_url=IMAGE_URL, timeout=20, transport=transport)
        self._min_interval = 1 / requests_per_second if requests_per_second else 0
        self._next_slot = 0.0
        self._lock = threading.Lock()  # gunicorn threads share one client

    # --- API -------------------------------------------------------------------------------

    def get(self, path: str, **params) -> dict:
        """GET an API endpoint and return the decoded JSON."""
        return self._request(self._api, path, params).json()

    def search(self, query: str, language: str) -> dict:
        """Movies, shows and people matching `query` (first page, 20 results)."""
        return self.get("/search/multi", query=query, language=language, include_adult="false")

    def details(self, media_type: str, tmdb_id: int, language: str) -> dict:
        """Details of a movie or show, including the texts in all languages and the
        streaming providers in all regions (`watch/providers`, data from JustWatch)."""
        return self.get(
            f"/{media_type}/{int(tmdb_id)}",
            language=language,
            append_to_response=DETAILS_APPENDED,
        )

    def seasons(self, tmdb_id: int, numbers: list[int], language: str) -> dict[int, dict]:
        """Seasons of a show with their episodes, as {season number: TMDB season}.

        Several seasons come in one request (`append_to_response=season/1,season/2,…`),
        at most MAX_APPENDED_SEASONS at a time.
        """
        if len(numbers) > MAX_APPENDED_SEASONS:
            raise ValueError(f"At most {MAX_APPENDED_SEASONS} seasons per request")
        appended = ",".join(f"season/{int(number)}" for number in numbers)
        data = self.get(f"/tv/{int(tmdb_id)}", language=language, append_to_response=appended)
        return {n: data[f"season/{n}"] for n in numbers if f"season/{n}" in data}

    # --- Images -----------------------------------------------------------------------------

    def image(self, size: str, filename: str) -> tuple[bytes, str]:
        """Download an image. Returns (content, content type)."""
        response = self._request(self._images, f"/{size}/{filename}", {})
        content_type = response.headers.get("Content-Type", "").split(";")[0]
        if not content_type.startswith("image/"):
            raise TMDBError(f"Unexpected content type for image: {content_type!r}")
        if len(response.content) > MAX_IMAGE_BYTES:
            raise TMDBError("Image too large")
        return response.content, content_type

    # --- Internals ----------------------------------------------------------------------------

    def _request(self, http: httpx.Client, path: str, params: dict) -> httpx.Response:
        for attempt in range(MAX_RETRIES + 1):
            self._wait_for_slot()
            try:
                response = http.get(path, params=params)
            except httpx.HTTPError as error:
                raise TMDBError(f"TMDB request failed: {error}") from error

            if response.status_code == 429 and attempt < MAX_RETRIES:
                wait = _retry_after(response)
                logger.warning("TMDB rate limit reached, retrying in %s s", wait)
                time.sleep(wait)
                continue
            if response.status_code == 404:
                raise TMDBNotFound(path)
            if response.status_code == 401:
                logger.error("TMDB rejected the token. Check TMDB_API_TOKEN.")
            if response.is_error:
                raise TMDBError(f"TMDB answered {response.status_code} for {path}")
            return response
        raise TMDBError("TMDB rate limit")  # pragma: no cover (loop always returns or raises)

    def _wait_for_slot(self):
        """Simple per-process throttle: keep at least `_min_interval` between requests."""
        with self._lock:
            now = time.monotonic()
            wait = self._next_slot - now
            if wait > 0:
                time.sleep(wait)
            self._next_slot = max(now, self._next_slot) + self._min_interval


def _retry_after(response: httpx.Response) -> float:
    try:
        seconds = float(response.headers.get("Retry-After", 1))
    except ValueError:
        seconds = 1
    return min(max(seconds, 0), MAX_RETRY_WAIT_SECONDS)


_client: TMDBClient | None = None


def get_client() -> TMDBClient:
    """The shared client of this process (created on first use)."""
    global _client
    if not settings.TMDB_API_TOKEN:
        raise TMDBNotConfigured("TMDB_API_TOKEN is not set")
    if _client is None:
        _client = TMDBClient(settings.TMDB_API_TOKEN)
    return _client
