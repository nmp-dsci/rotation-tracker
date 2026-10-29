"""play/v1: what the extractor returns, and the rules code applies to it.

The model fills ``WeekMentions`` through structured output; code then checks each mention's
direction against its play, fixes asset roles a rotation implies, and derives the stance each
asset gets (rotation in ⇒ bullish, out ⇒ bearish, per the owner's note of 28 Oct 2026).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel, Field

EXTRACTOR_VERSION = "play/v1"
GOLD_VERSION = "gold/v1"
BASELINE_VERSION = "play/v0"

Play = Literal["rotation", "flow", "valuation", "technical", "regime", "relative", "call", "other"]
Direction = Literal[
    "in", "out", "out_in", "buying", "selling", "under", "over", "fair", "bullish", "bearish",
    "neutral", "risk_on", "risk_off", "bull", "bear", "a_over_b", "long", "short", "avoid", "watch",
]  # fmt: skip
Kind = Literal[
    "index", "sector", "theme", "stock", "fund", "crypto", "rates", "credit", "commodity", "fx",
    "macro",
]  # fmt: skip
Role = Literal["subject", "from", "to", "versus"]
Stance = Literal["bullish", "bearish", "neutral"]

PLAYS: tuple[str, ...] = Play.__args__  # type: ignore[attr-defined]
DIRECTIONS: dict[str, tuple[str, ...]] = {
    "rotation": ("in", "out", "out_in"),
    "flow": ("buying", "selling"),
    "valuation": ("under", "over", "fair"),
    "technical": ("bullish", "bearish", "neutral"),
    "regime": ("risk_on", "risk_off", "bull", "bear", "neutral"),
    "relative": ("a_over_b",),
    "call": ("long", "short", "avoid", "watch"),
    "other": ("bullish", "bearish", "neutral"),
}
STANCE: dict[str, Stance] = {
    "in": "bullish", "out": "bearish", "out_in": "bullish", "buying": "bullish",
    "selling": "bearish", "under": "bullish", "over": "bearish", "fair": "neutral",
    "bullish": "bullish", "bearish": "bearish", "neutral": "neutral", "risk_on": "bullish",
    "risk_off": "bearish", "bull": "bullish", "bear": "bearish", "a_over_b": "bullish",
    "long": "bullish", "short": "bearish", "avoid": "bearish", "watch": "neutral",
}  # fmt: skip
FLIP: dict[Stance, Stance] = {"bullish": "bearish", "bearish": "bullish", "neutral": "neutral"}


class AssetRef(BaseModel):
    spoken: str = Field(description="The asset exactly as said in the quote, e.g. 'semis'.")
    ticker: str | None = Field(
        description="Best ticker or symbol guess (NVDA, SMH, BTC, GLD, ^TNX), null if none."
    )
    kind: Kind
    role: Role


class Mention(BaseModel):
    section: int = Field(description="The § number of the section the quote is in.")
    quote: str = Field(description="Verbatim, contiguous copy of the transcript words.")
    play: Play
    direction: Direction
    assets: list[AssetRef]
    speaker: Literal["him", "reported"]
    reported_source: str | None = Field(
        description="Whose view he is relaying when speaker is 'reported', else null."
    )
    modality: Literal["observed", "expected", "recommended"]
    horizon: Literal["days", "weeks", "months", "years", "unspecified"]
    confidence: float = Field(description="0 to 1; hedges lower it.")


class WeekMentions(BaseModel):
    mentions: list[Mention]


def check(m: Mention) -> str | None:
    """Why a mention cannot be kept, or None. Mutates roles a rotation or relative implies."""
    if m.direction not in DIRECTIONS[m.play]:
        return "bad-direction"
    if not m.assets:
        return "no-asset"
    if m.play == "rotation":
        if m.direction == "out":
            for a in m.assets:
                if a.role == "subject":
                    a.role = "from"
        elif m.direction == "in":
            for a in m.assets:
                if a.role == "subject":
                    a.role = "to"
    return None


def asset_stance(play: str, direction: str, role: str) -> Stance:
    """The stance a mention implies for one of its assets."""
    if role == "from":
        return "bearish"
    if role == "to":
        return "bullish"
    base = STANCE[direction]
    if play == "relative":
        return "bearish" if role == "versus" else "bullish"
    return FLIP[base] if role == "versus" else base


def mention_stance(play: str, direction: str, roles: Sequence[str]) -> Stance:
    """Toward the mention's first asset."""
    return asset_stance(play, direction, roles[0]) if roles else STANCE[direction]
