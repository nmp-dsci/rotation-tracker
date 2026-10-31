"""The viewer's prices: ``market_staging`` (market-getdata over postgres_fdw), read as rotation_ro.

``series_values`` is the one table a chart needs (series key × date → value: Yahoo adjusted
close, a FRED level, a basket's value); ``instruments`` gives each series' name and first date.
Either may be missing (fdw not imported yet) or empty (no backfill yet): the viewer then shows a
notice and every row its series without a line.

A chart's x buckets are quarters. A series' point in a quarter is its last value in that quarter
(the quarter-end close; the latest one for a quarter in progress). Yahoo and basket series are
performance lines, rebased to 100 at the chart's first x; FRED series are levels in their units.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager
from datetime import date
from typing import Any, Literal, Protocol

from psycopg import sql
from psycopg.rows import dict_row

from rotation_tracker.market.proxies import NONE, source, symbol

SCHEMA = "market_staging"
Mode = Literal["performance", "level", "none"]


def mode(series: str) -> Mode:
    src = source(series)
    return "level" if src == "fred" else "none" if src is None else "performance"


def label(series: str | None) -> str:
    """``yahoo:SMH`` → ``SMH``; ``fred:DGS10`` → ``DGS10``; ``basket:mag7`` → ``mag7 basket``."""
    if not series or series == NONE:
        return "none"
    return f"{symbol(series)} basket" if source(series) == "basket" else symbol(series)


def quarter_of(d: date) -> date:
    return date(d.year, 3 * ((d.month - 1) // 3) + 1, 1)


def align(closes: dict[date, float], quarters: Sequence[date]) -> list[float | None]:
    """One point per chart quarter; None where the series has no value in it."""
    return [closes.get(q) for q in quarters]


def rebase(points: list[float | None]) -> list[float | None]:
    """Performance: 100 at the first quarter with a value (the chart's first x, if it has one)."""
    base = next((v for v in points if v), None)
    return [None if v is None or not base else round(100 * v / base, 2) for v in points]


def line(
    series: str | None,
    closes: dict[date, float] | None,
    quarters: Sequence[date],
    info: dict[str, Any] | None = None,
    reason: str | None = None,
) -> dict[str, Any] | None:
    """A chart row's price strip: the series, how to read it, and its points (may be empty)."""
    if not series:
        return None
    m = mode(series)
    pts: list[float | None] = []
    if closes and m != "none":
        raw = align(closes, quarters)
        pts = (
            rebase(raw) if m == "performance" else [None if v is None else round(v, 4) for v in raw]
        )
        if not any(v is not None for v in pts):
            pts = []
    return {
        "series": series,
        "label": label(series),
        "mode": m,
        "points": pts,
        "name": (info or {}).get("name"),
        "first_date": (info or {}).get("first_date"),
        "reason": reason,
    }


class Market(Protocol):
    """What the viewer reads about prices (``MarketStaging``; a fake in tests)."""

    def status(self) -> tuple[bool, str | None]: ...
    def quarter_closes(
        self, series: Sequence[str], since: date
    ) -> dict[str, dict[date, float]]: ...
    def instruments(self, series: Sequence[str]) -> dict[str, dict[str, Any]]: ...


NOT_IMPORTED = (
    "No prices yet: {schema}.series_values is not there. Prices come from market-getdata; once "
    "its staging tables exist, `uv run rt db migrate` imports them over postgres_fdw."
)
EMPTY = "No prices yet: {schema}.series_values is empty (market-getdata has not loaded a backfill)."


class MarketStaging:
    """``market_staging`` through a read-only connection (``connect``: a context manager)."""

    def __init__(
        self,
        connect: Callable[[], AbstractContextManager[Any]],
        schema: str = SCHEMA,
    ) -> None:
        self.connect, self.schema = connect, schema

    def _t(self, table: str) -> sql.Composed:
        return sql.SQL("{}.{}").format(sql.Identifier(self.schema), sql.Identifier(table))

    def status(self) -> tuple[bool, str | None]:
        """(prices available, the notice to show when not). Never raises."""
        try:
            with self.connect() as con:
                there = con.execute(
                    "SELECT to_regclass(%s) IS NOT NULL AND to_regclass(%s) IS NOT NULL",
                    (f"{self.schema}.series_values", f"{self.schema}.instruments"),
                ).fetchone()
                if not (there and there[0]):
                    return False, NOT_IMPORTED.format(schema=self.schema)
                row = con.execute(
                    sql.SQL("SELECT 1 FROM {} LIMIT 1").format(self._t("series_values"))
                ).fetchone()
                if row is None:
                    return False, EMPTY.format(schema=self.schema)
        except Exception as e:  # the feed being down is a state the page shows
            first = (str(e).strip().splitlines() or [type(e).__name__])[0]
            return False, f"Prices unavailable: {type(e).__name__}: {first[:200]}"
        return True, None

    def quarter_closes(self, series: Sequence[str], since: date) -> dict[str, dict[date, float]]:
        """Series → quarter start → the last value in that quarter, from ``since`` on.

        Two reads: the last date per series and quarter, then the values on those dates.
        postgres_fdw ships the filters and the local server groups (checked 31 Oct 2026: 326
        series since 2023, ≈ 330k remote rows, 0.3 s over the loopback); Python sees ≈ 5k rows.
        """
        if not series:
            return {}
        sv = self._t("series_values")
        args = {"s": list(series), "since": since}
        with self.connect() as con:
            last = con.execute(
                sql.SQL(
                    """SELECT series, max(date) FROM {} WHERE series = ANY(%(s)s)
                         AND date >= %(since)s AND value IS NOT NULL
                       GROUP BY series, extract(year FROM date), extract(quarter FROM date)"""
                ).format(sv),
                args,
            ).fetchall()
            want = {(s, d) for s, d in last}
            days = sorted({d for _, d in want})
            rows = con.execute(
                sql.SQL(
                    """SELECT series, date, value FROM {} WHERE series = ANY(%(s)s)
                         AND date = ANY(%(d)s) AND value IS NOT NULL"""
                ).format(sv),
                {**args, "d": days},
            ).fetchall()
        out: dict[str, dict[date, float]] = {}
        for s, d, v in rows:
            if (s, d) in want:
                out.setdefault(s, {})[quarter_of(d)] = float(v)
        return out

    def instruments(self, series: Sequence[str]) -> dict[str, dict[str, Any]]:
        if not series:
            return {}
        with self.connect() as con, con.cursor(row_factory=dict_row) as cur:
            rows = cur.execute(
                sql.SQL(
                    """SELECT series, name, source, type, currency, first_date, last_date
                       FROM {} WHERE series = ANY(%(s)s)"""
                ).format(self._t("instruments")),
                {"s": list(series)},
            ).fetchall()
        return {r["series"]: r for r in rows}


def proxy_rows(con: Any, asset_ids: Sequence[str]) -> dict[str, list[dict[str, Any]]]:
    """``rt.asset_proxies`` for these assets: the primary first, then companions in order."""
    out: dict[str, list[dict[str, Any]]] = {}
    with con.cursor(row_factory=dict_row) as cur:
        for r in cur.execute(
            """SELECT asset_id, series, role, ord, from_date, to_date, note
               FROM rt.asset_proxies WHERE asset_id = ANY(%s)
               ORDER BY asset_id, role = 'companion', ord""",
            (list(asset_ids),),
        ):
            out.setdefault(r["asset_id"], []).append(r)
    return out


def priced(row: dict[str, Any], info: dict[str, Any] | None) -> dict[str, Any]:
    """One ``rt.asset_proxies`` row for the Asset page: how to read it and since when."""
    return {
        "series": row["series"],
        "label": label(row["series"]),
        "mode": mode(row["series"]),
        "role": row["role"],
        "from_date": row["from_date"],
        "to_date": row["to_date"],
        "note": row["note"],
        "name": (info or {}).get("name"),
        "first_date": (info or {}).get("first_date"),
        "last_date": (info or {}).get("last_date"),
    }
