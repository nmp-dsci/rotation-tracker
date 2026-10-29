"""assets/v1: build ``rt.assets`` and ``rt.aliases`` (``rt assets seed``).

Four sources, all public and fetched at build time (or read from a local copy):

- ``assets/themes.yaml``: the curated layers (index, GICS sector, theme, crypto, rates, credit,
  commodity, FX, macro), each with a proxy and aliases;
- Nasdaq Trader's symbol directory: every US-listed ticker, so any stock he names can resolve
  (owner's decision, 28 Oct 2026: no index gate);
- the S&P 500 constituent list (Wikipedia): membership, date added, GICS sector and
  sub-industry, and a company name to generate a spoken alias from;
- the Nasdaq-100 list (Nasdaq's own API): membership and a company name.

``assets/extras.yaml`` adds the nicknames, mishearings and ambiguous names by hand. Assets are
upserted and never deleted (mentions point at them); the alias table is rebuilt each time.
"""

from __future__ import annotations

import json
import re
import urllib.request
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import yaml

from rotation_tracker.config import ROOT
from rotation_tracker.mining.resolve import normalise

ASSETS_VERSION = "assets/v1"
ASSET_DIR = ROOT / "assets"
SOURCES = {
    "sp500": "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
    "ndx": "https://api.nasdaq.com/api/quote/list-type/nasdaq100",
    "nasdaqlisted": "https://www.nasdaqtrader.com/dynamic/symdir/nasdaqlisted.txt",
    "otherlisted": "https://www.nasdaqtrader.com/dynamic/symdir/otherlisted.txt",
}
EXCHANGES = {"A": "NYSE American", "N": "NYSE", "P": "NYSE Arca", "Z": "Cboe BZX", "V": "IEX"}
# Listings that are not a company's common stock or a fund.
NOT_COMMON = re.compile(
    r"\b(warrants?|units?|rights?|preferred|pfd|notes? due|debentures?|subordinated|perpetual)\b"
    r"|depositary shares?,? each representing (a|1/)|\bseries [a-z]{1,2}\b|%",
    re.I,
)
SUFFIX = re.compile(
    r"(\s+-\s+.*$)|\(.*?\)|\b(common (stock|shares)|ordinary shares|class [abc]( common stock)?|"
    r"american depositary shares?|ads|adr|new)\b",
    re.I,
)
CORP = {
    "inc", "incorporated", "corp", "corporation", "co", "company", "plc", "ltd", "limited",
    "holdings", "holding", "group", "sa", "nv", "ag", "se", "lp", "llc", "the", "n v", "s a",
}  # fmt: skip
# "Palantir Technologies" is also "Palantir"; "American Express" is not "American".
GENERIC_SECOND = {
    "platforms", "technologies", "technology", "systems", "financial", "communications", "brands",
    "labs", "laboratories", "networks", "software", "pharmaceuticals", "therapeutics", "motors",
    "airlines", "entertainment", "interactive", "markets", "global", "computer", "health",
    "industries", "enterprises", "resources", "solutions", "services", "worldwide", "digital",
    "scientific", "materials", "partners", "capital", "semiconductor", "energy", "devices",
}  # fmt: skip
WEAK_FIRST = {
    "american", "general", "united", "first", "global", "international", "national", "new",
    "southern", "northern", "eastern", "western", "central", "public", "consolidated",
    "advanced", "applied", "universal", "royal", "best", "discovery", "digital", "pacific",
    "atlantic", "texas", "southwest", "north", "south", "us", "regions", "realty", "west",
}  # fmt: skip


@lru_cache(maxsize=1)
def curated() -> dict[str, Any]:
    return dict(yaml.safe_load((ASSET_DIR / "themes.yaml").read_text()))


@lru_cache(maxsize=1)
def extras() -> dict[str, Any]:
    return dict(yaml.safe_load((ASSET_DIR / "extras.yaml").read_text()))


