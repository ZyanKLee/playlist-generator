"""Command-line interface.

Usage examples
--------------
Generate a playlist from an artist list and export to all formats::

    python -m src generate source_data/artists_test.txt

Export only CSV (for Deezer manual import)::

    python -m src generate source_data/artists_test.txt --format csv

Convert a VirtualDJ CSV export to Soundiiz-compatible CSV (with ISRC)::

    python -m src convert "source_data/my set.csv" --name "My Set"

How to import into Deezer via Soundiiz
---------------------------------------
1. Run ``convert`` to produce a Soundiiz CSV in ``output/``.
2. Import the CSV into Soundiiz (Transfer → Import from File).
3. Soundiiz will match tracks and push them to your Deezer account.
"""

from __future__ import annotations

import csv
import logging
import sys
from pathlib import Path
from typing import Any

import click

from .config import config
from .database import get_session, init_db
from .exporter import FORMATS, export, export_all
from .input_parser import InputMode, parse_input_file
from .models import Album, Artist, Track, playlist_tracks
from .playlist_generator import generate_playlist


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        level=level,
        stream=sys.stderr,
    )


_FORMAT_CHOICES = list(FORMATS) + ["all"]


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
def cli() -> None:
    """Playlist generator – generate or convert playlists for Deezer / Soundiiz."""


# ---------------------------------------------------------------------------
# generate subcommand (original behaviour)
# ---------------------------------------------------------------------------

@cli.command("generate")
@click.argument("input_file", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--mode",
    type=click.Choice([m.value for m in InputMode], case_sensitive=False),
    default=None,
    help="Input mode (auto-detected if omitted).",
)
@click.option("--name", default="Generated Playlist", show_default=True, help="Playlist name.")
@click.option("--description", default="", help="Playlist description.")
@click.option("--public/--private", default=False, show_default=True, help="Mark playlist public in metadata.")
@click.option(
    "--limit",
    default=10,
    show_default=True,
    metavar="N",
    help="Max tracks fetched per artist / album.",
)
@click.option(
    "--format", "fmt",
    type=click.Choice(_FORMAT_CHOICES, case_sensitive=False),
    default="all",
    show_default=True,
    help=(
        "Output format(s).  "
        "'all' writes XSPF, M3U, CSV, and JSON simultaneously.  "
        "CSV is the easiest to import into Deezer manually."
    ),
)
@click.option(
    "--output-dir",
    type=click.Path(path_type=Path),
    default=None,
    help="Directory for output files (default: output/).",
)
@click.option(
    "--db-url",
    default=None,
    help="Override DATABASE_URL from .env.",
)
@click.option("-v", "--verbose", is_flag=True, default=False, help="Enable debug logging.")
def generate(
    input_file: Path,
    mode: str | None,
    name: str,
    description: str,
    public: bool,
    limit: int,
    fmt: str,
    output_dir: Path | None,
    db_url: str | None,
    verbose: bool,
) -> None:
    """Generate a playlist from INPUT_FILE and export it to standard formats.

    INPUT_FILE may be a plain-text list of artist names (one per line) or a
    CSV file with columns appropriate for the chosen --mode.

    \b
    Importing into Deezer (no app registration needed):
      1. Use --format csv  (included in the default 'all')
      2. Go to deezer.com -> My Music -> Import tracks
      3. Upload the CSV from output/
    """
    _setup_logging(verbose)
    logger = logging.getLogger(__name__)

    if db_url:
        import os
        os.environ["DATABASE_URL"] = db_url

    out_dir = output_dir or config.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    init_db()
    logger.info("Database ready at %s", config.db_url)

    input_mode = InputMode(mode) if mode else None
    parsed = parse_input_file(input_file, mode=input_mode)
    n_entries = len(parsed.artists) or len(parsed.albums) or len(parsed.tracks)
    click.echo(f"Parsed {input_file.name}: mode={parsed.mode.value}, entries={n_entries}")

    playlist = generate_playlist(
        parsed,
        name=name,
        description=description,
        public=public,
        limit_per_source=limit,
    )

    tracks_data = _load_tracks_data(playlist.id)
    click.echo(f"Playlist '{playlist.name}' built: {len(tracks_data)} tracks (db id={playlist.id})")

    stem = _safe_stem(name)
    if fmt == "all":
        paths = export_all(playlist, tracks_data, output_dir=out_dir, stem=stem)
        for f, p in paths.items():
            click.echo(f"  [{f.upper():4s}] {p}")
    else:
        p = export(playlist, tracks_data, fmt=fmt, output_dir=out_dir, stem=stem)
        click.echo(f"  [{fmt.upper():4s}] {p}")

    csv_path = out_dir / f"{stem}.csv"
    click.echo()
    click.echo("To import into Deezer:")
    click.echo("  1. Open https://www.deezer.com -> My Music -> Import tracks")
    click.echo(f"  2. Upload: {csv_path}")


