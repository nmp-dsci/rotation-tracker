"""Keyword themes for the viewer's chart: which sectors and assets come up, quarter by quarter.

These are word counts over the macro-and-flows sections, not rotation calls. Extraction and
the taxonomy are still open decisions (AGENTS.md), so nothing here is a signal.

A theme is ranked by mentions per weekly wrap. Most themes come up in nearly every 30-minute
wrap, so "weeks that mention it" saturates; how often it comes up does not.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

THEMES_VERSION = "themes/v0"
CHART_SIZE = 10

# (name, Postgres regex body). Matched case-insensitively as whole words: \m(?:body)\M.
THEMES: tuple[tuple[str, str], ...] = (
    ("Semiconductors", r"semiconductors?|semis|chips?|nvidia|smh"),
    ("Software & SaaS", r"software|saas|igv"),
    ("AI", r"ai|artificial intelligence"),
    ("Big tech", r"big tech|mega ?caps?|magnificent (?:7|seven)|mag ?7"),
    ("Banks & financials", r"banks?|banking|financials|xlf"),
    ("Energy & oil", r"energy|oil|crude|brent|xle"),
    ("Healthcare", r"health ?care|pharma|biotech|xlv"),
    ("Small caps", r"small[- ]caps?|russell(?: 2000)?|iwm"),
    ("Gold & silver", r"gold|silver"),
    ("Crypto", r"bitcoin|crypto|ethereum"),
    ("Bonds & yields", r"bonds?|yields?|treasur(?:y|ies)"),
    ("The dollar", r"dxy|dollar index|the dollar|us dollar"),
    ("China", r"china|chinese"),
    ("Utilities", r"utilities|xlu"),
    ("Consumer", r"consumer|retail|xly"),
    ("Industrials", r"industrials|xli"),
    ("Real estate", r"real estate|reits?"),
    ("Defensives", r"defensives?|staples"),
)


# s03: each theme pinned to one asset, so the keyword line, the mined line and one price share a
# row (the plan's chart map). The asset's primary series in assets/proxies.yaml prices the row.
ASSET_OF: dict[str, str] = {
    "Semiconductors": "theme:semis",
    "Software & SaaS": "theme:software",
    "AI": "theme:ai",
    "Big tech": "theme:mag7",
    "Banks & financials": "theme:banks",
    "Energy & oil": "sector:energy",
    "Healthcare": "sector:healthcare",
    "Small caps": "index:rut",
    "Gold & silver": "commodity:gold",
    "Crypto": "crypto:btc",
    "Bonds & yields": "rates:us10y",
    "The dollar": "fx:dxy",
    "China": "theme:china-stocks",
    "Utilities": "sector:utilities",
    "Consumer": "sector:discretionary",
    "Industrials": "sector:industrials",
    "Real estate": "sector:real-estate",
    "Defensives": "theme:defensives",
}


def pattern(body: str) -> str:
    return rf"\m(?:{body})\M"


@dataclass(frozen=True)
class Entry:
    theme: str  # the name ranked: a theme, or an asset id on the assets view
    mentions: int  # in the quarter's macro-and-flows sections
    weeks_hit: int  # weekly wraps in the quarter that mention it at least once
    rate: float  # mentions per weekly wrap
    rank: int | None  # None: not mentioned in the quarter (listed only with size=None)
    prev_rank: int | None  # None: not mentioned at all last quarter
    move: str  # new (not on last quarter's chart) | up | down | same | none (unranked)
    history: list[float]  # rate in every quarter on record, oldest first: one x scale for all
    bullish: list[float]  # the same, counting only hits inside calls bullish on the theme
    bearish: list[float]  # ... and bearish on it; the rest are neutral, mixed or not in a call
    total: int  # mentions in every quarter on record


def _order(mentions: dict[str, dict[date, int]], weeks: dict[date, int], q: date) -> dict[str, int]:
    n = weeks.get(q, 0)
    rates = [(name, by_q.get(q, 0) / n if n else 0.0) for name, by_q in mentions.items()]
    rates.sort(key=lambda r: (-r[1], r[0]))
    return {name: i + 1 for i, (name, rate) in enumerate(rates) if rate > 0}


def rank(
    mentions: dict[str, dict[date, int]],
    weeks_hit: dict[str, dict[date, int]],
    weeks: dict[date, int],
    quarter: date,
    size: int | None = CHART_SIZE,
    bullish: dict[str, dict[date, int]] | None = None,
    bearish: dict[str, dict[date, int]] | None = None,
) -> tuple[list[Entry], list[str]]:
    """The chart for ``quarter``: the top ``size`` names by mentions per weekly wrap, each
    with its move against the quarter before, and the names that fell off the chart.

    ``size=None`` lists every name: the ranked ones, then the ones not mentioned in
    ``quarter`` (unranked, most mentioned over all quarters first), so nothing falls off."""

    def per_wrap(counts: dict[date, int]) -> list[float]:
        return [counts.get(q, 0) / weeks[q] if weeks[q] else 0.0 for q in sorted(weeks)]

    quarters = sorted(q for q in weeks if q <= quarter)
    prev = quarters[-2] if len(quarters) > 1 else None
    now = _order(mentions, weeks, quarter)
    before = _order(mentions, weeks, prev) if prev else {}

    def on_chart(r: int | None) -> bool:
        return r is not None and (size is None or r <= size)

    def entry(name: str, r: int | None) -> Entry:
        p = before.get(name)
        last = p if on_chart(p) else None  # its place on last quarter's chart
        move = (
            "none" if r is None
            else "new" if last is None
            else "up" if last > r
            else "down" if last < r
            else "same"
        )  # fmt: skip
        n = mentions[name].get(quarter, 0)
        hit = weeks_hit.get(name, {}).get(quarter, 0)
        up = per_wrap((bullish or {}).get(name, {}))
        down = per_wrap((bearish or {}).get(name, {}))
        total = sum(mentions[name].values())
        return Entry(
            name, n, hit, n / weeks[quarter], r, p, move, per_wrap(mentions[name]), up, down, total
        )

    ranked = sorted(now.items(), key=lambda kv: kv[1])
    entries = [entry(name, r) for name, r in (ranked if size is None else ranked[:size])]
    if size is None:
        rest = sorted(
            (n for n in mentions if n not in now), key=lambda n: (-sum(mentions[n].values()), n)
        )
        entries += [entry(name, None) for name in rest]
    listed = {e.theme for e in entries}
    fell = [n for n, r in sorted(before.items(), key=lambda kv: kv[1]) if on_chart(r)]
    return entries, [n for n in fell if n not in listed]
