"""One week as the miner reads it: the pick, its sections, and the caption timing."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

import psycopg

from rotation_tracker.mining.locate import Section, attach_marks

READ_TOPICS = (
    "macro-flows",
    "untagged",
)  # decision (s02): technicals, intro and promo are not read


@dataclass
class Week:
    video_id: str
    week_friday: date
    title: str
    published_at: datetime | None
    sections: dict[int, Section]  # every section, so caption buckets match topics.cut

    @property
    def read(self) -> dict[int, Section]:
        return {k: s for k, s in self.sections.items() if s.topic in READ_TOPICS and s.text}

    @property
    def n_chars(self) -> int:
        return sum(len(s.text) for s in self.read.values())


def load(con: psycopg.Connection, video_id: str) -> Week:
    row = con.execute(
        """SELECT p.week_friday, v.title, v.published_at, t.segments
           FROM rt.weekly_picks p JOIN rt.videos v USING (video_id)
           JOIN rt.transcripts t USING (video_id) WHERE p.video_id = %s""",
        (video_id,),
    ).fetchone()
    if row is None:
        raise KeyError(f"{video_id}: no weekly pick with a transcript")
    friday, title, published, segments = row
    secs = {
        idx: Section(idx, float(st or 0.0), en, ti, topic, text)
        for idx, st, en, ti, topic, text in con.execute(
            """SELECT idx, start_s, end_s, title, topic, text FROM rt.transcript_chapters
               WHERE video_id = %s ORDER BY idx""",
            (video_id,),
        )
    }
    attach_marks(list(secs.values()), segments or [])
    return Week(video_id, friday, title, published, secs)


def clock(s: float) -> str:
    s = int(s)
    return (
        f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"
    )


def render(w: Week) -> str:
    """The user turn: a header, then each section the miner reads behind a § marker."""
    pub = f", published {w.published_at:%Y-%m-%d}" if w.published_at else ""
    parts = [
        f'Week ending Friday {w.week_friday:%Y-%m-%d}. Video: "{w.title}"{pub}.',
        "The sections to read follow, each opened by a marker [§n · start · chapter title].",
    ]
    for k, s in sorted(w.read.items()):
        parts.append(f"\n[§{k} · {clock(s.start_s)} · {s.title or 'untitled'}]\n{s.text}")
    return "\n".join(parts)


def weeks(
    con: psycopg.Connection, since: date | None = None, ids: list[str] | None = None
) -> list[tuple[str, date]]:
    """Weekly picks that have a transcript, newest first."""
    sql = """SELECT p.video_id, p.week_friday FROM rt.weekly_picks p
             JOIN rt.transcripts t USING (video_id) WHERE true"""
    args: list[Any] = []
    if since:
        sql += " AND p.week_friday >= %s"
        args.append(since)
    if ids:
        sql += " AND p.video_id = ANY(%s)"
        args.append(ids)
    return [(v, f) for v, f in con.execute(sql + " ORDER BY p.week_friday DESC", args)]