# ---------------------------------------------------------------------------
# convert subcommand – VirtualDJ CSV → Soundiiz CSV with ISRC enrichment
# ---------------------------------------------------------------------------

@cli.command("convert")
@click.argument("input_file", type=click.Path(exists=True, path_type=Path))
@click.option("--name", default=None, help="Playlist/output file name stem (default: input filename).")
@click.option(
    "--output-dir",
    type=click.Path(path_type=Path),
    default=None,
    help="Directory for output files (default: output/).",
)
@click.option(
    "--candidates",
    default=5,
    show_default=True,
    metavar="N",
    help="Number of Deezer search candidates to fetch per track.",
)
@click.option("-v", "--verbose", is_flag=True, default=False, help="Enable debug logging.")
def convert(
    input_file: Path,
    name: str | None,
    output_dir: Path | None,
    candidates: int,
    verbose: bool,
) -> None:
    """Convert a VirtualDJ CSV export to a Soundiiz-compatible CSV with ISRC.

    Reads INPUT_FILE (VirtualDJ CSV with Titel/Interpret/Album/BPM/Key columns),
    enriches every track with an ISRC via Deezer (falling back to MusicBrainz),
    and writes a CSV with title,artist,album,isrc columns ready for Soundiiz import.

    When multiple candidates are found you will be prompted to pick the correct
    one.  Press Enter to accept the top result, or type a number to choose.
    Type 's' to skip a track (writes row without ISRC).
    """
    _setup_logging(verbose)

    out_dir = output_dir or config.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = _parse_vdj_csv(input_file)
    click.echo(f"Loaded {len(rows)} tracks from {input_file.name}")

    from .deezer_api import DeezerClient
    from .musicbrainz_api import MusicBrainzClient

    deezer = DeezerClient()
    mb = MusicBrainzClient()

    enriched: list[dict[str, str]] = []
    for i, row in enumerate(rows, 1):
        title: str = row["title"]
        artist: str = row["artist"]
        album: str = row["album"]

        click.echo(f"\n[{i}/{len(rows)}] {artist} – {title}")

        isrc = _resolve_isrc(title, artist, deezer, mb, candidates)

        if isrc:
            click.echo(f"  ✓ ISRC: {isrc}")
        else:
            click.echo("  – No ISRC found, row will be written without one.")

        enriched.append({"title": title, "artist": artist, "album": album, "isrc": isrc or ""})

    stem = _safe_stem(name or input_file.stem)
    out_path = out_dir / f"{stem}.csv"
    _write_soundiiz_csv(enriched, out_path)
    click.echo(f"\nWrote {len(enriched)} tracks → {out_path}")
    click.echo("\nTo import into Soundiiz:")
    click.echo("  1. Go to soundiiz.com → Transfer → Import from File")
    click.echo(f"  2. Upload: {out_path}")


# ---------------------------------------------------------------------------
# VirtualDJ CSV parser
# ---------------------------------------------------------------------------

def _parse_vdj_csv(path: Path) -> list[dict[str, str]]:
    """Parse a VirtualDJ CSV export into a list of track dicts.

    VirtualDJ exports start with a ``sep=,`` hint line which we skip.
    Expected columns (case-insensitive): Titel/Title, Interpret/Artist,
    Album, BPM, Key.
    """
    text = path.read_text(encoding="utf-8-sig")
    lines = text.splitlines()

    # Drop the leading ``sep=,`` line if present
    if lines and lines[0].strip().lower().startswith("sep="):
        lines = lines[1:]

    reader = csv.DictReader(lines)
    # Normalise header names: strip quotes/whitespace, lower-case
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


# ---------------------------------------------------------------------------
# ISRC resolution with interactive disambiguation
# ---------------------------------------------------------------------------

def _resolve_isrc(
    title: str,
    artist: str,
    deezer: Any,
    mb: Any,
    n_candidates: int,
) -> str | None:
    """Search Deezer (then MusicBrainz) and return an ISRC, prompting when ambiguous."""

    # --- Deezer ---
    candidates = deezer.search_track_candidates(title, artist, limit=n_candidates)

    if candidates:
        chosen = _pick_candidate(candidates, title, artist, source="Deezer")
        if chosen is not None:
            # Fetch full track object to get ISRC
            full = deezer.get_track(chosen["id"])
            if full and full.isrc:
                return full.isrc
            # If Deezer has the track but no ISRC, fall through to MusicBrainz

    # --- MusicBrainz fallback ---
    click.echo("  → Trying MusicBrainz…")
    mb_results = mb.search_recording(title, artist, limit=n_candidates)
    if not mb_results:
        return None

    chosen_mb = _pick_mb_candidate(mb_results, title, artist)
    if chosen_mb is None:
        return None
    isrcs: list[str] = chosen_mb.get("isrcs", [])
    return isrcs[0] if isrcs else None


