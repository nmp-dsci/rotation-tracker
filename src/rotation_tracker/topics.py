"""Chapter topic tags, ``topic/v1``, and cutting a transcript at its chapters.

The rotation work reads ``macro-flows`` and ``untagged`` sections only. Most of a
2023+ wrap is macro and flows, so that is the default; the rules below pick out
chart reading, sponsors and the intro/outro by the chapter title alone.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

TOPIC_RULE_VERSION = "topic/v1"

_PROMO = re.compile(
    r"\b(tiger|broker(s|age)?|sponsor\w*|partner|pause screen|giveaway|discount|course|"
    r"newsletter|membership|live event|channel update|free training|promo\w*)\b"
)
_INTRO_OUTRO = re.compile(r"^(intro\w*|outro|closing( remarks| thoughts)?|welcome)\b|\boutro\b")
_TECHNICALS = re.compile(
    r"\b(technical\w*|charts?|levels?|support|resistance|trend ?lines?|fibonacci|"
    r"price action|candles?\w*|elliott|chart patterns?)\b"
)
# A chapter titled with nothing but an index or ticker ("SP 500", "QQQ") is a chart walk.
_TICKER_ONLY = re.compile(
    r"^(s ?& ?p ?500|sp ?500|spx|spy|qqq|nasdaq|ndx|dow|djia|iwm|russell( 2000)?|vix|dxy|"
    r"btc|eth|bitcoin|tsla|nvda|aapl)( (and|&|,) ?(s ?& ?p ?500|sp ?500|spx|spy|qqq|nasdaq|"
    r"dow|iwm|vix|dxy|btc|eth|bitcoin))*$"
)


def tag(title: str | None) -> str:
    if not title or not title.strip():
        return "untagged"
    t = " ".join(title.lower().split())
    if _PROMO.search(t):
        return "promo"
    if _INTRO_OUTRO.search(t):
        return "intro-outro"
    if _TECHNICALS.search(t) or _TICKER_ONLY.match(t):
        return "technicals"
    return "macro-flows"


@dataclass(frozen=True)
class Section:
    idx: int
    start_s: float
    end_s: float | None
    title: str | None
    topic: str
    text: str


def cut(segments: Sequence[dict[str, Any]], chapters: Sequence[dict[str, Any]]) -> list[Section]:
    """Assign each transcript segment to the chapter its start falls in.

    ``segments`` carry ``start_seconds`` and ``text`` (transcript·lab's shape);
    ``chapters`` carry ``start_time``, ``end_time`` and ``title`` (yt-dlp's).
    Without chapters the whole transcript is one ``untagged`` section.
    """
    if not chapters:
        text = " ".join(str(s.get("text", "")).strip() for s in segments).strip()
        end = max((float(s.get("end_seconds") or 0) for s in segments), default=None)
        return [Section(0, 0.0, end, None, "untagged", text)]
    chs = sorted(chapters, key=lambda c: float(c["start_time"]))
    starts = [float(c["start_time"]) for c in chs]
    buckets: list[list[str]] = [[] for _ in chs]
    for s in segments:
        st = float(s.get("start_seconds") or 0)
        i = 0
        for j, c0 in enumerate(starts):
            if st >= c0:
                i = j
            else:
                break
        buckets[i].append(str(s.get("text", "")).strip())
    out = []
    for i, c in enumerate(chs):
        end = c.get("end_time")
        out.append(
            Section(
                idx=i,
                start_s=float(c["start_time"]),
                end_s=float(end) if end is not None else None,
                title=c.get("title"),
                topic=tag(c.get("title")),
                text=" ".join(b for b in buckets[i] if b).strip(),
            )
        )
    return out