def fetch(url: str) -> str:
    req = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0 rotation-tracker", "Accept": "*/*"}
    )
    with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310 - fixed public URLs
        return str(r.read().decode("utf-8", "replace"))


class _Tables(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tables: list[list[list[str]]] = []
        self.row: list[str] | None = None
        self.cell: list[str] | None = None
        self.depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "table":
            self.depth += 1
            self.tables.append([])
        elif tag == "tr" and self.depth:
            self.row = []
        elif tag in ("td", "th") and self.row is not None:
            self.cell = []

    def handle_endtag(self, tag: str) -> None:
        if tag in ("td", "th") and self.cell is not None and self.row is not None:
            self.row.append(" ".join("".join(self.cell).split()))
            self.cell = None
        elif tag == "tr" and self.row is not None:
            self.tables[-1].append(self.row)
            self.row = None
        elif tag == "table":
            self.depth -= 1

    def handle_data(self, data: str) -> None:
        if self.cell is not None:
            self.cell.append(data)


def parse_sp500(html: str) -> list[dict[str, Any]]:
    """The constituents table: ticker, name, GICS sector and sub-industry, date added."""
    p = _Tables()
    p.feed(html)
    want = ("symbol", "security", "gics sector", "gics sub", "date added")
    for t in p.tables:
        head = [h.lower() for h in (t[0] if t else [])]
        if not all(any(w in h for h in head) for w in want):
            continue
        ix = {w: next(i for i, h in enumerate(head) if w in h) for w in want}
        rows = []
        for r in t[1:]:
            if len(r) <= max(ix.values()):
                continue
            added = re.match(r"\d{4}-\d{2}-\d{2}", r[ix["date added"]])
            rows.append(
                {
                    "ticker": r[ix["symbol"]].strip(),
                    "name": r[ix["security"]].strip(),
                    "sector": r[ix["gics sector"]].strip(),
                    "sub_industry": r[ix["gics sub"]].strip(),
                    "added": date.fromisoformat(added.group(0)) if added else None,
                }
            )
        return rows
    raise ValueError("no S&P 500 constituents table (symbol, security, GICS, date added)")


def parse_ndx(text: str) -> list[dict[str, str]]:
    """Nasdaq's ``list-type/nasdaq100`` JSON: ticker and name."""
    rows = json.loads(text)["data"]["data"]["rows"]
    return [{"ticker": r["symbol"].strip(), "name": r["companyName"].strip()} for r in rows]


def parse_listed(nasdaq: str, other: str) -> list[dict[str, Any]]:
    """Nasdaq Trader's two pipe files: every US-listed common stock, ADR and fund."""
    out: list[dict[str, Any]] = []

    def rows(text: str) -> Iterable[dict[str, str]]:
        lines = [ln for ln in text.splitlines() if ln and not ln.startswith("File Creation")]
        head = lines[0].split("|")
        for ln in lines[1:]:
            yield dict(zip(head, ln.split("|"), strict=False))

    for r in rows(nasdaq):
        out.append(
            {"ticker": r["Symbol"], "name": r["Security Name"], "exchange": "Nasdaq",
             "etf": r.get("ETF") == "Y", "test": r.get("Test Issue") == "Y"}
        )  # fmt: skip
    for r in rows(other):
        out.append(
            {"ticker": r["ACT Symbol"], "name": r["Security Name"],
             "exchange": EXCHANGES.get(r.get("Exchange", ""), r.get("Exchange", "")),
             "etf": r.get("ETF") == "Y", "test": r.get("Test Issue") == "Y"}
        )  # fmt: skip
    return [
        r
        for r in out
        if not r["test"]
        and re.fullmatch(r"[A-Z]{1,5}(\.[A-Z])?", r["ticker"])
        and (r["etf"] or not NOT_COMMON.search(r["name"]))
    ]


def clean_name(name: str) -> str:
    """ "Palantir Technologies Inc. Class A Common Stock" → "palantir technologies"."""
    n = SUFFIX.sub(" ", name)
    words = normalise(n).replace("&", " & ").split()
    while words and words[-1] in CORP | {"&"}:
        words.pop()
    return " ".join(words)


def name_aliases(name: str) -> list[str]:
    full = clean_name(name)
    out = [full] if full else []
    words = full.split()
    if (
        len(words) == 2
        and words[1] in GENERIC_SECOND
        and words[0] not in WEAK_FIRST
        and len(words[0]) >= 4
    ):
        out.append(words[0])
    return out


@dataclass
class Built:
    assets: list[dict[str, Any]] = field(default_factory=list)
    aliases: dict[tuple[str, str], tuple[bool, str]] = field(default_factory=dict)
    report: dict[str, int] = field(default_factory=dict)


def build(
    cur: dict[str, Any],
    ext: dict[str, Any],
    listed: list[dict[str, Any]],
    sp500: list[dict[str, Any]],
    ndx: list[dict[str, str]],
    snapshot: date,
) -> Built:
    b = Built()
    base = {"snapshot": snapshot, "assets_version": ASSETS_VERSION}
    taken: set[str] = set()  # curated aliases: a generated name never overrides one
    for a in cur["assets"]:
        b.assets.append(
            {**base, "id": a["id"], "kind": a["kind"], "name": a["name"], "ticker": None,
             "proxy": a.get("proxy"), "source": "themes.yaml"}
        )  # fmt: skip
        for al in a.get("aliases") or []:
            n = normalise(al)
            b.aliases[(n, a["id"])] = (False, "themes.yaml")
            taken.add(n)

    spm = {r["ticker"]: r for r in sp500}
    ndm = {r["ticker"]: r for r in ndx}
    seen: set[str] = set()
    for r in listed:
        t = r["ticker"]
        if t in seen:
            continue
        seen.add(t)
        sp, nd = spm.get(t), ndm.get(t)
        b.assets.append(
            {**base, "id": f"{'fund' if r['etf'] else 'stock'}:{t}",
             "kind": "fund" if r["etf"] else "stock",
             "name": (sp or {}).get("name") or clean_name(r["name"]).title() or t,
             "ticker": t, "proxy": t.replace(".", "-"), "exchange": r["exchange"],
             "gics_sector": (sp or {}).get("sector"),
             "gics_sub_industry": (sp or {}).get("sub_industry"),
             "sp500": sp is not None, "sp500_added": (sp or {}).get("added"), "ndx": nd is not None,
             "source": "nasdaqtrader"}
        )  # fmt: skip
    by_ticker = {a["ticker"]: a["id"] for a in b.assets if a["ticker"]}
    cue = {normalise(w) for w in ext.get("needs_cue") or []}
    for t, spoken in (ext.get("stocks") or {}).items():
        aid = by_ticker.get(t)
        if not aid:
            b.report["extras_missing"] = b.report.get("extras_missing", 0) + 1
            continue
        for al in spoken:
            n = normalise(al)
            b.aliases[(n, aid)] = (n in cue, "extras.yaml")
            taken.add(n)
    for t in sorted(set(spm) | set(ndm)):
        aid = by_ticker.get(t)
        if not aid:
            continue
        names = {clean_name((spm.get(t) or ndm[t])["name"])}
        if t in ndm:
            names.add(clean_name(ndm[t]["name"]))
        for name in names:
            for al in name_aliases(name):
                if al and al not in taken:
                    b.aliases[(al, aid)] = (al in cue, "listing-name")
    b.report.update(
        {
            "curated": len(cur["assets"]),
            "listed": len(seen),
            "funds": sum(a["kind"] == "fund" for a in b.assets),
            "sp500": len(sp500),
            "sp500_matched": sum(1 for t in spm if t in by_ticker),
            "ndx": len(ndx),
            "ndx_matched": sum(1 for t in ndm if t in by_ticker),
            "aliases": len(b.aliases),
            "needs_cue": sum(1 for c, _ in b.aliases.values() if c),
        }
    )
    return b


COLUMNS = (
    "id", "kind", "name", "ticker", "proxy", "gics_sector", "gics_sub_industry", "exchange",
    "sp500", "sp500_added", "ndx", "source", "snapshot", "assets_version",
)  # fmt: skip


def write(con: Any, b: Built) -> None:
    cols = ", ".join(COLUMNS)
    upd = ", ".join(f"{c} = EXCLUDED.{c}" for c in COLUMNS[1:])
    rows = [
        tuple(a.get(c, False if c in ("sp500", "ndx") else None) for c in COLUMNS) for a in b.assets
    ]
    with con.cursor() as cur:
        cur.executemany(
            f"INSERT INTO rt.assets ({cols}) VALUES ({', '.join(['%s'] * len(COLUMNS))}) "
            f"ON CONFLICT (id) DO UPDATE SET {upd}",
            rows,
        )
        cur.execute("DELETE FROM rt.aliases")
        cur.executemany(
            "INSERT INTO rt.aliases (alias, asset_id, needs_cue, source) VALUES (%s, %s, %s, %s)",
            [(al, aid, cue, src) for (al, aid), (cue, src) in b.aliases.items()],
        )
    con.commit()


def seed(con: Any, local: Path | None = None, log: Callable[[str], None] = print) -> dict[str, int]:
    """Fetch (or read from ``local``/<name>.{html,json,txt}) the four sources, build, write."""

    def get(name: str) -> str:
        if local:
            hits = sorted(local.glob(f"{name}.*"))
            if hits:
                return hits[0].read_text()
        log(f"  fetching {name}: {SOURCES[name]}")
        return fetch(SOURCES[name])

    listed = parse_listed(get("nasdaqlisted"), get("otherlisted"))
    sp500 = parse_sp500(get("sp500"))
    try:
        ndx = parse_ndx(get("ndx"))
    except Exception as e:  # risk r10: the list moves; membership is a tag, not a gate
        log(f"  Nasdaq-100 list unavailable ({type(e).__name__}); ndx tags left false")
        ndx = []
    b = build(curated(), extras(), listed, sp500, ndx, date.today())
    write(con, b)
    return b.report
