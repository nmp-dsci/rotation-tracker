"""components/v1: what is inside a category (``assets/components.yaml``).

Three lists, unioned: the GICS list (S&P 500 members whose sub-industry or sector maps to the
category, or an index's members), the names he says (stocks with a mention on that list, plus
stocks with no GICS row named in the same role of at least two of the category's mentions),
ranked by mentions; and the proxy ETF's issuer holdings, which are phase 2.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from psycopg.rows import dict_row

from rotation_tracker.config import ROOT

COMPONENTS_VERSION = "components/v1"
COMPONENTS_FILE = ROOT / "assets" / "components.yaml"
HOLDINGS = "issuer holdings: phase 2 (market-getdata staging.holdings)"
CO_MENTIONS = 2  # a name without a GICS row joins after this many mentions beside the category
INDEX_FLAGS = ("sp500", "ndx")


@dataclass(frozen=True)
class Basis:
    """What defines a category's GICS list."""

    sub_industries: tuple[str, ...] = ()
    sectors: tuple[str, ...] = ()
    index: str | None = None  # an rt.assets membership flag

    @property
    def defined(self) -> bool:
        return bool(self.sub_industries or self.sectors or self.index)

    def describe(self) -> list[str]:
        out = [f"GICS sub-industry {s}" for s in self.sub_industries]
        out += [f"GICS sector {s}" for s in self.sectors]
        if self.index:
            out.append({"sp500": "S&P 500 members", "ndx": "Nasdaq-100 members"}[self.index])
        return out


@dataclass(frozen=True)
class Components:
    version: str
    sub_industries: Mapping[str, tuple[str, ...]]
    sectors: Mapping[str, str]
    indexes: Mapping[str, str] = field(default_factory=dict)

    @classmethod
    def parse(cls, doc: Mapping[str, Any]) -> Components:
        if doc.get("version") != COMPONENTS_VERSION:
            raise ValueError(f"version must be {COMPONENTS_VERSION}, not {doc.get('version')!r}")
        subs = {
            str(k): (tuple(v) if isinstance(v, list) else (str(v),))
            for k, v in (doc.get("sub_industries") or {}).items()
        }
        indexes = {str(k): str(v) for k, v in (doc.get("indexes") or {}).items()}
        bad = [f for f in indexes.values() if f not in INDEX_FLAGS]
        if bad:
            raise ValueError(f"index flags must be one of {INDEX_FLAGS}: {bad}")
        sectors = {str(k): str(v) for k, v in (doc.get("sectors") or {}).items()}
        return cls(str(doc["version"]), subs, sectors, indexes)

    def basis(self, asset_id: str) -> Basis:
        return Basis(
            tuple(sorted(s for s, cats in self.sub_industries.items() if asset_id in cats)),
            tuple(sorted(s for s, cat in self.sectors.items() if cat == asset_id)),
            self.indexes.get(asset_id),
        )

    def targets(self) -> set[str]:
        out = {c for cats in self.sub_industries.values() for c in cats}
        return out | set(self.sectors.values()) | set(self.indexes)


@lru_cache(maxsize=1)
def load(path: Path = COMPONENTS_FILE) -> Components:
    return Components.parse(yaml.safe_load(path.read_text()))


def components(con: Any, asset_id: str, comp: Components | None = None) -> dict[str, Any]:
    """The three lists for one asset, read as any role that can see ``rt``.

    ``named`` counts the miner's current calls (today's prompt), as every viewer page does.
    """
    from rotation_tracker.serving.mining import CURRENT, ON_CUR, _args

    b = (comp or load()).basis(asset_id)
    out: dict[str, Any] = {
        "version": COMPONENTS_VERSION,
        "defined": b.defined,
        "basis": b.describe(),
        "gics": [],
        "named": [],
        "holdings": HOLDINGS,
    }
    if not b.defined:
        return out
    flag = b.index or ""
    member = (
        "s.kind = 'stock' AND (s.gics_sub_industry = ANY(%(subs)s) OR s.gics_sector = ANY(%(secs)s)"
        f"{f' OR s.{flag}' if flag in INDEX_FLAGS else ''})"
    )
    a = _args(
        asset=asset_id, subs=list(b.sub_industries), secs=list(b.sectors), co=CO_MENTIONS,
        gics_basis=bool(b.sub_industries or b.sectors),
    )  # fmt: skip
    with con.cursor(row_factory=dict_row) as cur:
        out["gics"] = cur.execute(
            f"""SELECT s.id AS asset_id, s.ticker, s.name, s.gics_sub_industry AS sub_industry
                FROM rt.assets s WHERE {member} ORDER BY s.ticker""",
            a,
        ).fetchall()
        out["named"] = cur.execute(
            f"""WITH {CURRENT},
                x AS (SELECT a.mention_id, a.asset_id, a.role FROM rt.mention_assets a
                      JOIN rt.mentions m ON m.id = a.mention_id {ON_CUR}
                      WHERE a.asset_id IS NOT NULL),
                n AS (SELECT asset_id, count(DISTINCT mention_id) AS mentions FROM x GROUP BY 1),
                co AS (SELECT o.asset_id, count(DISTINCT o.mention_id) AS n
                       FROM x c JOIN x o ON o.mention_id = c.mention_id
                        AND o.asset_id <> c.asset_id AND o.role = c.role
                       WHERE c.asset_id = %(asset)s GROUP BY 1)
                SELECT s.id AS asset_id, s.ticker, s.name, n.mentions,
                       CASE WHEN {member} THEN 'gics' ELSE 'named beside it' END AS via
                FROM n JOIN rt.assets s ON s.id = n.asset_id
                LEFT JOIN co ON co.asset_id = s.id
                WHERE s.kind = 'stock'
                  AND ({member} OR (%(gics_basis)s AND s.gics_sub_industry IS NULL
                                    AND coalesce(co.n, 0) >= %(co)s))
                ORDER BY n.mentions DESC, s.ticker""",
            a,
        ).fetchall()
    return out
