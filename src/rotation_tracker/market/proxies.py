"""proxies/v2: which price series stands for each asset (``assets/proxies.yaml``).

A series is a typed key shared with market-getdata: ``yahoo:<SYMBOL>``, ``fred:<ID>``,
``basket:<id>``, or ``none`` (deliberately unpriced, with a reason). Every curated asset has a row
in the file; a listed stock or fund is priced by its own ticker in Yahoo spelling unless the file
says otherwise. Each asset has exactly one primary and any number of companions.

``rt assets seed`` writes the resolution of every asset to ``rt.asset_proxies``;
``rt assets export-symbols`` writes the instrument list market-getdata fetches;
``rt assets check-proxies`` fails when an asset with a mention resolves to nothing.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml

from rotation_tracker.config import ROOT

PROXIES_VERSION = "proxies/v2"
PROXIES_FILE = ROOT / "assets" / "proxies.yaml"
EXPORT_DEFAULT = ROOT.parent / "market-getdata" / "instruments" / "rotation-tracker.txt"
NONE = "none"
LISTED = ("stock", "fund")  # kinds the listings give; priced by their own ticker by default
KINDS = ("index", "sector", "theme", "stock", "fund", "crypto", "rates", "credit", "commodity",
         "fx", "macro")  # fmt: skip
SOURCES = ("yahoo", "fred", "basket")
SERIES = re.compile(r"^(yahoo:[A-Z0-9^][A-Z0-9^.=-]*|fred:[A-Z0-9_]+|basket:[a-z0-9-]+)$")
REASONS = ("proxy", "named", "companion")  # the order reasons are written in

Role = Literal["primary", "companion"]


@dataclass(frozen=True)
class Proxy:
    """One row of ``rt.asset_proxies``."""

    asset_id: str
    series: str  # a typed key, or "none" (primary only)
    role: Role
    ord: int = 0  # companions in the file's order; the primary is 0
    from_date: date | None = None
    to_date: date | None = None
    note: str | None = None  # for "none", the reason


def source(series: str) -> str | None:
    """``yahoo:SMH`` → ``yahoo``; ``none`` → None."""
    return series.split(":", 1)[0] if ":" in series else None


def symbol(series: str) -> str:
    """``yahoo:BRK-B`` → ``BRK-B``; ``basket:mag7`` → ``mag7``."""
    return series.split(":", 1)[1] if ":" in series else series


def yahoo_spelling(ticker: str) -> str:
    """A listing ticker in Yahoo's spelling: a share class takes a dash (``BRK.B`` → ``BRK-B``)."""
    return ticker.replace(".", "-")


def default_series(kind: str, ticker: str | None) -> str | None:
    """A listed stock or fund is priced by its own ticker."""
    return f"yahoo:{yahoo_spelling(ticker)}" if kind in LISTED and ticker else None


class ProxyError(ValueError):
    pass


def _entry(asset_id: str, raw: Any, role: Role, ord_: int) -> Proxy:
    if isinstance(raw, str):
        raw = {"series": raw}
    if not isinstance(raw, dict) or not isinstance(raw.get("series"), str):
        raise ProxyError(f"{asset_id}: a {role} must be a key or {{series, from, to, note}}")
    extra = set(raw) - {"series", "from", "to", "note"}
    if extra:
        raise ProxyError(f"{asset_id}: unknown field(s) {sorted(extra)} on {raw['series']}")
    for k in ("from", "to"):
        if raw.get(k) is not None and not isinstance(raw[k], date):
            raise ProxyError(f"{asset_id}: {k} must be a date (YYYY-MM-DD)")
    p = Proxy(asset_id, raw["series"], role, ord_, raw.get("from"), raw.get("to"), raw.get("note"))
    if p.from_date and p.to_date and p.from_date > p.to_date:
        raise ProxyError(f"{asset_id}: {p.series} runs from {p.from_date} to {p.to_date}")
    return p


