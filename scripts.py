import subprocess


def generate_changelog() -> None:
    """Generate CHANGELOG.md using git-cliff."""
    subprocess.run(["git", "cliff", "-o", "CHANGELOG.md"], check=True)