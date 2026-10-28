"""The weekly pick rule, ``pick/v1``.

For each trading week, keyed by its Friday F: the last eligible upload published
at or after that week's Monday 09:30 New York time and before the next Monday
09:30. It is tagged ``weekend`` when it came after F's 16:00 close, otherwise
``fallback``. A week with no eligible upload gets no pick. Only weeks whose
window has closed are picked.

The creator publishes in the New York evening (the next morning in Australia),
so each upload recaps the session that just closed, and the one between
Friday's close and Monday's open is the weekly wrap (s00 plan, 84 of 97 sampled
weeks).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

RULE_VERSION = "pick/v1"
NY = ZoneInfo("America/New_York")
OPEN = time(9, 30)
CLOSE = time(16, 0)
# Uploads that are never a weekly wrap: live streams and anything Shorts-length.
EXCLUDED_LIVE = {"is_live", "is_upcoming", "was_live", "post_live"}
MIN_DURATION_S = 180


@dataclass(frozen=True)
class Upload:
    video_id: str
    published_at: datetime  # timezone-aware
    tab: str = "videos"
    live_status: str | None = None
    duration_s: int | None = None


@dataclass(frozen=True)
class Span:
    """An undated upload, bounded by its dated neighbours in the newest-first listing."""

    video_id: str
    after: datetime | None
    before: datetime | None


@dataclass(frozen=True)
class Pick:
    week_friday: date
    video_id: str
    reason: str
    published_at: datetime


def eligible(u: Upload) -> bool:
    if u.tab != "videos" or u.live_status in EXCLUDED_LIVE:
        return False
    return u.duration_s is None or u.duration_s >= MIN_DURATION_S


def window(friday: date) -> tuple[datetime, datetime]:
    """[Monday 09:30, next Monday 09:30) in New York time, for the week ending ``friday``."""
    start = datetime.combine(friday - timedelta(days=4), OPEN, tzinfo=NY)
    end = datetime.combine(friday + timedelta(days=3), OPEN, tzinfo=NY)
    return start, end


def pick_weeks(uploads: Iterable[Upload], first_friday: date, now: datetime) -> list[Pick]:
    if first_friday.weekday() != 4:
        raise ValueError(f"{first_friday} is not a Friday")
    pool = sorted((u for u in uploads if eligible(u)), key=lambda u: u.published_at)
    picks: list[Pick] = []
    friday = first_friday
    while True:
        start, end = window(friday)
        if end > now:
            break
        inside = [u for u in pool if start <= u.published_at < end]
        if inside:
            last = inside[-1]
            close = datetime.combine(friday, CLOSE, tzinfo=NY)
            reason = "weekend" if last.published_at >= close else "fallback"
            picks.append(Pick(friday, last.video_id, reason, last.published_at))
        friday += timedelta(days=7)
    return picks


def undated_spans(listing: Iterable[tuple[str, datetime | None]]) -> list[Span]:
    """Bound each undated upload using the dated rows around it. ``listing`` is the Videos
    tab, newest first, as (video_id, published_at or None)."""
    rows = list(listing)
    spans: list[Span] = []
    for i, (vid, at) in enumerate(rows):
        if at is not None:
            continue
        before = next((t for _, t in reversed(rows[:i]) if t is not None), None)
        after = next((t for _, t in rows[i + 1 :] if t is not None), None)
        spans.append(Span(vid, after, before))
    return spans


def undated_weeks(
    spans: Iterable[Span], first_friday: date, now: datetime
) -> dict[date, list[str]]:
    """Weeks whose window an undated upload may fall in, with the video ids, so a pick
    there cannot be trusted."""
    pending = list(spans)
    out: dict[date, list[str]] = {}
    friday = first_friday
    while True:
        start, end = window(friday)
        if end > now:
            break
        ids = [
            s.video_id
            for s in pending
            if (s.after is None or s.after < end) and (s.before is None or s.before >= start)
        ]
        if ids:
            out[friday] = ids
        friday += timedelta(days=7)
    return out
