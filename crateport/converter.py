"""VirtualDJ CSV parser and Soundiiz CSV writer for the convert command."""

from __future__ import annotations

import csv
from pathlib import Path


def parse_vdj_csv(path: Path) -> list[dict[str, str]]:
    """Parse a VirtualDJ CSV export into a list of track dicts.

    VirtualDJ exports start with a ``sep=,`` hint line which we skip.
    Expected columns (case-insensitive): Titel/Title, Interpret/Artist, Album.
    """
    text = path.read_text(encoding="utf-8-sig")
    lines = text.splitlines()

    if lines and lines[0].strip().lower().startswith("sep="):
        lines = lines[1:]

    reader = csv.DictReader(lines)
    if reader.fieldnames is None:
        return []

    _col_map = {
        "titel": "title",
        "title": "title",
        "interpret": "artist",
        "artist": "artist",
        "album": "album",
        "bpm": "bpm",
        "key": "key",
    }

    rows: list[dict[str, str]] = []
    for raw in reader:
        row: dict[str, str] = {}
        for k, v in raw.items():
            norm = _col_map.get((k or "").strip().lower())
            if norm:
                row[norm] = (v or "").strip()
        if row.get("title"):
            row.setdefault("artist", "")
            row.setdefault("album", "")
            rows.append(row)
    return rows


def write_soundiiz_csv(tracks: list[dict[str, str]], path: Path) -> None:
    """Write *tracks* as a Soundiiz-compatible CSV (title, artist, album, isrc)."""
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["title", "artist", "album", "isrc"])
        writer.writeheader()
        writer.writerows(tracks)
