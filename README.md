# playlist-generator

Generate playlists from a list of artists, albums, or tracks using the **Deezer public API** — no application credentials required. Results are cached locally in SQLite and exported to standard playlist formats that can be imported into Deezer (or opened in any media player).

---

## How it works

1. You provide an input file (artist names, album list, or track list).
2. The tool queries the [Deezer public API](https://developers.deezer.com/api) to resolve each entry to actual tracks.
3. Resolved data is cached in `output/cache.db` (SQLite) to avoid redundant API calls.
4. The playlist is saved to `output/` in one or more standard formats.

### Importing into Deezer (no API key needed)

Deezer does not currently accept new application registrations, so direct API submission is not available. However, Deezer supports manual track import:

1. Run the tool with `--format csv` (or the default `--format all`).
2. Open [deezer.com](https://www.deezer.com) → **My Music** → **Import tracks**.
3. Upload the generated `.csv` file from `output/`.

Deezer matches tracks by ISRC first (exact match), then falls back to title + artist.

---

## Requirements

- Python ≥ 3.14
- [Poetry](https://python-poetry.org/) for dependency management

---

## Installation

```bash
git clone https://github.com/your-username/playlist-generator.git
cd playlist-generator
poetry install
```

---

## Usage

```bash
poetry run python -m src INPUT_FILE [OPTIONS]
```

### Arguments

| Argument | Description |
|----------|-------------|
| `INPUT_FILE` | Path to the input file (see [Input formats](#input-formats) below) |

### Options

| Option | Default | Description |
|--------|---------|-------------|
| `--mode [artists\|albums\|tracks]` | auto-detected | Force a specific input mode |
| `--name TEXT` | `Generated Playlist` | Playlist name (used in output filenames and metadata) |
| `--description TEXT` | *(empty)* | Playlist description embedded in exported files |
| `--public / --private` | `--private` | Mark the playlist as public or private in exported metadata |
| `--limit N` | `10` | Maximum tracks fetched per artist or album |
| `--format [xspf\|m3u\|csv\|json\|all]` | `all` | Output format(s) |
| `--output-dir PATH` | `output/` | Directory for all output files |
| `--db-url TEXT` | SQLite in `output/` | Override the database URL (e.g. for PostgreSQL) |
| `-v / --verbose` | off | Enable debug logging |
| `-h / --help` | | Show help message |

### Examples

```bash
# Generate from an artist list, export all formats (default)
poetry run python -m src source_data/artists_test.txt

# Custom playlist name and limit
poetry run python -m src source_data/artists_test.txt \
    --name "My Techno Mix" --description "Top tracks" --limit 15

# Export only the Deezer-importable CSV
poetry run python -m src source_data/artists_test.txt --format csv

# Albums CSV input, export as XSPF
poetry run python -m src source_data/albums.csv --mode albums --format xspf

# Use PostgreSQL instead of SQLite
poetry run python -m src source_data/artists.txt \
    --db-url "postgresql+psycopg2://user:pass@localhost/playlist"

# Debug mode
poetry run python -m src source_data/artists_test.txt -v
```

---

## Input formats

The input file is auto-detected. You can also force a mode with `--mode`.

### Artists — plain text (one name per line)

```
ADAM BEYER
BLAZY
Charlotte de Witte
```

### Artists — CSV with header

```csv
artist
ADAM BEYER
BLAZY
```

The tool fetches the top N tracks (controlled by `--limit`) for each artist.

### Albums — CSV

```csv
title,artist
Ricochet,ADAM BEYER
Fuse 30,Various Artists
```

Optional extra column: `upc`

The tool fetches all tracks from each matched album.

### Tracks — CSV

```csv
title,artist,album,isrc
Kinsman,ADAM BEYER,Kinsman,
Red Nail,Charlotte de Witte,Doppler,BEBE12345678
```

Only `title` is required; `artist`, `album`, and `isrc` improve match accuracy. When `isrc` is present it is used as an exact identifier.

---

## Output formats

All files are written to `output/` (or the directory given by `--output-dir`). The filename stem is derived from `--name`.

| Format | Extension | Description |
|--------|-----------|-------------|
| `csv`  | `.csv`    | Deezer import-compatible CSV (title, artist, album, isrc) |
| `xspf` | `.xspf`   | XML Shareable Playlist Format v1 — VLC, foobar2000, etc. |
| `m3u`  | `.m3u8`   | Extended M3U with `#EXTINF` metadata |
| `json` | `.json`   | Full machine-readable dump of the playlist and all track metadata |

---

## Caching

API responses are cached in `output/cache.db` (SQLite). Cached entries are considered fresh for **24 hours** by default. Re-running the tool within that window makes zero API calls.

Cache TTL can be changed via the `CACHE_TTL_HOURS` environment variable (see [Configuration](#configuration)).

---

## Configuration

Copy `.env.example` to `.env` and adjust as needed. All values are optional.

```bash
cp .env.example .env
```

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite:///output/cache.db` | SQLAlchemy database URL. Change to a `postgresql+psycopg2://…` URL to use PostgreSQL. |
| `CACHE_TTL_HOURS` | `24` | How long cached API responses remain valid |
| `DEEZER_APP_ID` | *(empty)* | Reserved for future direct Deezer submission (not required for file export) |
| `DEEZER_SECRET` | *(empty)* | Reserved for future direct Deezer submission |
| `DEEZER_REDIRECT_URI` | `http://localhost:8080/callback` | OAuth callback URI |

---

## Project structure

```
playlist-generator/
├── src/
│   ├── config.py           # Environment-based configuration
│   ├── models.py           # SQLAlchemy ORM models (Artist, Album, Track, Playlist)
│   ├── database.py         # Engine, session factory, cache TTL helpers
│   ├── deezer_api.py       # Deezer public API client with caching
│   ├── input_parser.py     # Input file parsing & auto-detection
│   ├── playlist_generator.py  # Resolves entries → Track objects, persists playlist
│   ├── exporter.py         # XSPF / M3U / CSV / JSON writers
│   ├── auth.py             # Deezer OAuth flow (for future use)
│   └── cli.py              # Click CLI entry point
├── source_data/            # Put your input files here
├── output/                 # Generated playlists and cache.db land here
├── docs/
│   └── project_plan.md
├── .env.example
├── pyproject.toml
└── README.md
```

---

## License

MIT
