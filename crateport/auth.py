"""Deezer OAuth 2.0 authentication.

Deezer uses a custom three-legged OAuth flow:

1. Open the authorization URL in the user's browser.
2. The user logs in and grants permissions.
3. Deezer redirects to *redirect_uri* with ``?code=<auth_code>``.
4. Exchange the code for an access token.

A lightweight ``http.server`` is started locally to capture the callback
when the redirect URI points to ``localhost``.

.. note::

    You must register an application at https://developers.deezer.com/ and
    populate ``DEEZER_APP_ID`` and ``DEEZER_SECRET`` in your ``.env`` file.
"""

from __future__ import annotations

import logging
import threading
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

import requests

from .config import config

logger = logging.getLogger(__name__)

_AUTH_URL = "https://connect.deezer.com/oauth/auth.php"
_TOKEN_URL = "https://connect.deezer.com/oauth/access_token.php"
_TOKEN_FILE = config.output_dir / ".deezer_token"

_PERMS = "basic_access,email,manage_library,delete_library"


# ---------------------------------------------------------------------------
# Token persistence
# ---------------------------------------------------------------------------


def load_saved_token() -> str | None:
    """Return the access token saved from a previous session, or ``None``."""
    if _TOKEN_FILE.exists():
        return _TOKEN_FILE.read_text().strip() or None
    return None


def save_token(token: str) -> None:
    """Persist *token* to disk for reuse across sessions."""
    _TOKEN_FILE.write_text(token)
    _TOKEN_FILE.chmod(0o600)
    logger.debug("Saved access token to %s", _TOKEN_FILE)


# ---------------------------------------------------------------------------
# OAuth flow
# ---------------------------------------------------------------------------


def get_access_token(force_reauth: bool = False) -> str:
    """Return a valid Deezer access token, prompting the user to log in if needed.

    Raises
    ------
    ValueError
        When ``DEEZER_APP_ID`` or ``DEEZER_SECRET`` are not configured.
    RuntimeError
        When the OAuth flow fails or times out.
    """
    if not force_reauth:
        token = load_saved_token()
        if token:
            logger.debug("Using saved Deezer access token.")
            return token

    if not config.deezer_app_id or not config.deezer_secret:
        raise ValueError(
            "DEEZER_APP_ID and DEEZER_SECRET must be set in your .env file.\n"
            "Register an application at https://developers.deezer.com/"
        )

    code = _run_local_oauth_flow()
    token = _exchange_code_for_token(code)
    save_token(token)
    return token


def _build_auth_url() -> str:
    params = {
        "app_id": config.deezer_app_id,
        "redirect_uri": config.deezer_redirect_uri,
        "perms": _PERMS,
        "response_type": "code",
    }
    return f"{_AUTH_URL}?{urllib.parse.urlencode(params)}"


def _run_local_oauth_flow() -> str:
    """Open the browser and wait for the OAuth callback. Return the auth code."""
    parsed = urllib.parse.urlparse(config.deezer_redirect_uri)
    host = parsed.hostname or "localhost"
    port = parsed.port or 8080

    received_code: list[str] = []
    done = threading.Event()

    class Handler(BaseHTTPRequestHandler):  # pylint: disable=too-few-public-methods
        """Minimal HTTP handler that captures the OAuth callback code."""

        def do_GET(self) -> None:  # noqa: N802  # pylint: disable=invalid-name
            """Handle the OAuth redirect GET request and extract the auth code."""
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            code = qs.get("code", [""])[0]
            if code:
                received_code.append(code)
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            msg = (
                "<h2>Authorization successful!</h2><p>You can close this tab.</p>"
                if code
                else "<h2>No code received.</h2>"
            )
            self.wfile.write(msg.encode())
            done.set()

        def log_message(self, *args) -> None:  # silence request logs
            pass

    server = HTTPServer((host, port), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    auth_url = _build_auth_url()
    logger.info("Opening browser for Deezer authorization…")
    print(f"\nIf your browser does not open automatically, visit:\n  {auth_url}\n")
    webbrowser.open(auth_url)

    if not done.wait(timeout=120):
        server.shutdown()
        raise RuntimeError("Timed out waiting for Deezer OAuth callback (120 s).")

    server.shutdown()
    if not received_code:
        raise RuntimeError("OAuth callback received but no auth code was found.")
    return received_code[0]


def _exchange_code_for_token(code: str) -> str:
    """Exchange an authorization code for an access token."""
    params = {
        "app_id": config.deezer_app_id,
        "secret": config.deezer_secret,
        "code": code,
        "output": "json",
    }
    resp = requests.get(_TOKEN_URL, params=params, timeout=15)
    resp.raise_for_status()
    # Deezer may return JSON or URL-encoded depending on the ``output`` param
    try:
        data = resp.json()
        token = data.get("access_token", "")
    except ValueError:
        qs = urllib.parse.parse_qs(resp.text)
        token = qs.get("access_token", [""])[0]

    if not token:
        raise RuntimeError(f"Failed to obtain access token. Response: {resp.text}")
    logger.info("Successfully obtained Deezer access token.")
    return token


def revoke_saved_token() -> None:
    """Delete the locally saved token file."""
    if _TOKEN_FILE.exists():
        _TOKEN_FILE.unlink()
        logger.info("Saved token deleted.")
