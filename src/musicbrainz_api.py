"""MusicBrainz REST API client (no credentials required).

Uses the MusicBrainz JSON web service v2.
https://musicbrainz.org/doc/MusicBrainz_API

Requires a descriptive User-Agent per MusicBrainz policy.
Rate limit: ≤ 1 request per second for anonymous clients.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import requests

logger = logging.getLogger(__name__)

_BASE = "https://musicbrainz.org/ws/2"
_RATE_LIMIT_DELAY = 1.1  # seconds — MusicBrainz requires max 1 req/s
_DEFAULT_USER_AGENT = (
    "playlist-generator/1.0 (https://github.com/your-org/playlist-generator)"
)


class MusicBrainzError(Exception):
    """Raised when the MusicBrainz API returns an unexpected response."""


class MusicBrainzClient:
    """Thin wrapper around the MusicBrainz JSON web service v2."""

    def __init__(self, user_agent: str = _DEFAULT_USER_AGENT) -> None:
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Accept": "application/json",
                "User-Agent": user_agent,
            }
        )

    # ------------------------------------------------------------------
    # Low-level HTTP
    # ------------------------------------------------------------------

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        url = f"{_BASE}{path}"
        p: dict[str, Any] = {"fmt": "json"}
        if params:
            p.update(params)
        logger.debug("MusicBrainz GET %s %s", url, p)
        time.sleep(_RATE_LIMIT_DELAY)
        resp = self._session.get(url, params=p, timeout=15)
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Artist
    # ------------------------------------------------------------------

    def search_artist(self, name: str) -> dict | None:
        """Search for an artist by name and return the exact match or None.

        Uses the Lucene-based search endpoint.  Only an exact
        case-insensitive match is accepted; the first-result fallback that
        caused false positives in the Deezer client is deliberately avoided.
        """
        data = self._get("/artist", {"query": f'artist:"{name}"', "limit": 5})
        artists: list[dict] = data.get("artists", [])
        if not artists:
            logger.warning("MusicBrainz: no artist found for %r", name)
            return None

        q = name.casefold()
        for a in artists:
            if a.get("name", "").casefold() == q:
                logger.debug("MusicBrainz: artist match %r → mbid=%s", name, a["id"])
                return a

        logger.warning(
            "MusicBrainz: no exact artist match for %r (candidates: %s)",
            name,
            [a.get("name") for a in artists],
        )
        return None

    # ------------------------------------------------------------------
    # Recordings
    # ------------------------------------------------------------------

    def search_recording(
        self,
        title: str,
        artist: str | None = None,
        limit: int = 5,
    ) -> list[dict]:
        """Search for recordings by title (and optionally artist).

        Returns up to *limit* recording dicts.  Each may include an
        ``isrcs`` list when the recording has registered ISRCs in
        MusicBrainz.  The ``artist-credit`` key carries the credited
        artists as a list of dicts.
        """
        query = f'recording:"{title}"'
        if artist:
            query += f' AND artist:"{artist}"'
        data = self._get("/recording", {"query": query, "inc": "isrcs", "limit": limit})
        recordings: list[dict] = data.get("recordings", [])
        logger.debug(
            "MusicBrainz: search_recording %r → %d results", title, len(recordings)
        )
        return recordings

    def get_artist_recordings(
        self, mbid: str, limit: int = 10
    ) -> list[dict]:
        """Return up to *limit* recordings for the given MusicBrainz artist MBID.

        Recordings include their ISRCs via ``inc=isrcs``.  The MusicBrainz
        browse API is used (paginated); only the first page is fetched.
        Results are returned in the order the API provides them (roughly
        alphabetical by title).
        """
        # Over-fetch slightly so that recordings without ISRCs can be
        # skipped without falling short of the requested limit.
        fetch = min(limit * 3, 100)
        data = self._get(
            "/recording",
            {"artist": mbid, "inc": "isrcs", "limit": fetch, "offset": 0},
        )
        recordings: list[dict] = data.get("recordings", [])
        logger.debug(
            "MusicBrainz: %d recordings fetched for mbid=%s", len(recordings), mbid
        )
        return recordings[:limit]
