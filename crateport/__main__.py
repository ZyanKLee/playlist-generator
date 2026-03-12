"""Allow ``python -m crateport`` to run the CLI.

Subcommands
-----------
``crateport generate <input_file>``   – generate a playlist from artist/track list
``crateport convert  <vdj_csv>``      – convert VirtualDJ CSV → Soundiiz CSV with ISRC
"""

from crateport.cli import cli

if __name__ == "__main__":
    cli()
