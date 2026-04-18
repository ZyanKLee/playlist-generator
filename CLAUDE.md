# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**crateport** is a DJ-focused Python CLI tool (Python ≥3.14) for generating and converting music playlists. Two main workflows:

- **`generate`** — Build playlists from artist/album/track lists using the Deezer public API; export to XSPF, M3U, CSV, or JSON
- **`convert`** — Transform VirtualDJ CSV exports into Soundiiz-compatible CSVs with ISRC enrichment via Deezer and MusicBrainz

## Commands

```bash
# Install dependencies
poetry install

# Run CLI
poetry run crateport --help

# Format / lint (also run automatically by lefthook pre-commit hook)
poetry run black crateport/
poetry run isort crateport/
poetry run pylint crateport/

# Run all pre-commit checks via lefthook
lefthook run pre-commit
```

There are currently no automated tests. `lefthook.yml` has commented-out stubs for pytest, mypy, and bandit if they are added in future.

## Architecture

```
CLI Entry Point (cli.py)
├── generate command
│   ├── input_parser.py     — auto-detects artists list / album CSV / track CSV
│   ├── playlist_generator.py — resolves parsed entries to Track objects; persists playlist
│   │   ├── deezer_api.py   — Deezer public API client; caches results
│   │   ├── musicbrainz_api.py — MusicBrainz v2 client for ISRC fallback
│   │   └── database.py + models.py — SQLAlchemy ORM + session/cache logic
│   └── exporter.py         — writes XSPF / M3U / CSV / JSON
└── convert command
    ├── converter.py        — parse VirtualDJ CSV; write Soundiiz CSV
    └── isrc_resolver.py    — interactive ISRC lookup (Deezer → MusicBrainz fallback)
```

**Key ORM models** (`models.py`): `Artist`, `Album`, `Track` (has `isrc`, `rank`, `preview_url`), `GeneratedPlaylist` with many-to-many `playlist_tracks`.

**Database**: SQLite at `./output/cache.db` by default; configurable to PostgreSQL via `DATABASE_URL`. TTL-based cache freshness checked per-entry (`CACHE_TTL_HOURS`, default 24h).

**Config** (`config.py`): all settings loaded from environment / `.env`; all output paths are relative to the working directory (important for pipx installs).

**API rate limits**: Deezer enforces a 0.3 s delay between requests; MusicBrainz enforces 1.1 s (max 1 req/s policy). These delays are baked into the respective API client modules.

**`auth.py`**: Deezer OAuth 2.0 skeleton — reserved for a future "push playlist to Deezer account" feature; not wired into the CLI yet.

## Release Process

Releases use `python-semantic-release` with Conventional Commits. Tagging and PyPI publishing are automated via `.github/workflows/release.yml` (Trusted Publishing — no API token needed).

```bash
poetry run semantic-release version --print     # dry-run version bump
poetry run semantic-release version --changelog # cut release (bumps, tags, GH release)
poetry run semantic-release publish             # publish to PyPI
```