@dataclass(frozen=True)
class Proxies:
    """``assets/proxies.yaml``, validated."""

    version: str
    baskets: Mapping[str, str]
    explicit: Mapping[str, tuple[Proxy, ...]]  # asset id → primary first, then companions

    @classmethod
    def parse(cls, doc: Mapping[str, Any]) -> Proxies:
        if doc.get("version") != PROXIES_VERSION:
            raise ProxyError(f"version must be {PROXIES_VERSION}, not {doc.get('version')!r}")
        baskets = dict(doc.get("baskets") or {})
        explicit: dict[str, tuple[Proxy, ...]] = {}
        for aid, body in (doc.get("assets") or {}).items():
            if not isinstance(body, dict) or "primary" not in body:
                raise ProxyError(f"{aid}: needs a primary (a series or none)")
            extra = set(body) - {"primary", "companions", "reason"}
            if extra:
                raise ProxyError(f"{aid}: unknown field(s) {sorted(extra)}")
            if body["primary"] == NONE:
                reason = str(body.get("reason") or "").strip()
                if not reason:
                    raise ProxyError(f"{aid}: primary none needs a reason")
                if body.get("companions"):
                    raise ProxyError(f"{aid}: an unpriced asset has no companions")
                explicit[aid] = (Proxy(aid, NONE, "primary", 0, note=reason),)
                continue
            if body.get("reason"):
                raise ProxyError(f"{aid}: a reason is for primary none; use a note")
            rows = [_entry(aid, body["primary"], "primary", 0)]
            rows += [
                _entry(aid, c, "companion", i + 1)
                for i, c in enumerate(body.get("companions") or [])
            ]
            seen: set[str] = set()
            for p in rows:
                if p.series == NONE:
                    raise ProxyError(f"{aid}: none is a primary only")
                if not SERIES.match(p.series):
                    raise ProxyError(
                        f"{aid}: {p.series!r} is not a typed key (yahoo:, fred:, basket:)"
                    )
                if source(p.series) == "basket" and symbol(p.series) not in baskets:
                    raise ProxyError(f"{aid}: unknown basket {symbol(p.series)!r}")
                if p.series in seen:
                    raise ProxyError(f"{aid}: {p.series} is listed twice")
                seen.add(p.series)
            explicit[aid] = tuple(rows)
        return cls(str(doc["version"]), baskets, explicit)

    def resolve(self, asset_id: str, kind: str, ticker: str | None) -> tuple[Proxy, ...]:
        """Primary first, then companions; empty when nothing prices the asset."""
        if asset_id in self.explicit:
            return self.explicit[asset_id]
        s = default_series(kind, ticker)
        return (Proxy(asset_id, s, "primary"),) if s else ()

    def legacy(self, asset_id: str, kind: str, ticker: str | None) -> str | None:
        """``rt.assets.proxy``: the primary's bare Yahoo symbol, kept for compatibility."""
        rows = self.resolve(asset_id, kind, ticker)
        if rows and source(rows[0].series) == "yahoo":
            return symbol(rows[0].series)
        return None


@lru_cache(maxsize=1)
def load(path: Path = PROXIES_FILE) -> Proxies:
    return Proxies.parse(yaml.safe_load(path.read_text()))


def check_curated(px: Proxies, curated: Iterable[Mapping[str, Any]]) -> list[str]:
    """Every curated asset has a row; every row is a curated asset or a listed stock or fund."""
    ids = {a["id"] for a in curated}
    problems = [f"{a}: curated in themes.yaml, missing from proxies.yaml" for a in sorted(ids)
                if a not in px.explicit]  # fmt: skip
    problems += [
        f"{a}: in proxies.yaml but not a curated asset or a listing row"
        for a in sorted(px.explicit)
        if a not in ids and a.split(":", 1)[0] not in LISTED
    ]
    return problems


# ── seed ──────────────────────────────────────────────────────────────────────────────
def rows_for(
    px: Proxies, assets: Iterable[tuple[str, str, str | None]]
) -> tuple[list[Proxy], list[str]]:
    """``rt.asset_proxies`` for every (id, kind, ticker), and the ids nothing resolves."""
    rows: list[Proxy] = []
    unresolved: list[str] = []
    for aid, kind, ticker in assets:
        got = px.resolve(aid, kind, ticker)
        if got:
            rows.extend(got)
        else:
            unresolved.append(aid)
    return rows, unresolved


