"""play/v0: the seed keywords as an extractor, the zero-cost baseline play/v1 must beat.

A keyword hit opens a window of words around it; the window becomes a mention when an alias
names an asset inside it. The play comes from the keyword, the direction from cue words in the
window, roles from "out of" / "into" / "versus". It fills the same table through the same gates
as the LLM, so the eval compares like with like.
"""

from __future__ import annotations

import bisect
import re
from typing import Any

from rotation_tracker.mining import corpus
from rotation_tracker.mining.locate import _norm_map, norm
from rotation_tracker.mining.schema import BASELINE_VERSION, AssetRef, Mention

VERSION = BASELINE_VERSION
HALF = 12  # words either side of the keyword
# In the order a hit is assigned when two plays' keywords share a window (prompt.md's order).
SEEDS: dict[str, str] = {
    "rotation": r"rotat\w*|money (?:is )?moving|moving (?:in ?to|out of)|flow(?:ing|s)? in ?to|"
    r"broaden\w*|leadership",
    "relative": r"versus|vs|outperform\w*|underperform\w*|ratio|relative to|compared to",
    "flow": r"dark pools?|options flow|call buying|put buying|(?:buying|bought) (?:calls|puts)|"
    r"gamma|hedge funds?|biggest players|retail (?:investors|traders)|insiders?|buybacks?|"
    r"inflows?|outflows?|cot report|fund managers?|smart money|whales?",
    "valuation": r"undervalued|overvalued|cheap|expensive|frothy|bubble|bargain|p e ratios?|"
    r"price to earnings|fair value|valuations?",
    "technical": r"overbought|oversold|break(?:ing)? ?out|break(?:ing)? ?down|pull ?back|"
    r"correction|capitulat\w*|melt ?up|support|resistance|breadth|all time highs?|new highs?|"
    r"double top|topp(?:ed|ing)|bottom(?:ed|ing)?",
    "regime": r"risk on|risk off|bull market|bear market|recession|liquidity|rate (?:cuts?|hikes?)|"
    r"worst (?:two |three )?months|seasonality|santa rally|crash",
    "call": r"i like|big fan|stay away|don ?t touch|watch ?list|trade idea|get in ?to|i m buying|"
    r"i m (?:long|short)|i would (?:be )?(?:buying|selling|adding)|load(?:ing)? up",
}
CUES: dict[str, list[tuple[str, str]]] = {
    "flow": [(r"sell|sold|dump|outflow|put buying|puts|short|distribut", "selling")],
    "valuation": [
        (r"undervalued|cheap|bargain", "under"),
        (r"overvalued|expensive|frothy|bubble", "over"),
    ],
    "technical": [
        (
            r"overbought|break(?:ing)? ?down|topp|resistance|pull ?back|correction|double top",
            "bearish",
        ),
        (
            r"oversold|break(?:ing)? ?out|bottom|support|new high|all time high|capitulat|melt ?up",
            "bullish",
        ),
    ],  # fmt: skip
    "regime": [
        (r"risk on", "risk_on"),
        (r"risk off", "risk_off"),
        (r"bull market", "bull"),
        (r"bear market|recession|crash", "bear"),
    ],
    "call": [(r"stay away|don ?t touch", "avoid"), (r"short", "short"), (r"watch", "watch")],
}
DEFAULT = {"flow": "buying", "valuation": "fair", "technical": "neutral", "regime": "neutral",
           "relative": "a_over_b", "call": "long", "other": "neutral"}  # fmt: skip
NOISY = {"stocks", "markets", "market", "value", "growth", "yield", "credit", "coins", "rates",
         "consumer", "earnings", "debt", "war", "fiscal", "conflict", "positioning", "sentiment",
         "defense", "space", "travel", "media", "medical", "international", "bank", "mining",
         "energy", "financial", "industrial", "communication", "insurance", "jobs", "employment",
         "profits", "trade", "commodity", "materials", "technology", "liquidity",
         "recession"}  # fmt: skip
