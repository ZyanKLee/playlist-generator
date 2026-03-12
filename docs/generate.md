# `crateport generate`

```bash
crateport generate INPUT_FILE [OPTIONS]
```

Queries the Deezer public API to resolve each entry in `INPUT_FILE` to real tracks, caches results locally, and exports the playlist.

## Options

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

## Examples

```bash
# Generate from an artist list, export all formats (default)
crateport generate source_data/artists.txt

# Custom name and track limit
crateport generate source_data/artists.txt \
    --name "My Techno Mix" --limit 15

# Export only the Deezer-importable CSV
crateport generate source_data/artists.txt --format csv

# Albums CSV input, export as XSPF
crateport generate source_data/albums.csv --mode albums --format xspf
```

## Input formats

The format is auto-detected from the file header. Use `--mode` to override.

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

Fetches the top N tracks (controlled by `--limit`) for each artist.

### Albums — CSV

```csv
title,artist
Ricochet,ADAM BEYER
Fuse 30,Various Artists
```

Optional extra column: `upc`. Fetches all tracks from each matched album.

### Tracks — CSV

```csv
title,artist,album,isrc
Kinsman,ADAM BEYER,Kinsman,
Red Nail,Charlotte de Witte,Doppler,BEBE12345678
```

Only `title` is required. `isrc` is used as an exact identifier when present.

## Output formats

All files land in `output/` (or `--output-dir`). The filename stem is derived from `--name`.

| Format | Extension | Description |
|--------|-----------|-------------|
| `csv`  | `.csv`    | Soundiiz / Deezer import CSV (`title, artist, album, isrc`) |
| `xspf` | `.xspf`   | XML Shareable Playlist Format v1 — VLC, foobar2000, etc. |
| `m3u`  | `.m3u8`   | Extended M3U with `#EXTINF` metadata |
| `json` | `.json`   | Full machine-readable dump of the playlist and track metadata |

## Importing into Deezer

Deezer does not currently accept new application registrations, so direct API push is not available. Instead:

1. Run with `--format csv` (included in the default `all`).
2. Open [deezer.com](https://www.deezer.com) → **My Music** → **Import tracks**.
3. Upload the `.csv` file from `output/`.

Deezer matches by ISRC first, then falls back to title + artist.
