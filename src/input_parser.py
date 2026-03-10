"""Input file parser.

Supported formats
-----------------
1. **Artists** – one artist name per line *or* a CSV whose only meaningful
   column is ``artist``.
2. **Albums** – CSV with at least ``title`` + ``artist`` columns (optionally
   ``upc``).
3. **Tracks** – CSV with at least a ``title`` column (optionally ``artist``,
   ``album``, ``isrc``).

Auto-detection logic
--------------------
- If the file has no header that contains ``title``, assume it is a plain
  artist list.
- If the header contains ``title`` AND ``isrc`` or ``album``, assume tracks.
- If the header contains ``title`` AND ``artist`` but no ``isrc``/``album``,
  assume albums.
- If the header contains only ``artist``, assume artists.
"""

from __future__ import annotations

import csv
import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)


class InputMode(str, Enum):
    ARTISTS = "artists"
    ALBUMS = "albums"
    TRACKS = "tracks"


@dataclass
class ArtistEntry:
    artist: str


@dataclass
class AlbumEntry:
    title: str
    artist: str
    upc: str = ""


@dataclass
class TrackEntry:
    title: str
    artist: str = ""
    album: str = ""
    isrc: str = ""


@dataclass
class ParsedInput:
    mode: InputMode
    artists: list[ArtistEntry] = field(default_factory=list)
    albums: list[AlbumEntry] = field(default_factory=list)
    tracks: list[TrackEntry] = field(default_factory=list)


def parse_input_file(path: str | Path, mode: InputMode | None = None) -> ParsedInput:
    """Parse *path* and return a :class:`ParsedInput`.

    When *mode* is ``None`` (default) the format is auto-detected.
    """
    path = Path(path)
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        raise ValueError(f"Input file is empty: {path}")

    lines = raw.splitlines()

    # ------------------------------------------------------------------ #
    # Sniff whether this looks like CSV                                    #
    # ------------------------------------------------------------------ #
    dialect = None
    try:
        dialect = csv.Sniffer().sniff(raw[:4096], delimiters=",;\t|")
    except csv.Error:
        pass

    header_fields: list[str] = []
    if dialect or "," in lines[0]:
        reader = csv.reader(lines, dialect=dialect or csv.excel)
        first_row = next(reader)
        header_fields = [f.strip().lower() for f in first_row]
    else:
        # Plain text – treat every line as an artist name
        header_fields = []

    # ------------------------------------------------------------------ #
    # Auto-detect mode                                                     #
    # ------------------------------------------------------------------ #
    if mode is None:
        mode = _detect_mode(header_fields)

    # ------------------------------------------------------------------ #
    # Parse rows                                                           #
    # ------------------------------------------------------------------ #
    result = ParsedInput(mode=mode)

    if mode == InputMode.ARTISTS:
        # Support both plain list and CSV with "artist" column
        if not header_fields or header_fields == ["artist"]:
            if header_fields == ["artist"]:
                # Skip the header row; re-read everything
                data_lines = lines[1:]
            else:
                data_lines = lines
            for line in data_lines:
                name = line.strip().strip('"')
                if name:
                    result.artists.append(ArtistEntry(artist=name))
        else:
            # CSV with multiple columns but mode forced to artists
            artist_col = _col(header_fields, "artist")
            for row in _csv_rows(lines, dialect):
                val = _safe_get(row, artist_col)
                if val:
                    result.artists.append(ArtistEntry(artist=val))

    elif mode == InputMode.ALBUMS:
        title_col = _col(header_fields, "title")
        artist_col = _col(header_fields, "artist")
        upc_col = _col(header_fields, "upc", required=False)
        for row in _csv_rows(lines, dialect):
            title = _safe_get(row, title_col)
            artist = _safe_get(row, artist_col)
            if title and artist:
                result.albums.append(
                    AlbumEntry(
                        title=title,
                        artist=artist,
                        upc=_safe_get(row, upc_col) if upc_col is not None else "",
                    )
                )

    elif mode == InputMode.TRACKS:
        title_col = _col(header_fields, "title")
        artist_col = _col(header_fields, "artist", required=False)
        album_col = _col(header_fields, "album", required=False)
        isrc_col = _col(header_fields, "isrc", required=False)
        for row in _csv_rows(lines, dialect):
            title = _safe_get(row, title_col)
            if title:
                result.tracks.append(
                    TrackEntry(
                        title=title,
                        artist=_safe_get(row, artist_col) if artist_col is not None else "",
                        album=_safe_get(row, album_col) if album_col is not None else "",
                        isrc=_safe_get(row, isrc_col) if isrc_col is not None else "",
                    )
                )

    logger.info(
        "Parsed %s: mode=%s artists=%d albums=%d tracks=%d",
        path.name,
        mode.value,
        len(result.artists),
        len(result.albums),
        len(result.tracks),
    )
    return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _detect_mode(header_fields: list[str]) -> InputMode:
    if not header_fields:
        return InputMode.ARTISTS
    if header_fields == ["artist"] or (len(header_fields) == 1 and "artist" in header_fields[0]):
        return InputMode.ARTISTS
    if "title" not in header_fields:
        return InputMode.ARTISTS
    if "isrc" in header_fields or (
        "album" in header_fields and "artist" in header_fields
    ):
        return InputMode.TRACKS
    return InputMode.ALBUMS


def _col(fields: list[str], name: str, *, required: bool = True) -> int | None:
    try:
        return fields.index(name)
    except ValueError:
        if required:
            raise ValueError(f"Expected column {name!r} in header {fields}")
        return None


def _safe_get(row: list[str], idx: int | None) -> str:
    if idx is None or idx >= len(row):
        return ""
    return row[idx].strip()


def _csv_rows(lines: list[str], dialect) -> list[list[str]]:
    """Return data rows (skipping the header)."""
    reader = csv.reader(lines, dialect=dialect or csv.excel)
    rows = list(reader)
    return rows[1:]  # skip header
