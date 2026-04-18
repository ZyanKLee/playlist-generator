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

import logging
import os
import sys
from pathlib import Path

import click

from .config import config
from .converter import parse_vdj_csv, write_soundiiz_csv
from .database import init_db, load_tracks_data
from .deezer_api import DeezerClient
from .exporter import FORMATS, export, export_all
from .input_parser import InputMode, parse_input_file
from .isrc_resolver import resolve_isrc
from .musicbrainz_api import MusicBrainzClient
from .playlist_generator import generate_playlist


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        level=level,
        stream=sys.stderr,
    )


def _safe_stem(name: str) -> str:
    """Convert a playlist name to a safe filename stem."""
    safe = "".join(c if c.isalnum() or c in " -_" else "_" for c in name)
    return safe.strip().replace(" ", "_")[:64] or "playlist"


_FORMAT_CHOICES = list(FORMATS) + ["all"]


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
def cli() -> None:
    """crateport – generate or convert playlists for Deezer / Soundiiz."""


# ---------------------------------------------------------------------------
# generate subcommand
# ---------------------------------------------------------------------------


@cli.command("generate")
@click.argument("input_file", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--mode",
    type=click.Choice([m.value for m in InputMode], case_sensitive=False),
    default=None,
    help="Input mode (auto-detected if omitted).",
)
@click.option(
    "--name", default="Generated Playlist", show_default=True, help="Playlist name."
)
@click.option("--description", default="", help="Playlist description.")
@click.option(
    "--public/--private",
    default=False,
    show_default=True,
    help="Mark playlist public in metadata.",
)
@click.option(
    "--limit",
    default=10,
    show_default=True,
    metavar="N",
    help="Max tracks fetched per artist / album.",
)
@click.option(
    "--format",
    "fmt",
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
@click.option(
    "-v", "--verbose", is_flag=True, default=False, help="Enable debug logging."
)
def generate(  # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals
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
        os.environ["DATABASE_URL"] = db_url

    out_dir = output_dir or config.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    init_db()
    logger.info("Database ready at %s", config.db_url)

    input_mode = InputMode(mode) if mode else None
    parsed = parse_input_file(input_file, mode=input_mode)
    n_entries = len(parsed.artists) or len(parsed.albums) or len(parsed.tracks)
    click.echo(
        f"Parsed {input_file.name}: mode={parsed.mode.value}, entries={n_entries}"
    )

    playlist = generate_playlist(
        parsed,
        name=name,
        description=description,
        public=public,
        limit_per_source=limit,
    )

    tracks_data = load_tracks_data(playlist.id)
    click.echo(
        f"Playlist '{playlist.name}' built: {len(tracks_data)} tracks (db id={playlist.id})"
    )

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
@click.option(
    "--name",
    default=None,
    help="Playlist/output file name stem (default: input filename).",
)
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
@click.option(
    "-1",
    "--always-select-first",
    is_flag=True,
    default=False,
    help="Non-interactively always pick the first candidate (no prompt).",
)
@click.option(
    "-v", "--verbose", is_flag=True, default=False, help="Enable debug logging."
)
def convert(  # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals
    input_file: Path,
    name: str | None,
    output_dir: Path | None,
    candidates: int,
    always_select_first: bool,
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

    rows = parse_vdj_csv(input_file)
    click.echo(f"Loaded {len(rows)} tracks from {input_file.name}")

    deezer = DeezerClient()
    mb = MusicBrainzClient()

    enriched: list[dict[str, str]] = []
    for i, row in enumerate(rows, 1):
        title: str = row["title"]
        artist: str = row["artist"]
        album: str = row["album"]

        click.echo(f"\n[{i}/{len(rows)}] {artist} – {title}")

        isrc = resolve_isrc(title, artist, deezer, mb, candidates, always_select_first)

        if isrc:
            click.echo(f"  ✓ ISRC: {isrc}")
        else:
            click.echo("  – No ISRC found, row will be written without one.")

        enriched.append(
            {"title": title, "artist": artist, "album": album, "isrc": isrc or ""}
        )

    stem = _safe_stem(name or input_file.stem)
    out_path = out_dir / f"{stem}.csv"
    write_soundiiz_csv(enriched, out_path)
    click.echo(f"\nWrote {len(enriched)} tracks → {out_path}")
    click.echo("\nTo import into Soundiiz:")
    click.echo("  1. Go to soundiiz.com → Transfer → Import from File")
    click.echo(f"  2. Upload: {out_path}")


if __name__ == "__main__":
    cli()
