"""ISRC resolution with interactive candidate disambiguation.

Searches Deezer first, then falls back to MusicBrainz.  When multiple
candidates are returned the user is prompted to pick one, unless
*always_select_first* is set.
"""

from __future__ import annotations

from typing import Any

import click


def resolve_isrc(
    title: str,
    artist: str,
    deezer: Any,
    mb: Any,
    n_candidates: int,
    always_select_first: bool = False,
) -> str | None:
    """Search Deezer (then MusicBrainz) and return an ISRC, prompting when ambiguous."""

    # --- Deezer ---
    candidates = deezer.search_track_candidates(title, artist, limit=n_candidates)

    if candidates:
        chosen = _pick_candidate(
            candidates, title, artist, source="Deezer", always_select_first=always_select_first
        )
        if chosen is not None:
            full = deezer.get_track(chosen["id"])
            if full and full.isrc:
                return full.isrc
            # Deezer has the track but no ISRC – fall through to MusicBrainz

    # --- MusicBrainz fallback ---
    click.echo("  → Trying MusicBrainz…")
    mb_results = mb.search_recording(title, artist, limit=n_candidates)
    if not mb_results:
        return None

    chosen_mb = _pick_mb_candidate(mb_results, title, artist, always_select_first=always_select_first)
    if chosen_mb is None:
        return None
    isrcs: list[str] = chosen_mb.get("isrcs", [])
    return isrcs[0] if isrcs else None


def _pick_candidate(
    candidates: list[dict],
    title: str,
    artist: str,
    source: str,
    always_select_first: bool = False,
) -> dict | None:
    """Return the chosen Deezer candidate, or ``None`` if the user skips.

    Auto-accepts when there is exactly one exact title+artist match, or when
    *always_select_first* is ``True``.
    """
    tl = title.casefold()
    al = artist.casefold()
    exact = [
        c
        for c in candidates
        if c.get("title", "").casefold() == tl
        and (not al or c.get("artist", {}).get("name", "").casefold() == al)
    ]
    if len(exact) == 1:
        c = exact[0]
        click.echo(
            f"  \u2192 Auto-matched [{source}]: "
            f"{c.get('artist', {}).get('name', '?')} \u2013 {c.get('title', '?')}"
        )
        return c

    if always_select_first:
        c = candidates[0]
        click.echo(
            f"  \u2192 Auto-selected first [{source}]: "
            f"{c.get('artist', {}).get('name', '?')} \u2013 {c.get('title', '?')}"
        )
        return c

    click.echo(f"  Candidates from {source}:")
    for idx, c in enumerate(candidates, 1):
        a_name = c.get("artist", {}).get("name", "?")
        alb_name = c.get("album", {}).get("title", "?")
        click.echo(f"    [{idx}] {a_name} – {c.get('title', '?')}  (album: {alb_name})")

    while True:
        raw = (
            click.prompt("  Pick number, Enter=1, s=skip", default="1", show_default=False)
            .strip()
            .lower()
        )
        if raw == "s":
            return None
        try:
            n = int(raw)
            if 1 <= n <= len(candidates):
                return candidates[n - 1]
        except ValueError:
            pass
        click.echo("  Invalid choice, try again.")


def _pick_mb_candidate(
    recordings: list[dict],
    title: str,
    artist: str,
    always_select_first: bool = False,
) -> dict | None:
    """Return the chosen MusicBrainz recording, or ``None`` if the user skips."""
    with_isrc = [r for r in recordings if r.get("isrcs")]
    pool = with_isrc or recordings

    if not pool:
        return None

    tl = title.casefold()
    al = artist.casefold()
    exact = [
        r
        for r in pool
        if r.get("title", "").casefold() == tl
        and (
            not al
            or any(
                ac.get("artist", {}).get("name", "").casefold() == al
                for ac in r.get("artist-credit", [])
                if isinstance(ac, dict)
            )
        )
    ]
    if len(exact) == 1:
        r = exact[0]
        click.echo(f"  → Auto-matched [MusicBrainz]: {_mb_credit(r)} – {r.get('title', '?')}")
        return r

    if always_select_first:
        r = pool[0]
        click.echo(f"  → Auto-selected first [MusicBrainz]: {_mb_credit(r)} – {r.get('title', '?')}")
        return r

    click.echo("  Candidates from MusicBrainz:")
    for idx, r in enumerate(pool, 1):
        isrcs = r.get("isrcs", [])
        isrc_str = isrcs[0] if isrcs else "no ISRC"
        click.echo(f"    [{idx}] {_mb_credit(r)} – {r.get('title', '?')}  ({isrc_str})")

    while True:
        raw = (
            click.prompt("  Pick number, Enter=1, s=skip", default="1", show_default=False)
            .strip()
            .lower()
        )
        if raw == "s":
            return None
        try:
            n = int(raw)
            if 1 <= n <= len(pool):
                return pool[n - 1]
        except ValueError:
            pass
        click.echo("  Invalid choice, try again.")


def _mb_credit(recording: dict) -> str:
    return " / ".join(
        ac.get("artist", {}).get("name", "")
        for ac in recording.get("artist-credit", [])
        if isinstance(ac, dict)
    )
