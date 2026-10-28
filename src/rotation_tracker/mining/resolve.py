"""Spoken asset → ``rt.assets`` id. Resolution is code, not the model.

The extractor returns an asset as it was said plus its best ticker and kind guess. The alias
table decides: a curated or generated alias first, then the ticker guess, else the asset goes to
the unknown queue (``rt assets unknown``). An alias that is also an ordinary word ("target",
"apple") only resolves when the ticker guess names the same stock. A guess that cannot be a US
listing (``^DJT``, ``CL=F``) never reaches the stock map, however its letters spell.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

Resolution = Literal["alias", "ticker", "ambiguous", "unknown"]

LEAD = ("the ", "a ", "some ", "these ", "those ", "all ", "certain ", "all the ")
TAIL = {
    "stock", "stocks", "shares", "share", "sector", "sectors", "names", "name", "space", "etf",
    "etfs", "index", "market", "markets", "price", "prices", "futures", "complex", "trade",
    "companies", "company", "plays", "play", "industry", "industries", "area", "related",
}  # fmt: skip
STOCKISH = {"stock", "fund"}
# Indices (^VIX), futures and FX (CL=F, EURUSD=X), crypto pairs (BTC-USD) and non-US listings
# (RHM.DE, 0700.HK, 7203.T). A one-letter suffix on a letter ticker is a US share class (BRK.B).
NOT_US = re.compile(r"^\^|=|-USD$|\.[A-Z]{2,}$|\d.*\.[A-Z]$")


def normalise(s: str) -> str:
    """Lower case, words only (``&`` kept for "S&P"), one space, no leading "the"."""
    s = s.lower().replace("’", "'").replace("'s", "s")
    s = re.sub(r"[^a-z0-9&]+", " ", s).strip()
    return s[4:] if s.startswith("the ") else s


def ticker_key(t: str) -> str:
    """``BRK.B``, ``BRK-B``, ``$brkb`` → ``BRKB``."""
    return re.sub(r"[^A-Z0-9]", "", t.upper())


def symbol_root(t: str) -> str:
    """``^DJT`` → ``djt``, ``CL=F`` → ``cl``, ``BTC-USD`` → ``btc``: the alias a symbol names."""
    return normalise(re.sub(r"(=.*|-USD|\.[A-Z]+)$", "", t.lstrip("^")))


def variants(spoken: str) -> list[str]:
    """The spoken form, then with leading determiners and trailing generic words removed."""
    n = normalise(spoken)
    out = [n]
    for lead in LEAD:
        if n.startswith(lead):
            n = n[len(lead) :]
            out.append(n)
    words = n.split()
    while len(words) > 1 and words[-1] in TAIL:
        words = words[:-1]
        out.append(" ".join(words))
    return list(dict.fromkeys(v for v in out if v))


@dataclass(frozen=True)
class Resolved:
    asset_id: str | None
    how: Resolution


class Resolver:
    """Built from ``rt.aliases`` and ``rt.assets`` rows (or test fixtures)."""

    def __init__(
        self,
        aliases: Iterable[tuple[str, str, bool]],
        assets: Iterable[tuple[str, str, str | None, str | None]],
        not_assets: Iterable[str] = (),
    ) -> None:
        """``aliases``: (alias, asset_id, needs_cue); ``assets``: (id, kind, ticker, proxy)."""
        self.kind: dict[str, str] = {}
        self.ticker: dict[str, str] = {}
        self.by_ticker: dict[str, str] = {}
        self.by_proxy: dict[str, str] = {}  # curated rows (no listing ticker) by their symbol
        for aid, kind, ticker, proxy in assets:
            self.kind[aid] = kind
            if ticker:
                self.ticker[aid] = ticker_key(ticker)
                if kind in STOCKISH:
                    self.by_ticker.setdefault(ticker_key(ticker), aid)
            elif proxy and kind != "macro":  # a macro row's proxy stands in; it is not the asset
                self.by_proxy.setdefault(proxy.upper(), aid)
        self.by_alias: dict[str, list[tuple[str, bool]]] = defaultdict(list)
        for alias, aid, cue in aliases:
            self.by_alias[normalise(alias)].append((aid, cue))
        self.never = {normalise(w) for w in not_assets}

    def _from_alias(self, key: str, tk: str, kind: str | None) -> Resolved | None:
        cands = self.by_alias.get(key)
        if not cands:
            return None
        ok = [aid for aid, cue in cands if not cue or (tk and self.ticker.get(aid) == tk)]
        if not ok:
            return Resolved(None, "ambiguous")
        if len(ok) > 1 and kind:
            same = [a for a in ok if self.kind.get(a) == kind]
            ok = same or ok
        if len(set(ok)) > 1:
            return Resolved(None, "ambiguous")
        return Resolved(ok[0], "alias")

    def _from_ticker(self, raw: str, kind: str | None) -> Resolved | None:
        tk = ticker_key(raw)
        if not tk:
            return None
        if NOT_US.search(raw):  # a curated row by its root's alias or its proxy, never a US stock
            curated = self._from_alias(symbol_root(raw), "", kind)
            if curated and curated.asset_id:
                return curated
            return Resolved(self.by_proxy[raw], "ticker") if raw in self.by_proxy else None
        stock = self.by_ticker.get(tk)
        curated = self._from_alias(tk.lower(), tk, kind)
        if kind in STOCKISH and stock:
            return Resolved(stock, "ticker")
        if curated and curated.asset_id:
            return curated
        return Resolved(stock, "ticker") if stock else None

    def resolve(self, spoken: str, ticker: str | None = None, kind: str | None = None) -> Resolved:
        raw = (ticker or "").strip().upper()
        tk = "" if NOT_US.search(raw) else ticker_key(raw)  # only a US symbol cues a stock alias
        vs = variants(spoken)
        if any(v in self.never for v in vs[:1]):
            return Resolved(None, "unknown")
        held: Resolved | None = None
        for v in vs:
            r = self._from_alias(v, tk, kind)
            if r and r.asset_id:
                return r
            held = held or r
        return self._from_ticker(raw, kind) or held or Resolved(None, "unknown")


def load(con: object) -> Resolver:
    """The resolver over the database's alias table (``con``: a psycopg connection)."""
    from rotation_tracker.mining.universe import extras

    cur = con.execute  # type: ignore[attr-defined]
    aliases = [
        (a, i, bool(c)) for a, i, c in cur("SELECT alias, asset_id, needs_cue FROM rt.aliases")
    ]
    assets = [(i, k, t, p) for i, k, t, p in cur("SELECT id, kind, ticker, proxy FROM rt.assets")]
    return Resolver(aliases, assets, extras().get("not_assets") or [])