def _pick_candidate(candidates: list[dict], title: str, artist: str, source: str) -> dict | None:
    """Interactively let the user choose among Deezer *candidates*.

    Returns the chosen dict, or ``None`` if the user skips.
    Automatically accepts when there is exactly one candidate that matches
    title and artist exactly (case-insensitive).
    """
    # Try an automatic exact match first
    tl = title.casefold()
    al = artist.casefold()
    exact = [
        c for c in candidates
        if c.get("title", "").casefold() == tl
        and (not al or c.get("artist", {}).get("name", "").casefold() == al)
    ]
    if len(exact) == 1:
        c = exact[0]
        click.echo(
            f"  → Auto-matched [{source}]: {c.get('artist', {}).get('name', '?')} – {c.get('title', '?')}"
        )
        return c

    # Prompt the user
    click.echo(f"  Candidates from {source}:")
    for idx, c in enumerate(candidates, 1):
        a_name = c.get("artist", {}).get("name", "?")
        alb_name = c.get("album", {}).get("title", "?")
        click.echo(f"    [{idx}] {a_name} – {c.get('title', '?')}  (album: {alb_name})")

    while True:
        raw = click.prompt(
            "  Pick number, Enter=1, s=skip",
            default="1",
            show_default=False,
        ).strip().lower()
        if raw == "s":
            return None
        try:
            n = int(raw)
            if 1 <= n <= len(candidates):
                return candidates[n - 1]
        except ValueError:
            pass
        click.echo("  Invalid choice, try again.")


def _pick_mb_candidate(recordings: list[dict], title: str, artist: str) -> dict | None:
    """Interactively let the user choose among MusicBrainz *recordings*."""
    # Filter to those with ISRCs only – no point picking one without
    with_isrc = [r for r in recordings if r.get("isrcs")]
    pool = with_isrc or recordings

    if not pool:
        return None

    tl = title.casefold()
    al = artist.casefold()
    exact = [
        r for r in pool
        if r.get("title", "").casefold() == tl
        and (
            not al
            or any(
                ac.get("artist", {}).get("name", "").casefold() == al
                for ac in r.get("artist-credit", [])
                if isinstance(ac, dict)
            )
        )
    ]
    if len(exact) == 1:
        r = exact[0]
        credit = " / ".join(
            ac.get("artist", {}).get("name", "")
            for ac in r.get("artist-credit", [])
            if isinstance(ac, dict)
        )
        click.echo(f"  → Auto-matched [MusicBrainz]: {credit} – {r.get('title', '?')}")
        return r

    click.echo("  Candidates from MusicBrainz:")
    for idx, r in enumerate(pool, 1):
        credit = " / ".join(
            ac.get("artist", {}).get("name", "")
            for ac in r.get("artist-credit", [])
            if isinstance(ac, dict)
        )
        isrcs = r.get("isrcs", [])
        isrc_str = isrcs[0] if isrcs else "no ISRC"
        click.echo(f"    [{idx}] {credit} – {r.get('title', '?')}  ({isrc_str})")

    while True:
        raw = click.prompt(
            "  Pick number, Enter=1, s=skip",
            default="1",
            show_default=False,
        ).strip().lower()
        if raw == "s":
            return None
        try:
            n = int(raw)
            if 1 <= n <= len(pool):
                return pool[n - 1]
        except ValueError:
            pass
        click.echo("  Invalid choice, try again.")


# ---------------------------------------------------------------------------
# Soundiiz CSV writer
# ---------------------------------------------------------------------------

def _write_soundiiz_csv(tracks: list[dict[str, str]], path: Path) -> None:
    """Write *tracks* as a Soundiiz-compatible CSV (title,artist,album,isrc)."""
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["title", "artist", "album", "isrc"])
        writer.writeheader()
        writer.writerows(tracks)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_tracks_data(playlist_id: int) -> list[dict]:
    """Return ordered track dicts for *playlist_id* with artist/album names resolved."""
    rows: list[dict] = []
    with get_session() as db:
        result = db.execute(
            playlist_tracks.select()
            .where(playlist_tracks.c.playlist_id == playlist_id)
            .order_by(playlist_tracks.c.position)
        ).fetchall()

        for row in result:
            t: Track | None = db.get(Track, row.track_id)
            if t is None:
                continue
            artist_name = ""
            if t.artist_id:
                a: Artist | None = db.get(Artist, t.artist_id)
                artist_name = a.name if a else ""
            album_title = ""
            if t.album_id:
                al: Album | None = db.get(Album, t.album_id)
                album_title = al.title if al else ""
            rows.append(
                {
                    "id": t.id,
                    "title": t.title,
                    "artist": artist_name,
                    "album": album_title,
                    "duration": t.duration,
                    "isrc": t.isrc,
                    "rank": t.rank,
                    "preview": t.preview,
                    "link": t.link,
                }
            )
    return rows


def _safe_stem(name: str) -> str:
    """Convert a playlist name to a safe filename stem."""
    safe = "".join(c if c.isalnum() or c in " -_" else "_" for c in name)
    return safe.strip().replace(" ", "_")[:64] or "playlist"


if __name__ == "__main__":
    cli()
