"""Connections to the project database and the idempotent migration."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import psycopg

from rotation_tracker.config import ROOT, market_env, settings

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


def migrate(log: Callable[[str], None] = print) -> list[str]:
    """Apply every ``sql/NNN_*.sql`` file in order as the superuser (each is idempotent), then
    import market-getdata's ``staging`` as ``market_staging`` over postgres_fdw (``market.fdw``),
    which is skipped with a notice when the ``MARKET_*`` variables or the remote schema are absent.
    """
    from rotation_tracker.market import fdw

    url = settings().admin_database_url
    if not url:
        raise SystemExit("ROTATION_ADMIN_DATABASE_URL is not set (see .db-urls.env).")
    applied = []
    files: list[Path] = sorted(SQL_DIR.glob("[0-9][0-9][0-9]_*.sql"))
    with psycopg.connect(url, autocommit=True) as con:
        for f in files:
            con.execute(f.read_text().encode())
            applied.append(f.name)
            log(f"applied {f.name}")
        got = fdw.import_market(con, market_env(), log)
    if got["tables"] and settings().ro_database_url:
        log(f"fdw: {fdw.probe(settings().ro_database_url, fdw.LOCAL_SCHEMA, got['tables'])}")
    return applied
