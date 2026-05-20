"""
SQLite-backed OAuth 2.0 models.
Lightweight — no ORM dependency, plain sqlite3.
"""
import json
import secrets
import sqlite3
import time
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / ".oauth.db"


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create tables if they don't exist. Called at server startup."""
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS oauth_clients (
                client_id     TEXT PRIMARY KEY,
                client_secret TEXT NOT NULL,
                redirect_uris TEXT NOT NULL,
                name          TEXT NOT NULL,
                created_at    INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS auth_codes (
                code          TEXT PRIMARY KEY,
                client_id     TEXT NOT NULL,
                redirect_uri  TEXT NOT NULL,
                scope         TEXT NOT NULL,
                user_id       TEXT NOT NULL,
                expires_at    INTEGER NOT NULL,
                used          INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS access_tokens (
                token         TEXT PRIMARY KEY,
                client_id     TEXT NOT NULL,
                user_id       TEXT NOT NULL,
                scope         TEXT NOT NULL,
                expires_at    INTEGER NOT NULL,
                created_at    INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS refresh_tokens (
                token         TEXT PRIMARY KEY,
                access_token  TEXT NOT NULL,
                client_id     TEXT NOT NULL,
                user_id       TEXT NOT NULL,
                expires_at    INTEGER NOT NULL
            );
        """)


def create_client(
    client_id: str,
    client_secret: str,
    redirect_uris: list[str],
    name: str,
) -> None:
    with get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO oauth_clients VALUES (?,?,?,?,?)",
            (client_id, client_secret, json.dumps(redirect_uris), name, int(time.time())),
        )


def create_auth_code(
    client_id: str,
    redirect_uri: str,
    scope: str,
    user_id: str,
) -> str:
    code = secrets.token_urlsafe(32)
    expires_at = int(time.time()) + 600  # 10 minutes
    with get_db() as conn:
        conn.execute(
            "INSERT INTO auth_codes VALUES (?,?,?,?,?,?,0)",
            (code, client_id, redirect_uri, scope, user_id, expires_at),
        )
    return code


def consume_auth_code(code: str) -> sqlite3.Row | None:
    """Validate and consume an auth code. Returns None if invalid."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM auth_codes WHERE code=? AND used=0 AND expires_at>?",
            (code, int(time.time())),
        ).fetchone()
        if row:
            conn.execute("UPDATE auth_codes SET used=1 WHERE code=?", (code,))
    return row


def create_access_token(
    client_id: str,
    user_id: str,
    scope: str,
) -> tuple[str, str]:
    """Returns (access_token, refresh_token)."""
    access = secrets.token_urlsafe(48)
    refresh = secrets.token_urlsafe(48)
    now = int(time.time())

    with get_db() as conn:
        conn.execute(
            "INSERT INTO access_tokens VALUES (?,?,?,?,?,?)",
            (access, client_id, user_id, scope, now + 3600, now),  # 1 hour
        )
        conn.execute(
            "INSERT INTO refresh_tokens VALUES (?,?,?,?,?)",
            (refresh, access, client_id, user_id, now + 86400 * 30),  # 30 days
        )
    return access, refresh


def validate_access_token(token: str) -> sqlite3.Row | None:
    """Returns token row if valid, None if expired or not found."""
    with get_db() as conn:
        return conn.execute(
            "SELECT * FROM access_tokens WHERE token=? AND expires_at>?",
            (token, int(time.time())),
        ).fetchone()