KEYWORDS = re.compile("|".join(f"(?P<{p}>\\b(?:{rx})\\b)" for p, rx in SEEDS.items()))


class Scanner:
    def __init__(self, aliases: list[tuple[str, str, str]]) -> None:
        """``aliases``: (alias, asset_id, kind) for aliases that need no cue."""
        self.kind: dict[str, str] = {}
        best: dict[str, tuple[str, str]] = {}
        for alias, aid, kind in aliases:
            n = norm(alias)
            if len(n) < 3 or n in NOISY:
                continue
            best.setdefault(n, (aid, kind))
        self.asset = best
        body = "|".join(re.escape(a) for a in sorted(best, key=len, reverse=True))
        self.rx = re.compile(rf"\b(?:{body})\b")

    @classmethod
    def from_db(cls, con: Any) -> Scanner:
        rows = con.execute(
            """SELECT l.alias, l.asset_id, a.kind
               FROM rt.aliases l JOIN rt.assets a ON a.id = l.asset_id
               WHERE NOT l.needs_cue"""
        ).fetchall()
        return cls([(a, i, k) for a, i, k in rows])

    def scan(self, week: corpus.Week) -> list[Mention]:
        out: list[Mention] = []
        for idx, sec in sorted(week.read.items()):
            t, pos = _norm_map(sec.text)
            words = [m.span() for m in re.finditer(r"\S+", t)]
            starts = [s for s, _ in words]
            names = [(m.start(), m.end(), m.group(0)) for m in self.rx.finditer(t)]
            last: tuple[str, int] | None = None
            for hit in KEYWORDS.finditer(t):
                play = hit.lastgroup or "other"
                w = _word_at(starts, hit.start())
                lo, hi = max(w - HALF, 0), min(w + HALF, len(words) - 1)
                a, b = words[lo][0], words[hi][1]
                inside = [n for n in names if n[0] >= a and n[1] <= b]
                if not inside:
                    continue
                if last and last[0] == play and a < last[1]:
                    continue
                last = (play, b)
                text = t[a:b]
                assets = _roles(play, t, inside, self.asset)
                out.append(
                    Mention(
                        section=idx,
                        quote=sec.text[pos[a] : pos[b - 1] + 1],
                        play=play,  # type: ignore[arg-type]
                        direction=_direction(play, text),  # type: ignore[arg-type]
                        assets=assets,
                        speaker="reported" if play == "flow" else "him",
                        reported_source=None,
                        modality="recommended" if play == "call" else "observed",
                        horizon="unspecified",
                        confidence=0.5,
                    )
                )
        return out


def _word_at(starts: list[int], pos: int) -> int:
    return max(bisect.bisect_right(starts, pos) - 1, 0)


def _direction(play: str, text: str) -> str:
    if play == "rotation":
        out = re.search(r"\bout of\b|\baway from\b", text)
        into = re.search(r"\bin ?to\b|\btowards\b", text)
        return "out_in" if out and into else "out" if out else "in"
    for rx, d in CUES.get(play, []):
        if re.search(rf"\b(?:{rx})", text):
            return d
    return DEFAULT[play]


def _roles(
    play: str, t: str, inside: list[tuple[int, int, str]], asset: dict[str, tuple[str, str]]
) -> list[AssetRef]:
    out: list[AssetRef] = []
    seen: set[str] = set()
    for i, (s, _, name) in enumerate(inside):
        aid, kind = asset[name]
        if aid in seen:
            continue
        seen.add(aid)
        before = t[max(s - 12, 0) : s]
        role = "subject"
        if play == "rotation":
            if re.search(r"out of $|from $|away from $", before):
                role = "from"
            elif re.search(r"in ?to $|towards $", before):
                role = "to"
        elif play == "relative" and i > 0:
            role = "versus"
        out.append(AssetRef(spoken=name, ticker=None, kind=kind, role=role))  # type: ignore[arg-type]
    return out
