# `crateport convert`

```bash
crateport convert INPUT_FILE [OPTIONS]
```

Reads a VirtualDJ CSV export, enriches every track with an ISRC via Deezer (falling back to MusicBrainz), and writes a Soundiiz-compatible CSV ready for import into Deezer or any other streaming platform.

**Disambiguation:** when multiple candidates are found you are prompted interactively — Enter accepts the top result, a number picks a specific candidate, `s` skips the track (written without ISRC).

## Options

| Option | Default | Description |
|--------|---------|-------------|
| `--name TEXT` | input filename stem | Output file name stem |
| `--output-dir PATH` | `output/` | Directory for the output CSV |
| `--candidates N` | `5` | Deezer search candidates fetched per track |
| `-v / --verbose` | off | Enable debug logging |

## Example

```bash
crateport convert "source_data/2026-03-13 My Set.csv" \
    --name "My_Set_2026-03-13"
```

Output: `output/My_Set_2026-03-13.csv`

## VirtualDJ CSV format

VirtualDJ exports start with a `sep=,` hint line which is stripped automatically. Expected columns (case-insensitive, both German and English names accepted):

| VirtualDJ column | Mapped to |
|------------------|-----------|
| `Titel` / `Title` | `title` |
| `Interpret` / `Artist` | `artist` |
| `Album` | `album` |
| `BPM`, `Key` | *(ignored, not written to output)* |

## ISRC resolution

For each track crateport:

1. Searches Deezer with title + artist (up to `--candidates` results)
2. Auto-matches when exactly one result matches title and artist exactly (case-insensitive)
3. Prompts you to choose when there are multiple plausible candidates
4. Falls back to MusicBrainz if Deezer finds no candidates or the matched track has no ISRC
5. Writes the row without ISRC if nothing is found (no tracks are dropped)

## Importing into Deezer via Soundiiz

1. Run `convert` to produce a CSV in `output/`.
2. Go to [soundiiz.com](https://soundiiz.com) → **Transfer** → **Import from File**.
3. Upload the CSV — Soundiiz matches tracks and pushes them to Deezer.
