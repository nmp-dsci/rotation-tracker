"""The pipeline steps behind the ``rt`` commands: catalog → refine → pick → ingest → sync."""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from rotation_tracker import pick as pick_rule
from rotation_tracker import supadata, topics, transcript_lab, youtube
from rotation_tracker.config import settings

Log = Callable[[str], None]


def _ts(v: Any) -> datetime | None:
    return datetime.fromtimestamp(int(v), tz=UTC) if v else None


# ── ① catalog ──────────────────────────────────────────────────────────────────
def catalog(con: psycopg.Connection, refresh: bool = False) -> dict[str, int]:
    counts = {}
    for tab in youtube.TABS:
        entries = youtube.listing(tab, refresh=refresh)
        with con.cursor() as cur:
            for e in entries:
                cur.execute(
                    """
                    INSERT INTO rt.videos (video_id, tab, listing_pos, title, duration_s,
                                           view_count, approx_published_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (video_id) DO UPDATE SET
                      tab = EXCLUDED.tab, listing_pos = EXCLUDED.listing_pos,
                      title = EXCLUDED.title, duration_s = EXCLUDED.duration_s,
                      view_count = EXCLUDED.view_count,
                      approx_published_at = EXCLUDED.approx_published_at,
                      listed_at = now()
                    """,
                    (
                        e["id"],
                        tab,
                        e["pos"],
                        e["title"],
                        e["duration"],
                        e["view_count"],
                        _ts(e["timestamp"]),
                    ),
                )
        counts[tab] = len(entries)
    con.commit()
    return counts


# ── ② refine ───────────────────────────────────────────────────────────────────
def _store_meta(con: psycopg.Connection, m: dict[str, Any]) -> None:
    con.execute(
        """
        UPDATE rt.videos SET published_at = %s, live_status = COALESCE(%s, live_status),
               has_auto_captions = COALESCE(%s, has_auto_captions), refined_at = now()
        WHERE video_id = %s
        """,
        (_ts(m.get("timestamp")), m.get("live_status"), m.get("has_auto_captions"), m["id"]),
    )


def refine(
    con: psycopg.Connection, workers: int = 2, batch: int = 20, log: Log = print
) -> dict[str, Any]:
    """Exact publish times for the Videos tab, newest first, until a whole batch is
    older than the first week in scope. Cached lookups (and the s00 seed) are free."""
    start, _ = pick_rule.window(settings().first_week_friday)
    rows = con.execute(
        "SELECT video_id FROM rt.videos WHERE tab = 'videos' ORDER BY listing_pos"
    ).fetchall()
    ids = [r[0] for r in rows]
    looked_up = from_cache = 0
    stopped = None
    for i in range(0, len(ids), batch):
        chunk = ids[i : i + batch]
        need = [v for v in chunk if not youtube.cached_meta(v)]
        from_cache += len(chunk) - len(need)
        try:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                list(pool.map(youtube.video_meta, need))
        except youtube.BotCheck as e:
            stopped = f"bot-check after {looked_up} lookups: {str(e)[:120]}"
            break
        looked_up += len(need)
        metas = [m for v in chunk if (m := youtube.cached_meta(v))]
        for m in metas:
            _store_meta(con, m)
        con.commit()
        times = [t for m in metas if (t := _ts(m.get("timestamp"))) is not None]
        span = f"  positions {i + 1}-{i + len(chunk)}"
        log(f"{span}: oldest {min(times):%Y-%m-%d} ({len(need)} looked up)" if times else span)
        if times and len(times) == len(metas) and max(times) < start:
            break
    return {"looked_up": looked_up, "from_cache": from_cache, "stopped": stopped}


# ── ③ pick ─────────────────────────────────────────────────────────────────────
def pick(con: psycopg.Connection, now: datetime | None = None) -> list[pick_rule.Pick]:
    rows = con.execute(
        """SELECT video_id, published_at, tab, live_status, duration_s
           FROM rt.videos WHERE published_at IS NOT NULL"""
    ).fetchall()
    uploads = [pick_rule.Upload(r[0], r[1], r[2], r[3], r[4]) for r in rows]
    picks = pick_rule.pick_weeks(uploads, settings().first_week_friday, now or datetime.now(UTC))
    with con.cursor() as cur:
        cur.execute(
            "DELETE FROM rt.weekly_picks WHERE rule_version = %s", (pick_rule.RULE_VERSION,)
        )
        for p in picks:
            cur.execute(
                "INSERT INTO rt.weekly_picks (week_friday, video_id, reason, rule_version) "
                "VALUES (%s, %s, %s, %s)",
                (p.week_friday, p.video_id, p.reason, pick_rule.RULE_VERSION),
            )
    con.commit()
    return picks


# ── ④ ingest ───────────────────────────────────────────────────────────────────
def pending_picks(con: psycopg.Connection, corpus: transcript_lab.Corpus) -> list[str]:
    rows = con.execute("SELECT video_id FROM rt.weekly_picks ORDER BY week_friday DESC").fetchall()
    return [r[0] for r in rows if not corpus.has(r[0])]