def write(con: Any, rows: list[Proxy]) -> dict[str, int]:
    """Replace ``rt.asset_proxies`` (one transaction) and set ``rt.assets.proxy`` to match."""
    with con.cursor() as cur:
        cur.execute("DELETE FROM rt.asset_proxies")
        cur.executemany(
            """INSERT INTO rt.asset_proxies
                 (asset_id, series, role, ord, from_date, to_date, note)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            [(p.asset_id, p.series, p.role, p.ord, p.from_date, p.to_date, p.note) for p in rows],
        )
        bare = "CASE WHEN left(p.series, 6) = 'yahoo:' THEN substr(p.series, 7) END"
        cur.execute(
            f"""UPDATE rt.assets a SET proxy = {bare}
                FROM rt.asset_proxies p
                WHERE p.asset_id = a.id AND p.role = 'primary'
                  AND a.proxy IS DISTINCT FROM {bare}"""
        )
        moved = cur.rowcount
    con.commit()
    primaries = [p for p in rows if p.role == "primary"]
    return {
        "asset_proxies": len(rows),
        "primary": len(primaries),
        "priced": sum(p.series != NONE for p in primaries),
        "none": sum(p.series == NONE for p in primaries),
        "companion": len(rows) - len(primaries),
        "proxy_column": moved,
    }


# ── check ─────────────────────────────────────────────────────────────────────────────
def check(
    px: Proxies, mentioned: Iterable[tuple[str, str, str | None]]
) -> tuple[dict[str, int], list[str]]:
    """Every asset with a mention resolves to a typed primary or a reasoned none."""
    counts = {"assets": 0, "priced": 0, "none": 0, "unresolved": 0}
    problems: list[str] = []
    for aid, kind, ticker in mentioned:
        counts["assets"] += 1
        rows = px.resolve(aid, kind, ticker)
        primary = rows[0] if rows else None
        if primary is None:
            counts["unresolved"] += 1
            problems.append(f"{aid} ({kind}): no series and no reasoned none")
        elif primary.series == NONE:
            counts["none"] += 1
            if not (primary.note or "").strip():
                problems.append(f"{aid}: none without a reason")
        elif not SERIES.match(primary.series):
            counts["unresolved"] += 1
            problems.append(f"{aid}: {primary.series!r} is not a typed key")
        else:
            counts["priced"] += 1
    return counts, problems


# ── export ────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Line:
    series: str
    kind: str
    reasons: tuple[str, ...]

    def __str__(self) -> str:
        return f"{self.series}\t{self.kind}\t{','.join(self.reasons)}"


def export(
    px: Proxies,
    curated: Iterable[tuple[str, str]],
    mentioned: Iterable[tuple[str, str, str | None]],
    listing_kind: Mapping[str, str],
) -> list[Line]:
    """The instrument list market-getdata fetches (ai_specs/s03_prices.md, the contract).

    ``curated``: (id, kind) of every curated asset; ``mentioned``: (id, kind, ticker) of every
    asset with a mention; ``listing_kind``: Yahoo symbol → ``stock``/``fund`` for every listing row.

    Reasons: ``proxy``, a primary of a curated asset; ``named``, the primary of a stock or fund he
    names; ``companion``. Kind: ``basket`` for a basket; else the kind of the series' own asset
    (the listing with that ticker, else a curated asset it is the primary of, macro last); else
    ``fred`` for a FRED series nobody owns; else the kind of an asset it accompanies.
    """
    curated = list(curated)
    curated_ids = {aid for aid, _ in curated}
    reasons: dict[str, set[str]] = {}
    owner: dict[str, list[str]] = {}  # series → kinds of assets it is the primary of
    user: dict[str, list[str]] = {}  # series → kinds of assets it accompanies

    def use(p: Proxy, kind: str, why: str) -> None:
        if p.series == NONE:
            return
        reasons.setdefault(p.series, set()).add(why)
        (owner if p.role == "primary" else user).setdefault(p.series, []).append(kind)

    for aid, kind in curated:
        for p in px.resolve(aid, kind, None):
            use(p, kind, "proxy" if p.role == "primary" else "companion")
    for aid, kind, ticker in mentioned:
        if aid in curated_ids and kind not in LISTED:
            continue  # already in, as a proxy
        for p in px.resolve(aid, kind, ticker):
            if p.role == "companion":
                use(p, kind, "companion")
            elif kind in LISTED:
                use(p, kind, "named")
            else:
                use(p, kind, "proxy")

    def first(kinds: list[str]) -> str | None:
        ranked = sorted(kinds, key=lambda k: k == "macro")  # stable: a macro row last
        return ranked[0] if ranked else None

    def kind_of(s: str) -> str:
        src = source(s)
        if src == "basket":
            return "basket"
        if src == "yahoo" and symbol(s) in listing_kind:
            return listing_kind[symbol(s)]
        own = first(owner.get(s, []))
        if own:
            return own
        if src == "fred":
            return "fred"
        return first(user.get(s, [])) or "fred"

    order = {src: i for i, src in enumerate(SOURCES)}
    keys = sorted(reasons, key=lambda s: (order.get(source(s) or "", 9), s))
    return [Line(s, kind_of(s), tuple(r for r in REASONS if r in reasons[s])) for s in keys]


def render(lines: list[Line]) -> str:
    """The file, with a header; ``#`` lines and blank lines are ignored by the reader."""
    by_src: dict[str, list[Line]] = {}
    for ln in lines:
        by_src.setdefault(source(ln.series) or "", []).append(ln)
    count = {r: sum(r in ln.reasons for ln in lines) for r in REASONS}
    head = [
        "# rotation-tracker → market-getdata: the series rotation-tracker prices (s03_prices.md).",
        "# Written by `rt assets export-symbols` from assets/proxies.yaml and the rotation",
        "# database; do not edit by hand. One series per line, tab-separated:",
        "# <typed key>\\t<kind>\\t<reasons>   reasons: proxy, named, companion",
        f"# {PROXIES_VERSION} · {len(lines)} series · "
        + " · ".join(f"{count[r]} {r}" for r in REASONS),
    ]
    body: list[str] = []
    for src in SOURCES:
        if by_src.get(src):
            body += ["", f"# {src} · {len(by_src[src])}", *(str(ln) for ln in by_src[src])]
    return "\n".join(head + body) + "\n"


def parse_export(text: str) -> list[Line]:
    """The reader's side of the contract: tab-separated, ``#`` comments and blanks ignored."""
    out = []
    for raw in text.splitlines():
        ln = raw.strip()
        if not ln or ln.startswith("#"):
            continue
        series, kind, reasons = ln.split("\t")
        out.append(Line(series, kind, tuple(reasons.split(","))))
    return out
