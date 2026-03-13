import subprocess


def generate_changelog() -> None:
    """Regenerate CHANGELOG.md using semantic-release."""
    subprocess.run(
        ["poetry", "run", "semantic-release", "changelog"], check=True
    )