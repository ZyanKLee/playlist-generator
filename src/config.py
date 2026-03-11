"""Configuration loaded from environment variables / .env file."""

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).parent.parent
OUTPUT_DIR = ROOT_DIR / "output"
SOURCE_DATA_DIR = ROOT_DIR / "source_data"


class Config:
    """Central configuration object.

    Values are read from environment variables; a ``.env`` file placed at the
    project root is loaded automatically if it exists.
    """

    def __init__(self) -> None:
        load_dotenv(ROOT_DIR / ".env")

        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        SOURCE_DATA_DIR.mkdir(parents=True, exist_ok=True)

        # Database – defaults to SQLite in output/
        self.db_url: str = os.getenv(
            "DATABASE_URL",
            f"sqlite:///{OUTPUT_DIR / 'cache.db'}",
        )

        # Deezer application credentials (register at developers.deezer.com)
        self.deezer_app_id: str = os.getenv("DEEZER_APP_ID", "")
        self.deezer_secret: str = os.getenv("DEEZER_SECRET", "")
        self.deezer_redirect_uri: str = os.getenv(
            "DEEZER_REDIRECT_URI", "http://localhost:8080/callback"
        )

        # MusicBrainz – used as fallback when Deezer has no exact artist match.
        # Must identify your application per https://wiki.musicbrainz.org/MusicBrainz_API/Rate_Limiting
        self.musicbrainz_user_agent: str = os.getenv(
            "MUSICBRAINZ_USER_AGENT",
            "playlist-generator/1.0 (https://github.com/ZyanKLee/playlist-generator)",
        )

        # How long cached API responses remain valid (hours)
        self.cache_ttl_hours: int = int(os.getenv("CACHE_TTL_HOURS", "24"))

        self.output_dir: Path = OUTPUT_DIR
        self.source_data_dir: Path = SOURCE_DATA_DIR
        self.root_dir: Path = ROOT_DIR


config = Config()
