# crateport

A DJ-focused playlist tool with two workflows:

- **`generate`** — build a playlist from a list of artists, albums, or tracks using the Deezer public API, then export it to XSPF / M3U / CSV / JSON.
- **`convert`** — take a VirtualDJ CSV export, enrich every track with an ISRC via Deezer (falling back to MusicBrainz), and produce a Soundiiz-compatible CSV ready for import into Deezer or any other streaming platform.

No Deezer application credentials required. API responses are cached locally in SQLite.

---

## Requirements

- Python ≥ 3.14
- [Poetry](https://python-poetry.org/) for dependency management

---

## Installation

```bash
git clone https://github.com/ZyanKLee/crateport.git
cd crateport
poetry install
```

---

## Usage

```bash
poetry run python -m src COMMAND [OPTIONS] INPUT_FILE
```

### Commands

| Command | Description |
|---------|-------------|
| `generate` | Resolve artists / albums / tracks via Deezer and export a playlist |
| `convert` | Convert a VirtualDJ CSV export to a Soundiiz-importable CSV with ISRC |

---

## `generate`

```bash
poetry run python -m src generate INPUT_FILE [OPTIONS]
```

Queries the Deezer public API to resolve each entry in `INPUT_FILE` to real tracks, caches results locally, and exports the playlist.

### Options

| Option | Default | Description |
|--------|---------|-------------|
| `--mode [artists\|albums\|tracks]` | auto-detected | Force a specific input mode |
| `--name TEXT` | `Generated Playlist` | Playlist name (used in filenames and embedded metadata) |
| `--description TEXT` | *(empty)* | Playlist description embedded in exported files |
| `--public / --private` | `--private` | Mark the playlist as public or private in exported metadata |
| `--limit N` | `10` | Maximum tracks fetched per artist or album |
| `--format [xspf\|m3u\|csv\|json\|all]` | `all` | Output format(s) |
| `--output-dir PATH` | `output/` | Directory for all output files |
| `--db-url TEXT` | SQLite in `output/` | Override the database URL |
| `-v / --verbose` | off | Enable debug logging |

### Examples

```bash
# Generate from an artist list, export all formats (default)
poetry run python -m src generate source_data/artists.txt

# Custom name and track limit
poetry run python -m src generate source_data/artists.txt \
    --name "My Techno Mix" --limit 15

# Export only the Deezer-importable CSV
poetry run python -m src generate source_data/artists.txt --format csv

# Albums CSV input, export as XSPF
poetry run python -m src generate source_data/albums.csv --mode albums --format xspf
```

### Input formats for `generate`

The format is auto-detected from the file header. Use `--mode` to override.

**Artists — plain text (one name per line)**
```
ADAM BEYER
BLAZY
Charlotte de Witte
```

**Artists — CSV with header**
```csv
artist
ADAM BEYER
BLAZY
```
Fetches the top N tracks (controlled by `--limit`) for each artist.

**Albums — CSV**
```csv
title,artist
Ricochet,ADAM BEYER
Fuse 30,Various Artists
```
Optional extra column: `upc`. Fetches all tracks from each matched album.

**Tracks — CSV**
```csv
title,artist,album,isrc
Kinsman,ADAM BEYER,Kinsman,
Red Nail,Charlotte de Witte,Doppler,BEBE12345678
```
Only `title` is required. `isrc` is used as an exact identifier when present.

### Output formats

All files land in `output/` (or `--output-dir`). Filename stem comes from `--name`.

| Format | Extension | Description |
|--------|-----------|-------------|
| `csv`  | `.csv`    | Soundiiz / Deezer import CSV (`title, artist, album, isrc`) |
| `xspf` | `.xspf`   | XML Shareable Playlist Format v1 — VLC, foobar2000, etc. |
| `m3u`  | `.m3u8`   | Extended M3U with `#EXTINF` metadata |
| `json` | `.json`   | Full machine-readable dump of the playlist and track metadata |

### Importing into Deezer

Deezer does not currently accept new application registrations, so direct API push is not available. Instead:

1. Run with `--format csv` (included in the default `all`).
2. Open [deezer.com](https://www.deezer.com) → **My Music** → **Import tracks**.
3. Upload the `.csv` file from `output/`.

Deezer matches by ISRC first, then falls back to title + artist.

---

## `convert`

```bash
poetry run python -m src convert INPUT_FILE [OPTIONS]
```

Reads a VirtualDJ CSV export (columns: `Titel`, `Interpret`, `Album`, `BPM`, `Key`), looks up each track on Deezer and MusicBrainz to obtain its ISRC, and writes a Soundiiz-compatible CSV.

**Disambiguation:** when multiple candidates are found you are prompted interactively — Enter accepts the top result, a number picks a specific candidate, `s` skips the track (written without ISRC).

### Options

| Option | Default | Description |
|--------|---------|-------------|
| `--name TEXT` | input filename stem | Output file name stem |
| `--output-dir PATH` | `output/` | Directory for the output CSV |
| `--candidates N` | `5` | Deezer search candidates fetched per track |
| `-v / --verbose` | off | Enable debug logging |

### Example

```bash
poetry run python -m src convert "source_data/2026-03-13 My Set.csv" \
    --name "My_Set_2026-03-13"
```

Output: `output/My_Set_2026-03-13.csv`

### VirtualDJ CSV format

VirtualDJ exports start with a `sep=,` hint line which is stripped automatically. Expected columns (case-insensitive, both German and English names accepted):

| VirtualDJ | Mapped to |
|-----------|-----------|
| `Titel` / `Title` | `title` |
| `Interpret` / `Artist` | `artist` |
| `Album` | `album` |
| `BPM`, `Key` | *(ignored, not written to output)* |

### Importing into Deezer via Soundiiz

1. Run `convert` to produce a CSV in `output/`.
2. Go to [soundiiz.com](https://soundiiz.com) → **Transfer** → **Import from File**.
3. Upload the CSV — Soundiiz matches tracks and pushes them to Deezer.

---

## Caching

API responses (Deezer + MusicBrainz) are cached in `output/cache.db` (SQLite) for **24 hours** by default. Re-running within that window makes zero API calls.

Control the TTL via `CACHE_TTL_HOURS` (see [Configuration](#configuration)).

---

## Configuration

Copy `.env.example` to `.env` and adjust as needed. All values are optional.

```bash
cp .env.example .env
```

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite:///output/cache.db` | SQLAlchemy database URL — switch to `postgresql+psycopg2://…` for PostgreSQL |
| `CACHE_TTL_HOURS` | `24` | How long cached API responses remain valid (hours) |
| `MUSICBRAINZ_USER_AGENT` | built-in | User-Agent sent to MusicBrainz (identify your instance) |
| `DEEZER_APP_ID` | *(empty)* | Reserved for future direct Deezer push (not required for file export) |
| `DEEZER_SECRET` | *(empty)* | Reserved for future direct Deezer push |
| `DEEZER_REDIRECT_URI` | `http://localhost:8080/callback` | OAuth callback URI |

---

## Project structure

```
crateport/
├── src/
│   ├── cli.py                 # Click CLI – 'generate' and 'convert' subcommands
│   ├── config.py              # Environment-based configuration
│   ├── models.py              # SQLAlchemy ORM models (Artist, Album, Track, Playlist)
│   ├── database.py            # Engine, session factory, cache TTL helpers
│   ├── deezer_api.py          # Deezer public API client with caching
│   ├── musicbrainz_api.py     # MusicBrainz API client (ISRC fallback)
│   ├── input_parser.py        # Input file parsing & auto-detection
│   ├── playlist_generator.py  # Resolves entries → Track objects, persists playlist
│   ├── exporter.py            # XSPF / M3U / CSV / JSON writers
│   └── auth.py                # Deezer OAuth flow (for future use)
├── source_data/               # Put your input files here
├── output/                    # Generated playlists and cache.db land here
├── docs/
│   └── project_plan.md
├── .env.example
├── pyproject.toml
└── README.md
```

---

## License

MIT
