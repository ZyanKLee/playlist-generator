# Contributing

## Project structure

```
crateport/
├── crateport/
│   ├── cli.py                 # Click CLI – 'generate' and 'convert' subcommands
│   ├── config.py              # Environment-based configuration (CWD-relative paths)
│   ├── models.py              # SQLAlchemy ORM models (Artist, Album, Track, Playlist)
│   ├── database.py            # Engine, session factory, cache TTL helpers
│   ├── deezer_api.py          # Deezer public API client with caching
│   ├── musicbrainz_api.py     # MusicBrainz API client (ISRC fallback)
│   ├── input_parser.py        # Input file parsing & auto-detection
│   ├── playlist_generator.py  # Resolves entries → Track objects, persists playlist
│   ├── exporter.py            # XSPF / M3U / CSV / JSON writers
│   └── auth.py                # Deezer OAuth flow (for future use)
├── docs/
│   ├── generate.md            # generate subcommand reference
│   └── convert.md             # convert subcommand reference
├── source_data/               # Put your input files here (git-ignored)
├── output/                    # Generated playlists and cache.db (git-ignored)
├── .env.example
├── pyproject.toml
├── CONTRIBUTING.md
└── README.md
```

## Development setup

```bash
git clone https://github.com/ZyanKLee/crateport.git
cd crateport
poetry install
```

Run the CLI directly without installing:

```bash
poetry run crateport --help
```

## Code style

```bash
poetry run black crateport/
poetry run isort crateport/
poetry run pylint crateport/
```

## Updating the installed version

After making changes, reinstall with pipx:

```bash
pipx install . --force
```