def ingest(
    con: psycopg.Connection, limit: int | None, max_credits: int, workers: int = 2, log: Log = print
) -> dict[str, Any]:
    """Index pending picks newest first through transcript·lab, at most ``max_credits``
    of them; the real spend is read from Supadata before and after."""
    corpus = transcript_lab.Corpus()
    todo = pending_picks(con, corpus)
    cap = min(max_credits, limit) if limit is not None else max_credits
    todo = todo[:cap]
    before = supadata.credits_left()
    batch_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:6]
    log(f"  batch {batch_id}: {len(todo)} to index, {before} credits left")

    def one(vid: str) -> tuple[str, datetime, int, str]:
        started = datetime.now(UTC)
        try:
            meta = youtube.video_meta(vid, need_chapters=True)
        except Exception as e:  # a bot-check or a removed video: log it, keep the batch going
            return vid, started, -2, f"metadata lookup failed: {str(e)[:200]}"
        rc, tail = transcript_lab.index(meta)
        return vid, started, rc, tail

    indexed, failed = 0, []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for vid, started, rc, tail in pool.map(one, todo):
            # The raw transcript is what this repo needs. index-rag can store it and then
            # fail on a later step (summary, dashboard); that still counts, with rc kept.
            ok = corpus.has(vid)
            con.execute(
                """INSERT INTO rt.ingest_log (batch_id, video_id, started_at, finished_at,
                                              returncode, status, detail)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (
                    batch_id,
                    vid,
                    started,
                    datetime.now(UTC),
                    rc,
                    "indexed" if ok else "failed",
                    tail,
                ),
            )
            con.commit()
            indexed += ok
            if not ok:
                failed.append(vid)
            log(f"  {vid} {'ok' if ok else 'FAILED rc=' + str(rc)}  {'' if ok else tail[:160]}")
    after = supadata.credits_left()
    return {
        "batch_id": batch_id,
        "attempted": len(todo),
        "indexed": indexed,
        "failed": failed,
        "credits_before": before,
        "credits_after": after,
        "credits_spent": before - after,
    }


# ── ⑤ sync ─────────────────────────────────────────────────────────────────────
def sync(con: psycopg.Connection, log: Log = print) -> dict[str, int]:
    corpus = transcript_lab.Corpus()
    picks = [r[0] for r in con.execute("SELECT video_id FROM rt.weekly_picks").fetchall()]
    synced = sections = untagged = 0
    for vid in picks:
        body = corpus.raw(vid)
        if body is None:
            continue
        segments = body.get("segments") or []
        text = " ".join(str(s.get("text", "")).strip() for s in segments).strip()
        digest = hashlib.sha256(json.dumps(segments, sort_keys=True).encode()).hexdigest()
        meta = youtube.video_meta(vid, need_chapters=True)
        chapters = meta.get("chapters") or []
        with con.cursor() as cur:
            cur.execute(
                """
                INSERT INTO rt.transcripts (video_id, source_id, segments, n_segments, text, sha256)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (video_id) DO UPDATE SET segments = EXCLUDED.segments,
                  n_segments = EXCLUDED.n_segments, text = EXCLUDED.text,
                  sha256 = EXCLUDED.sha256, synced_at = now()
                """,
                (vid, f"raw_transcript:{vid}", Jsonb(segments), len(segments), text, digest),
            )
            cur.execute("DELETE FROM rt.chapters WHERE video_id = %s", (vid,))
            for i, c in enumerate(chapters):
                cur.execute(
                    "INSERT INTO rt.chapters (video_id, idx, start_s, end_s, title) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (vid, i, c["start_time"], c.get("end_time"), c.get("title") or ""),
                )
            cur.execute("DELETE FROM rt.transcript_chapters WHERE video_id = %s", (vid,))
            for sec in topics.cut(segments, chapters):
                cur.execute(
                    """INSERT INTO rt.transcript_chapters (video_id, idx, start_s, end_s, title,
                                                           topic, topic_rule_version, text)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                    (
                        vid,
                        sec.idx,
                        sec.start_s,
                        sec.end_s,
                        sec.title,
                        sec.topic,
                        topics.TOPIC_RULE_VERSION,
                        sec.text,
                    ),
                )
                sections += 1
        untagged += not chapters
        synced += 1
        con.commit()
    log(f"  synced {synced} transcripts, {sections} sections ({untagged} videos without chapters)")
    return {"synced": synced, "sections": sections, "without_chapters": untagged}


# ── status ─────────────────────────────────────────────────────────────────────
STATUS_SQL = """
SELECT
  (SELECT count(*) FROM rt.videos WHERE tab = 'videos'),
  (SELECT count(*) FROM rt.videos WHERE tab = 'streams'),
  (SELECT count(*) FROM rt.videos WHERE tab = 'shorts'),
  (SELECT count(*) FROM rt.videos WHERE tab = 'videos' AND published_at IS NOT NULL),
  (SELECT count(*) FROM rt.weekly_picks),
  (SELECT count(*) FROM rt.weekly_picks WHERE reason = 'weekend'),
  (SELECT min(week_friday) FROM rt.weekly_picks),
  (SELECT max(week_friday) FROM rt.weekly_picks),
  (SELECT count(DISTINCT video_id) FROM rt.ingest_log WHERE status = 'indexed'),
  (SELECT count(*) FROM rt.transcripts),
  (SELECT count(*) FROM rt.transcript_chapters),
  (SELECT count(*) FROM rt.transcript_chapters WHERE topic = 'macro-flows')
"""


def status(con: psycopg.Connection) -> dict[str, Any]:
    row = con.execute(STATUS_SQL).fetchone()
    assert row is not None
    keys = [
        "videos",
        "streams",
        "shorts",
        "videos_dated",
        "picks",
        "picks_weekend",
        "first_week",
        "last_week",
        "ingested",
        "transcripts",
        "sections",
        "macro_flows",
    ]
    return dict(zip(keys, row, strict=True))
