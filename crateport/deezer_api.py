"""Deezer REST API client with transparent local caching.

Public API endpoints do *not* require authentication.
Authenticated endpoints (create/modify playlists) need an OAuth access token
obtained via the :mod:`auth` module.

Reference: https://developers.deezer.com/api
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

import requests
from sqlalchemy.orm import Session

from .database import get_session, is_fresh
from .models import Album, Artist, Track, artist_top_tracks

logger = logging.getLogger(__name__)

_BASE = "https://api.deezer.com"
_DEFAULT_TOP_LIMIT = 50
_RATE_LIMIT_DELAY = 0.3  # seconds between requests to stay well under limits


class DeezerAPIError(Exception):
    """Raised when the Deezer API returns an error payload."""


class DeezerClient:
    """Thin wrapper around the Deezer REST API with SQLAlchemy caching."""

    def __init__(self, access_token: str | None = None) -> None:
        self._token = access_token
        self._session = requests.Session()
        self._session.headers["Accept"] = "application/json"

    # ------------------------------------------------------------------
    # Low-level HTTP helpers
    # ------------------------------------------------------------------

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """Perform a GET request and return the parsed JSON body."""
        url = f"{_BASE}{path}"
        p: dict[str, Any] = params or {}
        if self._token:
            p["access_token"] = self._token
        logger.debug("GET %s %s", url, p)
        time.sleep(_RATE_LIMIT_DELAY)
        resp = self._session.get(url, params=p, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict) and "error" in data:
            err = data["error"]
            raise DeezerAPIError(
                f"{err.get('type', 'Error')} {err.get('code')}: {err.get('message')}"
            )
        return data

    def _post(self, path: str, params: dict[str, Any] | None = None) -> Any:
        url = f"{_BASE}{path}"
        p: dict[str, Any] = params or {}
        if self._token:
            p["access_token"] = self._token
        logger.debug("POST %s %s", url, p)
        resp = self._session.post(url, params=p, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict) and "error" in data:
            err = data["error"]
            raise DeezerAPIError(
                f"{err.get('type', 'Error')} {err.get('code')}: {err.get('message')}"
            )
        return data

    # ------------------------------------------------------------------
    # Artist
    # ------------------------------------------------------------------

    def search_artist(self, name: str) -> Artist | None:
        """Return the best-matching :class:`~models.Artist` for *name*.

        Results are cached; a fresh cached entry is returned without hitting
        the API.
        """
        with get_session() as db:
            cached = _find_artist_by_name(db, name)
            if cached and is_fresh(cached.cached_at):
                logger.debug("Cache hit: artist %r", name)
                return cached

            data = self._get("/search/artist", {"q": name, "limit": 5})
            items = data.get("data", [])
            if not items:
                logger.warning("No artist found for %r", name)
                return None

            # Pick the result whose name matches exactly (case-insensitive)
            best = _best_match(items, name, key="name")
            if best is None:
                logger.warning(
                    "No exact artist match for %r (candidates: %s)",
                    name,
                    [i.get("name") for i in items],
                )
                return None
            artist = _upsert_artist(db, best)
            return artist

    def get_artist_top_tracks(
        self, artist_id: int, limit: int = _DEFAULT_TOP_LIMIT
    ) -> list[Track]:
        """Return (and cache) the top *limit* tracks for the given artist."""
        with get_session() as db:
            artist: Artist | None = db.get(Artist, artist_id)
            if artist and is_fresh(artist.cached_at):
                existing = (
                    db.query(Track)
                    .join(artist_top_tracks, Track.id == artist_top_tracks.c.track_id)
                    .filter(artist_top_tracks.c.artist_id == artist_id)
                    .limit(limit)
                    .all()
                )
                # Only accept the cache when it holds at least as many tracks as
                # requested.  A previous run with a smaller --limit stores fewer
                # rows; in that case we fall through and re-query the API.
                if len(existing) >= limit:
                    logger.debug("Cache hit: top tracks for artist %s", artist_id)
                    return existing

            data = self._get(f"/artist/{artist_id}/top", {"limit": limit})
            items = data.get("data", [])
            tracks: list[Track] = []
            for item in items:
                track = _upsert_track(db, item)
                tracks.append(track)
                # Ensure the association row exists
                exists = db.execute(
                    artist_top_tracks.select().where(
                        artist_top_tracks.c.artist_id == artist_id,
                        artist_top_tracks.c.track_id == track.id,
                    )
                ).first()
                if not exists:
                    db.execute(
                        artist_top_tracks.insert().values(
                            artist_id=artist_id, track_id=track.id
                        )
                    )
        # Session is closed; enrich in separate per-track sessions
        tracks = self.enrich_isrcs(tracks)
        return tracks

    # ------------------------------------------------------------------
    # Album
    # ------------------------------------------------------------------

    def search_album(self, title: str, artist: str | None = None) -> Album | None:
        """Return the best-matching :class:`~models.Album` for *title*."""
        query = f'album:"{title}"'
        if artist:
            query += f' artist:"{artist}"'

        with get_session() as db:
            # Check cache first
            q = db.query(Album).filter(Album.title.ilike(title))
            if artist:
                q = q.join(Artist, Album.artist_id == Artist.id).filter(
                    Artist.name.ilike(artist)
                )
            cached = q.first()
            if cached and is_fresh(cached.cached_at):
                logger.debug("Cache hit: album %r", title)
                return cached

            data = self._get("/search/album", {"q": query, "limit": 5})
            items = data.get("data", [])
            if not items:
                logger.warning("No album found for %r", title)
                return None

            best = _best_match(items, title, key="title")
            if best is None:
                logger.warning(
                    "No exact album match for %r (candidates: %s)",
                    title,
                    [i.get("title") for i in items],
                )
                return None
            album = _upsert_album(db, best)
            return album

    def get_album_tracks(self, album_id: int) -> list[Track]:
        """Return (and cache) all tracks for the given album."""
        with get_session() as db:
            album: Album | None = db.get(Album, album_id)
            if album and is_fresh(album.cached_at):
                existing = db.query(Track).filter(Track.album_id == album_id).all()
                if existing:
                    logger.debug("Cache hit: tracks for album %s", album_id)
                    return existing

            data = self._get(f"/album/{album_id}/tracks")
            items = data.get("data", [])
            tracks = [_upsert_track(db, item, album_id=album_id) for item in items]
        # Session is closed; enrich in separate per-track sessions
        tracks = self.enrich_isrcs(tracks)
        return tracks

    # ------------------------------------------------------------------
    # Track (full object)
    # ------------------------------------------------------------------

    def get_track(self, track_id: int) -> Track | None:
        """Return the full track object for *track_id*, including ISRC.

        Skips the API call when the cached record already has an ISRC.
        """
        with get_session() as db:
            cached: Track | None = db.get(Track, track_id)
            if cached and cached.isrc and is_fresh(cached.cached_at):
                logger.debug("Cache hit (isrc): track %s", track_id)
                return cached

            data = self._get(f"/track/{track_id}")
            track = _upsert_track(db, data)
            return track

    def enrich_isrcs(self, tracks: list[Track]) -> list[Track]:
        """Fetch full track details for every track that is missing an ISRC.

        Tracks that already have an ISRC are returned unchanged without any
        API call.  Updated :class:`~models.Track` instances are returned in
        the same order.
        """
        enriched: list[Track] = []
        for track in tracks:
            if track.isrc:
                enriched.append(track)
            else:
                full = self.get_track(track.id)
                enriched.append(full if full is not None else track)
        return enriched

    # ------------------------------------------------------------------
    # Track search
    # ------------------------------------------------------------------

    def get_track_by_isrc(self, isrc: str) -> Track | None:
        """Look up a Deezer track directly by ISRC.

        Uses the ``/track/isrc/{isrc}`` endpoint which is an exact lookup.
        Returns ``None`` when the ISRC is not in Deezer's catalogue.
        """
        with get_session() as db:
            cached = db.query(Track).filter(Track.isrc == isrc).first()
            if cached and is_fresh(cached.cached_at):
                logger.debug("Cache hit (isrc lookup): %s", isrc)
                return cached
        try:
            data = self._get(f"/track/isrc/{isrc}")
        except DeezerAPIError as exc:
            logger.debug("ISRC %s not found on Deezer: %s", isrc, exc)
            return None
        if not isinstance(data, dict) or "id" not in data:
            return None
        with get_session() as db:
            track = _upsert_track(db, data)
        return track

    def search_track_candidates(
        self,
        title: str,
        artist: str | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Return up to *limit* raw Deezer search results for *title* / *artist*.

        Unlike :meth:`search_track`, nothing is persisted and no "best match"
        heuristic is applied, so the caller can do interactive disambiguation.
        Each result dict contains at minimum: ``id``, ``title``, ``artist``
        (nested dict with ``name``), ``album`` (nested dict with ``title``).
        The ``isrc`` key is **absent** from bulk search results; call
        :meth:`get_track` on the chosen ID to retrieve a full ISRC.
        """
        query = f'track:"{title}"'
        if artist:
            query += f' artist:"{artist}"'
        data = self._get("/search/track", {"q": query, "limit": limit})
        return data.get("data", [])

    def search_track(
        self,
        title: str,
        artist: str | None = None,
        album: str | None = None,
        isrc: str | None = None,
    ) -> Track | None:
        """Return the best-matching :class:`~models.Track`."""
        with get_session() as db:
            # ISRC is a perfect identifier – check cache first
            if isrc:
                cached = db.query(Track).filter(Track.isrc == isrc).first()
                if cached and is_fresh(cached.cached_at):
                    return cached

            query = f'track:"{title}"'
            if artist:
                query += f' artist:"{artist}"'
            if album:
                query += f' album:"{album}"'

            data = self._get("/search/track", {"q": query, "limit": 5})
            items = data.get("data", [])
            if not items:
                logger.warning("No track found for %r (artist=%r)", title, artist)
                return None

            best = _best_match(items, title, key="title")
            if best is None:
                logger.warning(
                    "No exact track match for %r (candidates: %s)",
                    title,
                    [i.get("title") for i in items],
                )
                return None
            track = _upsert_track(db, best)
        # Session is closed; enrich if ISRC missing
        if not track.isrc:
            track = self.get_track(track.id) or track
        return track

    # ------------------------------------------------------------------
    # Playlist management (requires auth)
    # ------------------------------------------------------------------

    def create_playlist(self, user_id: int | str, title: str) -> int:
        """Create a new Deezer playlist and return its ID."""
        data = self._post(f"/user/{user_id}/playlists", {"title": title})
        return int(data["id"])

    def add_tracks_to_playlist(self, playlist_id: int, track_ids: list[int]) -> bool:
        """Add tracks to a Deezer playlist (max 1000 IDs per call)."""
        songs = ",".join(str(t) for t in track_ids)
        self._post(f"/playlist/{playlist_id}/tracks", {"songs": songs})
        return True

    def update_playlist(
        self,
        playlist_id: int,
        *,
        description: str | None = None,
        public: bool | None = None,
    ) -> bool:
        """Update playlist metadata."""
        params: dict[str, Any] = {}
        if description is not None:
            params["description"] = description
        if public is not None:
            params["public"] = 1 if public else 0
        if params:
            self._post(f"/playlist/{playlist_id}", params)
        return True

    def get_me(self) -> dict[str, Any]:
        """Return the authenticated user's profile."""
        return self._get("/user/me")


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _best_match(items: list[dict], query: str, *, key: str) -> dict | None:
    """Return the item whose *key* field best matches *query* (case-insensitive).

    Returns the first exact (case-insensitive) match, or ``None`` when no
    candidate matches.  The previous behaviour of falling back to ``items[0]``
    caused unrelated artists/tracks to silently pollute generated playlists
    whenever the searched name was not present in the result set.
    """
    q = query.casefold()
    for item in items:
        if item.get(key, "").casefold() == q:
            return item
    return None


