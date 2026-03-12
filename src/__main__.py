"""Allow ``python -m src`` to run the CLI.

Subcommands
-----------
``python -m src generate <input_file>``   – generate a playlist from artist/track list
``python -m src convert  <vdj_csv>``      – convert VirtualDJ CSV → Soundiiz CSV with ISRC
"""

from src.cli import cli

if __name__ == "__main__":
    cli()
