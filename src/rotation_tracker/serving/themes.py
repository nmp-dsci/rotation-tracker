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


def pattern(body: str) -> str:
    return rf"\m(?:{body})\M"


@dataclass(frozen=True)
class Entry:
    theme: str
    mentions: int  # in the quarter's macro-and-flows sections
    weeks_hit: int  # weekly wraps in the quarter that mention it at least once
    rate: float  # mentions per weekly wrap
    rank: int
    prev_rank: int | None  # None: not mentioned at all last quarter
    move: str  # new (not on last quarter's chart) | up | down | same
    history: list[float]  # rate per quarter, oldest first, ending at this one


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
    size: int = CHART_SIZE,
    span: int = 8,
) -> tuple[list[Entry], list[str]]:
    """The chart for ``quarter``: the top ``size`` themes by mentions per weekly wrap, each
    with its move against the quarter before, and the themes that fell off the chart."""
    quarters = sorted(q for q in weeks if q <= quarter)
    prev = quarters[-2] if len(quarters) > 1 else None
    now = _order(mentions, weeks, quarter)
    before = _order(mentions, weeks, prev) if prev else {}
    window = quarters[-span:]
    entries = []
    for name, r in sorted(now.items(), key=lambda kv: kv[1])[:size]:
        p = before.get(name)
        last = p if p is not None and p <= size else None  # its place on last quarter's chart
        move = "new" if last is None else "up" if last > r else "down" if last < r else "same"
        n = mentions[name].get(quarter, 0)
        history = [mentions[name].get(q, 0) / weeks[q] if weeks.get(q) else 0.0 for q in window]
        hit = weeks_hit.get(name, {}).get(quarter, 0)
        entries.append(Entry(name, n, hit, n / weeks[quarter], r, p, move, history))
    on_chart = {e.theme for e in entries}
    fell = [n for n, r in sorted(before.items(), key=lambda kv: kv[1]) if r <= size]
    return entries, [n for n in fell if n not in on_chart]