def _find_artist_by_name(db: Session, name: str) -> Artist | None:
    return db.query(Artist).filter(Artist.name.ilike(name)).first()


def _upsert_artist(db: Session, data: dict) -> Artist:
    artist = Artist(
        id=data["id"],
        name=data["name"],
        picture=data.get("picture_medium") or data.get("picture"),
        nb_fan=data.get("nb_fan"),
        link=data.get("link"),
        cached_at=datetime.now(timezone.utc),
    )
    return db.merge(artist)


def _upsert_album(db: Session, data: dict, artist_id: int | None = None) -> Album:
    if "artist" in data and isinstance(data["artist"], dict):
        art = _upsert_artist(db, data["artist"])
        artist_id = art.id
    album = Album(
        id=data["id"],
        title=data["title"],
        artist_id=artist_id,
        cover=data.get("cover_medium") or data.get("cover"),
        upc=data.get("upc"),
        nb_tracks=data.get("nb_tracks"),
        cached_at=datetime.now(timezone.utc),
    )
    return db.merge(album)


def _upsert_track(db: Session, data: dict, album_id: int | None = None) -> Track:
    # Resolve nested artist/album if present
    art_id: int | None = None
    if "artist" in data and isinstance(data["artist"], dict):
        art = _upsert_artist(db, data["artist"])
        art_id = art.id
    alb_id = album_id
    if alb_id is None and "album" in data and isinstance(data["album"], dict):
        alb = _upsert_album(db, data["album"])
        alb_id = alb.id
    # Preserve a stored ISRC when the incoming data lacks one.
    # Bulk endpoints (/artist/{id}/top, /album/{id}/tracks) omit isrc; the
    # full /track/{id} object includes it.  We must not overwrite a good ISRC
    # with None on a second fetch.
    isrc = data.get("isrc")
    if not isrc:
        existing = db.get(Track, data["id"])
        if existing:
            isrc = existing.isrc
    track = Track(
        id=data["id"],
        title=data["title"],
        artist_id=art_id,
        album_id=alb_id,
        duration=data.get("duration"),
        isrc=isrc,
        rank=data.get("rank"),
        preview=data.get("preview"),
        link=data.get("link"),
        cached_at=datetime.now(timezone.utc),
    )
    return db.merge(track)
