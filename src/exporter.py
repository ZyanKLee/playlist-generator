"""Playlist export to standard interchange formats.

All exporters write to ``output/`` by default and return the path written.

Supported formats
-----------------
* **XSPF** (XML Shareable Playlist Format, version 1) – open standard readable
  by VLC, foobar2000, and most media players.
* **M3U** – extended M3U with ``#EXTINF`` metadata.
* **CSV** – Deezer-compatible track import file (title, artist, isrc columns).
  Import via *Deezer web → My Music → Import tracks*.
* **JSON** – machine-readable dump of the full playlist + track metadata.

Track data is passed as plain ``dict`` objects so no live ORM session is
required at export time.  Expected keys (all optional except ``title``):

    id, title, artist, album, duration, isrc, rank, preview, link

References
----------
* XSPF spec: https://xspf.org/xspf-v1.html
* Deezer track import: https://support.deezer.com/hc/en-gb/articles/360011538897
"""

from __future__ import annotations

import csv
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .models import GeneratedPlaylist

# A track record is a plain dict produced by cli._load_tracks_data().
TrackData = dict[str, Any]

FORMATS = ("xspf", "m3u", "csv", "json")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def export(
    playlist: "GeneratedPlaylist",
    tracks: list[TrackData],
    *,
    fmt: str,
    output_dir: Path,
    stem: str | None = None,
) -> Path:
    """Export *playlist* + *tracks* in the requested *fmt*.

    Parameters
    ----------
    playlist:
        The :class:`~models.GeneratedPlaylist` to export.
    tracks:
        Ordered list of track dicts (keys: id, title, artist, album,
        duration, isrc, rank, preview, link).
    fmt:
        One of ``"xspf"``, ``"m3u"``, ``"csv"``, ``"json"``.
    output_dir:
        Directory where the file will be written.
    stem:
        Base filename without extension.  Defaults to ``playlist_<id>``.

    Returns
    -------
    Path
        Absolute path of the written file.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = stem or f"playlist_{playlist.id}"

    exporters = {
        "xspf": _export_xspf,
        "m3u": _export_m3u,
        "csv": _export_csv,
        "json": _export_json,
    }
    fn = exporters.get(fmt.lower())
    if fn is None:
        raise ValueError(f"Unknown export format {fmt!r}. Choose from: {', '.join(exporters)}")

    return fn(playlist, tracks, output_dir / stem)


def export_all(
    playlist: "GeneratedPlaylist",
    tracks: list[TrackData],
    *,
    output_dir: Path,
    stem: str | None = None,
) -> dict[str, Path]:
    """Export *playlist* to all supported formats.

    Returns a mapping of ``{fmt: path}``.
    """
    return {
        fmt: export(playlist, tracks, fmt=fmt, output_dir=output_dir, stem=stem)
        for fmt in FORMATS
    }


# ---------------------------------------------------------------------------
# XSPF
# ---------------------------------------------------------------------------

_XSPF_NS = "http://xspf.org/ns/0/"


def _export_xspf(
    playlist: "GeneratedPlaylist",
    tracks: list[TrackData],
    dest: Path,
) -> Path:
    dest = dest.with_suffix(".xspf")

    ET.register_namespace("", _XSPF_NS)

    root = ET.Element(f"{{{_XSPF_NS}}}playlist", version="1")

    def _sub(parent: ET.Element, tag: str, text: str | None = None) -> ET.Element:
        el = ET.SubElement(parent, f"{{{_XSPF_NS}}}{tag}")
        if text is not None:
            el.text = text
        return el

    _sub(root, "title", playlist.name)
    if playlist.description:
        _sub(root, "annotation", playlist.description)

    track_list = _sub(root, "trackList")
    for t in tracks:
        track_el = _sub(track_list, "track")
        _sub(track_el, "title", t["title"])
        if t.get("artist"):
            _sub(track_el, "creator", t["artist"])
        if t.get("album"):
            _sub(track_el, "album", t["album"])
        if t.get("duration"):
            _sub(track_el, "duration", str(t["duration"] * 1000))  # ms
        if t.get("isrc"):
            _sub(track_el, "identifier", f"isrc:{t['isrc']}")
        if t.get("link"):
            _sub(track_el, "info", t["link"])
            _sub(track_el, "location", t["link"])

    ET.indent(root, space="  ")
    dest.write_bytes(
        b'<?xml version="1.0" encoding="UTF-8"?>\n'
        + ET.tostring(root, encoding="unicode").encode("utf-8")
    )
    return dest


# ---------------------------------------------------------------------------
# M3U
# ---------------------------------------------------------------------------


def _export_m3u(
    playlist: "GeneratedPlaylist",
    tracks: list[TrackData],
    dest: Path,
) -> Path:
    dest = dest.with_suffix(".m3u8")
    lines: list[str] = ["#EXTM3U", f"#PLAYLIST:{playlist.name}"]
    if playlist.description:
        lines.append(f"# {playlist.description}")
    lines.append("")

    for t in tracks:
        artist = t.get("artist", "")
        duration_s = t.get("duration") or -1
        display = f"{artist} - {t['title']}" if artist else t["title"]
        lines.append(f"#EXTINF:{duration_s},{display}")
        if t.get("isrc"):
            lines.append(f"# ISRC: {t['isrc']}")
        lines.append(t.get("link") or f"# deezer track id: {t['id']}")
        lines.append("")

    dest.write_text("\n".join(lines), encoding="utf-8")
    return dest


# ---------------------------------------------------------------------------
# Deezer-importable CSV
# ---------------------------------------------------------------------------


def _export_csv(
    playlist: "GeneratedPlaylist",
    tracks: list[TrackData],
    dest: Path,
) -> Path:
    """Write a CSV that Deezer's *Import tracks* tool understands.

    Deezer matches tracks by ISRC when present, falling back to title + artist.
    Columns: title, artist, album, isrc (title is the only required column).
    """
    dest = dest.with_suffix(".csv")
    with dest.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["title", "artist", "album", "isrc"])
        for t in tracks:
            writer.writerow([
                t.get("title", ""),
                t.get("artist", ""),
                t.get("album", ""),
                t.get("isrc", ""),
            ])
    return dest


# ---------------------------------------------------------------------------
# JSON
# ---------------------------------------------------------------------------


def _export_json(
    playlist: "GeneratedPlaylist",
    tracks: list[TrackData],
    dest: Path,
) -> Path:
    dest = dest.with_suffix(".json")
    payload = {
        "id": playlist.id,
        "name": playlist.name,
        "description": playlist.description,
        "public": playlist.public,
        "created_at": str(playlist.created_at),
        "tracks": tracks,
    }
    dest.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return dest
