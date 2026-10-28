"""The provenance gate: every quote must be found in its section, or the mention is dropped.

A found quote gets a character span in the section text and, through the caption segment that
holds its first character, the second in the video it was said (``t_seconds``). Matching is on
normalised text (lower case, words only), exact first, then fuzzy over word windows with a
similarity of at least ``FUZZY`` (auto-captions and the model's copy differ in small ways).
"""

from __future__ import annotations

import bisect
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any

FUZZY = 0.9
MIN_FUZZY_WORDS = 5


@dataclass
class Section:
    idx: int
    start_s: float
    end_s: float | None
    title: str | None
    topic: str
    text: str
    # (char offset in ``text``, segment start in seconds), ascending
    marks: list[tuple[int, float]] = field(default_factory=list)

    def t_at(self, pos: int) -> float:
        if not self.marks:
            return self.start_s
        i = bisect.bisect_right([m[0] for m in self.marks], pos) - 1
        return self.marks[max(i, 0)][1]


def attach_marks(sections: Sequence[Section], segments: Sequence[dict[str, Any]]) -> None:
    """Give each section the offsets of its caption segments, bucketed as ``topics.cut`` does
    (a segment belongs to the last section starting at or before it)."""
    ordered = sorted(sections, key=lambda s: s.start_s)
    starts = [s.start_s for s in ordered]
    pos = [0] * len(ordered)
    for seg in segments:
        text = str(seg.get("text", "")).strip()
        if not text:
            continue
        st = float(seg.get("start_seconds") or 0.0)
        i = max(bisect.bisect_right(starts, st) - 1, 0)
        sec = ordered[i]
        at = sec.text.find(text, pos[i])
        if at < 0:
            continue
        sec.marks.append((at, st))
        pos[i] = at + len(text)


def _norm_map(text: str) -> tuple[str, list[int]]:
    """Normalised text and, for each of its characters, the index in ``text``."""
    out: list[str] = []
    idx: list[int] = []
    space = True
    for i, ch in enumerate(text.lower()):
        if ch.isalnum():
            out.append(ch)
            idx.append(i)
            space = False
        elif not space:
            out.append(" ")
            idx.append(i)
            space = True
    while out and out[-1] == " ":
        out.pop()
        idx.pop()
    return "".join(out), idx


def norm(text: str) -> str:
    return _norm_map(text)[0]


@dataclass(frozen=True)
class Found:
    start: int
    end: int
    how: str  # 'exact' | 'fuzzy'
    score: float


def find(quote: str, text: str) -> Found | None:
    q = norm(quote)
    if not q:
        return None
    t, idx = _norm_map(text)
    at = t.find(q)
    if at >= 0:
        return Found(idx[at], idx[at + len(q) - 1] + 1, "exact", 1.0)
    qw = q.split()
    if len(qw) < MIN_FUZZY_WORDS:
        return None
    words = [(m.start(), m.end(), m.group(0)) for m in re.finditer(r"\S+", t)]
    tw = [w for _, _, w in words]
    head = {w: k for k, w in reversed(list(enumerate(qw[:4])))}
    starts = {i - k for i, w in enumerate(tw) if (k := head.get(w)) is not None and i - k >= 0}
    best: tuple[float, int, int] = (0.0, 0, 0)
    for s in sorted(starts):
        for n in (len(qw) - 1, len(qw), len(qw) + 1):
            win = tw[s : s + n]
            if not win:
                continue
            r = SequenceMatcher(None, win, qw, autojunk=False).ratio()
            if r > best[0]:
                best = (r, s, s + len(win))
    score, s, e = best
    if score < FUZZY:
        return None
    return Found(idx[words[s][0]], idx[words[e - 1][1] - 1] + 1, "fuzzy", round(score, 3))


def locate(quote: str, section: int, sections: dict[int, Section]) -> tuple[Section, Found] | None:
    """Find ``quote`` in the section the model cited, else anywhere in the sections it read."""
    first = sections.get(section)
    order = ([first] if first else []) + [s for k, s in sections.items() if k != section]
    for sec in order:
        hit = find(quote, sec.text)
        if hit:
            return sec, hit
    return None
