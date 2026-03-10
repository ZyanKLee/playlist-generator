"""Playlist generation logic.

Resolves entries from a :class:`~input_parser.ParsedInput` to Deezer
:class:`~models.Track` objects and stores the resulting playlist in the
local database.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from .database import get_session
from .deezer_api import DeezerClient
from .input_parser import InputMode, ParsedInput
from .models import GeneratedPlaylist, Track, playlist_tracks

logger = logging.getLogger(__name__)


def generate_playlist(
    parsed: ParsedInput,
    *,
    client: DeezerClient | None = None,
    name: str = "Generated Playlist",
    description: str = "",
    public: bool = False,
    limit_per_source: int = 10,
) -> GeneratedPlaylist:
    """Resolve *parsed* input to tracks and persist a :class:`~models.GeneratedPlaylist`.

    Parameters
    ----------
    parsed:
        Output of :func:`~input_parser.parse_input_file`.
    client:
        A :class:`~deezer_api.DeezerClient` instance.  Created automatically
        when not supplied.
    name:
        Human-readable playlist name stored in the database.
    description:
        Optional playlist description.
    public:
        Whether the playlist should be public on Deezer.
    limit_per_source:
        Maximum number of tracks fetched per artist / album.
    """
    if client is None:
        client = DeezerClient()

    tracks: list[Track] = []
    seen_ids: set[int] = set()

    def _add(t: Track | None) -> None:
        if t is not None and t.id not in seen_ids:
            seen_ids.add(t.id)
            tracks.append(t)

    # ------------------------------------------------------------------
    if parsed.mode == InputMode.ARTISTS:
        for entry in parsed.artists:
            logger.info("Processing artist: %s", entry.artist)
            artist = client.search_artist(entry.artist)
            if artist is None:
                logger.warning("Artist not found: %s", entry.artist)
                continue
            top = client.get_artist_top_tracks(artist.id, limit=limit_per_source)
            for t in top:
                _add(t)

    elif parsed.mode == InputMode.ALBUMS:
        for entry in parsed.albums:
            logger.info("Processing album: %s – %s", entry.title, entry.artist)
            album = client.search_album(entry.title, artist=entry.artist)
            if album is None:
                logger.warning("Album not found: %s", entry.title)
                continue
            for t in client.get_album_tracks(album.id)[:limit_per_source]:
                _add(t)

    elif parsed.mode == InputMode.TRACKS:
        for entry in parsed.tracks:
            logger.info("Processing track: %s", entry.title)
            t = client.search_track(
                entry.title,
                artist=entry.artist or None,
                album=entry.album or None,
                isrc=entry.isrc or None,
            )
            _add(t)

    # ------------------------------------------------------------------
    # Persist playlist to database
    # ------------------------------------------------------------------
    playlist = GeneratedPlaylist(
        name=name,
        description=description,
        public=public,
        created_at=datetime.now(timezone.utc),
    )

    with get_session() as db:
        db.add(playlist)
        db.flush()  # get auto-assigned id
        for position, track in enumerate(tracks):
            # Merge (or re-attach) track to *this* session
            track_in_session = db.merge(track)
            db.execute(
                playlist_tracks.insert().values(
                    playlist_id=playlist.id,
                    track_id=track_in_session.id,
                    position=position,
                )
            )
        db.refresh(playlist)
        # Detach so we can use it outside the session
        db.expunge(playlist)
        for t in tracks:
            try:
                db.expunge(t)
            except Exception:
                pass

    logger.info(
        "Playlist %r created with %d tracks (id=%s)", name, len(tracks), playlist.id
    )
    return playlist
