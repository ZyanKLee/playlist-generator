"""Command-line interface.

Usage examples
--------------
Generate a playlist from an artist list and export to all formats::

    python -m src source_data/artists_test.txt

Export only CSV (for Deezer manual import)::

    python -m src source_data/artists_test.txt --format csv

Specify playlist metadata::

    python -m src source_data/artists_test.txt \\
        --name "My Mix" --description "Auto-generated" --format xspf

Force a specific input mode::

    python -m src tracks.csv --mode tracks --limit 5

How to import into Deezer
--------------------------
1. Run with ``--format csv`` (or the default ``--format all``).
2. Open https://www.deezer.com → *My Music* → *Import tracks*.
3. Upload the generated CSV from ``output/``.
Deezer matches tracks by ISRC first, then by title + artist.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

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


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
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
    help=f"Directory for output files (default: output/).",
)
@click.option(
    "--db-url",
    default=None,
    help="Override DATABASE_URL from .env.",
)
@click.option("-v", "--verbose", is_flag=True, default=False, help="Enable debug logging.")
def cli(
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
