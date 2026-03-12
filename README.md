# crateport

A DJ-focused playlist tool with two workflows:

- **`generate`** — build a playlist from a list of artists, albums, or tracks using the Deezer public API, then export it to XSPF / M3U / CSV / JSON.
- **`convert`** — take a VirtualDJ CSV export, enrich every track with an ISRC via Deezer (falling back to MusicBrainz), and produce a Soundiiz-compatible CSV ready for import into Deezer or any other streaming platform.

No Deezer application credentials required. API responses are cached locally in SQLite.

---

## Requirements

- Python ≥ 3.14
- [pipx](https://pipx.pypa.io/) for installation

---

## Installation

```bash
git clone https://github.com/ZyanKLee/crateport.git
cd crateport
pipx install .
```

The `crateport` command is then available globally.

To upgrade after pulling new changes:

```bash
pipx install . --force
```

To uninstall:

```bash
pipx uninstall crateport
```

### Working directory

crateport always reads and writes relative to **where you run the command**, regardless of where it is installed:

| Path | Purpose |
|------|---------|
| `./output/` | Generated CSVs, XSPF, M3U, JSON, and `cache.db` — created automatically |
| `./source_data/` | Convenient place for input files — created automatically, not required |
| `./.env` | Optional configuration overrides (see [Configuration](#configuration)) |

---

## Quick start

```bash
# Convert a VirtualDJ set export to Soundiiz CSV with ISRC
crateport convert "source_data/2026-03-13 My Set.csv" --name "My_Set_2026-03-13"

# Generate a playlist from an artist list
crateport generate source_data/artists.txt --name "My Techno Mix"
```

**Full command reference:** [docs/convert.md](docs/convert.md) · [docs/generate.md](docs/generate.md)

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

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for project structure and development setup.

---

## License

MIT License © 2024 Zyan K. Lee
