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

## Release process

Releases are managed by [python-semantic-release](https://python-semantic-release.readthedocs.io/).
It reads **Conventional Commits** since the last tag to decide the version bump automatically:

| Commit type | Version bump |
|---|---|
| `fix:`, `perf:` | patch (0.0.x) |
| `feat:` | minor (0.x.0) |
| `feat!:` or `BREAKING CHANGE:` footer | major (x.0.0) |
| `chore:`, `docs:`, `refactor:`, etc. | no release triggered |

### Commit message format

```
<type>(<optional scope>): <short description>

# Examples:
feat(cli): add --dry-run flag
fix(deezer): handle 404 on track lookup
docs: update README with auth instructions
chore: bump dependencies
refactor!: rename config fields  ← triggers major bump
```

### Cutting a release

```bash
# 1. Check what the next version would be (dry run, no changes)
poetry run semantic-release version --print

# 2. Cut the release: bumps pyproject.toml, updates CHANGELOG.md,
#    commits, tags, builds dist/, pushes to GitHub, and creates
#    a GitHub Release with dist/*.whl and dist/*.tar.gz attached
GH_TOKEN=your_token poetry run semantic-release version --changelog
GH_TOKEN=your_token poetry run semantic-release publish
```

Pushing the tag triggers `.github/workflows/release.yml`, which builds and
publishes to PyPI automatically via Trusted Publishing (no token required).

> **Tip:** Set `GH_TOKEN` in your shell session once (`export GH_TOKEN=ghp_...`)
> so you don't have to prefix every command.


### Refresh the changelog without releasing

```bash
poetry run semantic-release changelog
```

### Force a specific bump (override auto-detection)

```bash
GH_TOKEN=your_token poetry run semantic-release version --changelog --patch
GH_TOKEN=your_token poetry run semantic-release version --changelog --minor
GH_TOKEN=your_token poetry run semantic-release version --changelog --major
```
