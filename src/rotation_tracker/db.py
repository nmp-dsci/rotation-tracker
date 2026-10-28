"""Connections to the project database and the idempotent migration."""

from __future__ import annotations

from pathlib import Path

import psycopg

from rotation_tracker.config import ROOT, settings

SQL_DIR = ROOT / "sql"


def connect(readonly: bool = False) -> psycopg.Connection:
    s = settings()
    url = s.ro_database_url if readonly else s.database_url
    if not url:
        name = "ROTATION_RO_DATABASE_URL" if readonly else "ROTATION_DATABASE_URL"
        raise SystemExit(
            f"{name} is not set. Run `make -C ../nmp-central-ai db-init` and paste the "
            "rotation block from its .db-urls.env into .env."
        )
    return psycopg.connect(url, autocommit=False)


def migrate() -> list[str]:
    """Apply every ``sql/NNN_*.sql`` file in order as the superuser. Each file is idempotent."""
    url = settings().admin_database_url
    if not url:
        raise SystemExit("ROTATION_ADMIN_DATABASE_URL is not set (see .db-urls.env).")
    applied = []
    files: list[Path] = sorted(SQL_DIR.glob("[0-9][0-9][0-9]_*.sql"))
    with psycopg.connect(url, autocommit=True) as con:
        for f in files:
            con.execute(f.read_text().encode())
            applied.append(f.name)
    return applied
