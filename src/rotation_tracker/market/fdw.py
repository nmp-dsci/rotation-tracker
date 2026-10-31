"""market-getdata's ``staging`` in database ``rotation`` as ``market_staging``, over postgres_fdw.

Run by ``rt db migrate`` after the SQL files, as the cluster superuser, inside ``rotation`` only.
Modelled on data-qa-agent's migration 0040 (propertyiq_staging). One transaction:

- ``CREATE EXTENSION postgres_fdw`` (declared for ``rotation`` in the platform registry);
- foreign server ``market`` (host, port and dbname from the environment, ``fetch_size 10000``)
  and one user mapping ``FOR PUBLIC`` as the read-only ``market_ro``;
- schema ``market_staging``, dropped and re-created (it holds only foreign tables), and
  ``IMPORT FOREIGN SCHEMA staging FROM SERVER market INTO market_staging``;
- USAGE and SELECT for ``rotation_owner`` and ``rotation_ro``; then (``probe``) one read in a
  fresh ``rotation_ro`` session.

Skipped with a notice, and nothing changed, when no ``MARKET_*`` variable is set, when database
``market`` cannot be reached, or when it has no ``staging`` schema yet. Connection values come
from the environment and are bound as literals at run time; no password is written to a file.

Both databases live in one container, so ``localhost`` is the container's own loopback, which the
platform's pg_hba trusts. postgres_fdw refuses a non-superuser a connection that asks for no
password, so on a loopback host the mapping sets ``password_required 'false'`` (superuser-only).
It maps to the read-only ``market_ro`` and nobody else can change it.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

import psycopg
from psycopg import errors, sql

SERVER = "market"
LOCAL_SCHEMA = "market_staging"
REMOTE_SCHEMA = "staging"
READERS = ("rotation_owner", "rotation_ro")
ENV = ("MARKET_FDW_HOST", "MARKET_FDW_PORT", "MARKET_FDW_DBNAME", "MARKET_RO_USER",
       "MARKET_RO_PASSWORD")  # fmt: skip
LOOPBACK = {"localhost", "127.0.0.1", "::1"}

Log = Callable[[str], None]


@dataclass(frozen=True)
class Target:
    host: str
    port: str
    dbname: str
    user: str
    password: str

    @property
    def loopback(self) -> bool:
        return self.host in LOOPBACK

    def __repr__(self) -> str:  # never print the password
        return f"Target({self.user}@{self.host}:{self.port}/{self.dbname})"


def target(env: Mapping[str, str]) -> Target | None:
    """The connection values, defaults filled in; None when no ``MARKET_*`` variable is set."""
    if not any(env.get(k) for k in ENV):
        return None
    user = env.get("MARKET_RO_USER") or "market_ro"
    return Target(
        host=env.get("MARKET_FDW_HOST") or "localhost",
        port=env.get("MARKET_FDW_PORT") or "5432",
        dbname=env.get("MARKET_FDW_DBNAME") or "market",
        user=user,
        password=env.get("MARKET_RO_PASSWORD") or user,  # the platform's local convention
    )


def _ddl(t: Target, server: str, schema: str) -> list[sql.Composed]:
    opts: list[sql.Composable] = [
        sql.SQL("user {}").format(sql.Literal(t.user)),
        sql.SQL("password {}").format(sql.Literal(t.password)),
    ]
    if t.loopback:
        opts.append(sql.SQL("password_required 'false'"))
    srv, sch = sql.Identifier(server), sql.Identifier(schema)
    return [
        sql.SQL("CREATE EXTENSION IF NOT EXISTS postgres_fdw").format(),
        sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sch),
        sql.SQL("DROP SERVER IF EXISTS {} CASCADE").format(srv),
        sql.SQL(
            "CREATE SERVER {} FOREIGN DATA WRAPPER postgres_fdw "
            "OPTIONS (host {}, port {}, dbname {}, fetch_size '10000')"
        ).format(srv, sql.Literal(t.host), sql.Literal(t.port), sql.Literal(t.dbname)),
        sql.SQL("CREATE USER MAPPING FOR PUBLIC SERVER {} OPTIONS ({})").format(
            srv, sql.SQL(", ").join(opts)
        ),
        sql.SQL("CREATE SCHEMA {}").format(sch),
        sql.SQL("COMMENT ON SCHEMA {} IS {}").format(
            sch,
            sql.Literal(
                "market-getdata staging over postgres_fdw: foreign tables only, "
                "re-imported by `rt db migrate`"
            ),
        ),
    ]


def import_market(
    con: psycopg.Connection[Any],
    env: Mapping[str, str],
    log: Log = print,
    *,
    server: str = SERVER,
    schema: str = LOCAL_SCHEMA,
    readers: tuple[str, ...] = READERS,
) -> dict[str, Any]:
    """Wire ``market_staging``. ``con``: a superuser connection to ``rotation`` (autocommit off).

    Returns ``{"status": "imported" | "skipped", "tables": [...], "reason": ...}``.
    """
    t = target(env)
    if t is None:
        reason = "no MARKET_* variable is set; the viewer runs without prices"
        log(f"fdw: skipped ({reason})")
        return {"status": "skipped", "reason": reason, "tables": []}
    sch = sql.Identifier(schema)
    try:
        with con.transaction():
            for stmt in _ddl(t, server, schema):
                con.execute(stmt)
            con.execute(
                sql.SQL("IMPORT FOREIGN SCHEMA {} FROM SERVER {} INTO {}").format(
                    sql.Identifier(REMOTE_SCHEMA), sql.Identifier(server), sch
                )
            )
            tables = [
                r[0]
                for r in con.execute(
                    """SELECT c.relname FROM pg_class c
                       JOIN pg_namespace n ON n.oid = c.relnamespace
                       WHERE n.nspname = %s AND c.relkind = 'f' ORDER BY 1""",
                    (schema,),
                )
            ]
            roles = sql.SQL(", ").join(sql.Identifier(r) for r in readers)
            con.execute(sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(sch, roles))
            con.execute(sql.SQL("GRANT SELECT ON ALL TABLES IN SCHEMA {} TO {}").format(sch, roles))
    except errors.FdwSchemaNotFound:
        reason = (
            f"database {t.dbname} has no schema {REMOTE_SCHEMA} yet (market-getdata not loaded)"
        )
        log(f"fdw: skipped ({reason}); run `rt db migrate` again once it has")
        return {"status": "skipped", "reason": reason, "tables": []}
    except (errors.SqlclientUnableToEstablishSqlconnection, errors.FdwUnableToEstablishConnection,
            errors.FdwError, errors.ConnectionException) as e:  # fmt: skip
        first = str(e).strip().splitlines()[0] if str(e).strip() else type(e).__name__
        reason = f"cannot reach {t.dbname} at {t.host}:{t.port} as {t.user}: {first}"
        log(f"fdw: skipped ({reason}); check MARKET_* in .env")
        return {"status": "skipped", "reason": reason, "tables": []}
    log(
        f"fdw: {schema} ← {t.dbname}.{REMOTE_SCHEMA} on {t.host}:{t.port} as {t.user}, "
        f"{len(tables)} foreign table(s){': ' + ', '.join(tables) if tables else ''}"
    )
    return {"status": "imported", "tables": tables}


def probe(ro_url: str, schema: str, tables: list[str]) -> str:
    """Read one row in a fresh session as the read-only role, as the viewer will.

    A fresh session matters: postgres_fdw caches a connection per user mapping, so a read in the
    importing session reuses the superuser's connection and proves nothing about rotation_ro.
    """
    table = "series_values" if "series_values" in tables else tables[0]
    try:
        with psycopg.connect(ro_url) as con:
            con.execute(
                sql.SQL("SELECT 1 FROM {}.{} LIMIT 1").format(
                    sql.Identifier(schema), sql.Identifier(table)
                )
            ).fetchall()
            who = con.execute("SELECT current_user").fetchone()
        return f"{who[0] if who else 'the read-only role'} reads {schema}.{table}"
    except psycopg.Error as e:
        first = str(e).strip().splitlines()[0] if str(e).strip() else type(e).__name__
        return f"WARNING: the read-only role cannot read {schema}.{table}: {first}"
