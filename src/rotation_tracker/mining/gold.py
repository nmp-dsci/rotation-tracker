"""The gold set: twelve fixed weeks, a careful pass, an independent second read of every
rotation mention, and the owner's spot-check queue.

- ``pick``: three weeks per year, 2023 to 2026, drawn with a fixed seed and stored in
  ``rt.gold_weeks`` (never re-drawn).
- the careful pass is ``rt mine run --gold --purpose gold --version gold/v1 --effort max``.
- ``second_read``: each rotation mention in the gold pass is read again by a separate call that
  sees the quote, its surrounding text and the proposed fields, and answers whether each is
  right. Its verdicts are ``rt.labels`` rows with source ``second-read``.
- ``sample``: fifty gold mentions for the owner, rotation first, then every other play.
"""

from __future__ import annotations

import json
import random
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Literal

import psycopg
from psycopg.types.json import Jsonb
from pydantic import BaseModel

from rotation_tracker.mining import corpus, extract
from rotation_tracker.mining.schema import GOLD_VERSION, Direction, Kind, Play, Role

Log = Callable[[str], None]
SEED = 20261028
YEARS = (2023, 2024, 2025, 2026)
PER_YEAR = 3
SPOT = 50
RULE = f"gold/v1: {PER_YEAR} per year {YEARS[0]}-{YEARS[-1]}, random.Random({SEED})"


def pick(con: psycopg.Connection) -> list[str]:
    have = [v for (v,) in con.execute("SELECT video_id FROM rt.gold_weeks")]
    if have:
        return have
    rng = random.Random(SEED)
    chosen: list[str] = []
    for y in YEARS:
        pool = [
            v
            for (v,) in con.execute(
                """SELECT p.video_id FROM rt.weekly_picks p JOIN rt.transcripts USING (video_id)
                   WHERE extract(year FROM p.week_friday) = %s ORDER BY p.week_friday""",
                (y,),
            )
        ]
        chosen += rng.sample(pool, PER_YEAR)
    for v in chosen:
        con.execute("INSERT INTO rt.gold_weeks (video_id, rule) VALUES (%s, %s)", (v, RULE))
    con.commit()
    return chosen


def gold_run(con: psycopg.Connection) -> str | None:
    row = con.execute(
        """SELECT run_id FROM rt.mine_runs WHERE extractor_version = %s AND status = 'done'
           ORDER BY started_at DESC LIMIT 1""",
        (GOLD_VERSION,),
    ).fetchone()
    return row[0] if row else None


# ── second read ──────────────────────────────────────────────────────────────────────────
SECOND_READ = """You check one extracted claim from an auto-captioned market-wrap transcript.
You see the claim's quote inside its surrounding text and the fields another reader proposed.
Decide independently, from the text alone:

- is_mention: is this a claim about an identifiable asset's price or money flow (not a topic
  cue like "let's talk rotation", not about the channel)?
- play: is "rotation" right? Rotation means money moving between assets, sectors or themes,
  or leadership changing. If another play fits better, give it (relative, flow, valuation,
  technical, regime, call, other).
- direction: for rotation, "out" (money leaving the assets), "in" (arriving), "out_in" (both
  sides named). Give the right one.
- assets: for each proposed asset, is it what the claim is about, with the right role (from =
  money leaving, to = money arriving, subject otherwise)? List any asset the claim names that
  is missing.

Return your verdict in the schema. Be strict: a field is right only if the text supports it."""


class AssetCheck(BaseModel):
    spoken: str
    right: bool
    role: Role
    kind: Kind


class Verdict(BaseModel):
    is_mention: bool
    play: Play
    direction: Direction
    assets: list[AssetCheck]
    missing_assets: list[str]
    note: str


def _context(week: corpus.Week, section: int, start: int, end: int, pad: int = 700) -> str:
    text = week.sections[section].text
    a, b = max(start - pad, 0), min(end + pad, len(text))
    return f"…{text[a:start]}<<{text[start:end]}>>{text[end:b]}…"


def second_read(
    con: psycopg.Connection, run_id: str, effort: str = "high", log: Log = print
) -> dict[str, Any]:
    rows = con.execute(
        """SELECT m.id, m.video_id, m.section_idx, m.span_start, m.span_end, m.play, m.direction,
                  coalesce(json_agg(json_build_object('spoken', a.spoken, 'role', a.role,
                    'kind', a.kind_guess) ORDER BY a.ord) FILTER (WHERE a.ord IS NOT NULL), '[]')
           FROM rt.mentions m LEFT JOIN rt.mention_assets a ON a.mention_id = m.id
           WHERE m.run_id = %s AND m.play = 'rotation'
             AND NOT EXISTS (SELECT 1 FROM rt.labels l
                             WHERE l.mention_id = m.id AND l.source = 'second-read')
           GROUP BY m.id ORDER BY m.id""",
        (run_id,),
    ).fetchall()
    weeks: dict[str, corpus.Week] = {}
    jobs = []
    for mid, vid, sec, s, e, play, direction, assets in rows:
        if vid not in weeks:
            weeks[vid] = corpus.load(con, vid)
        proposed = {"play": play, "direction": direction, "assets": assets}
        body = (
            f"Text (the claim is between << and >>):\n{_context(weeks[vid], sec, s, e)}\n\n"
            f"Proposed fields:\n{json.dumps(proposed)}"
        )
        jobs.append((mid, proposed, body))
    cl = extract.client()

    def ask(body: str) -> tuple[Verdict | None, extract.Usage]:
        v, u = extract.ask(cl, SECOND_READ, body, Verdict, effort=effort)
        return (v if isinstance(v, Verdict) else None), u

    usd = 0.0
    agree = 0
    done = 0
    with ThreadPoolExecutor(4) as pool:
        for (mid, proposed, _), (v, u) in zip(
            jobs, pool.map(lambda j: ask(j[2]), jobs), strict=True
        ):
            usd += u.usd()
            if v is None:
                log(f"  mention {mid}: no verdict")
                continue
            same_assets = all(a.right for a in v.assets) and not v.missing_assets
            ok = v.is_mention and v.play == "rotation" and v.direction == proposed["direction"]
            verdict: Literal["correct", "wrong", "fix"] = (
                "correct" if ok and same_assets else "wrong" if not v.is_mention else "fix"
            )
            fixes = {} if verdict == "correct" else v.model_dump(exclude={"note"})
            con.execute(
                """INSERT INTO rt.labels (mention_id, source, verdict, fixes, note, labeled_by)
                   VALUES (%s, 'second-read', %s, %s, %s, %s)""",
                (mid, verdict, Jsonb(fixes), v.note[:500], f"{extract.MODEL}@{effort}"),
            )
            agree += verdict == "correct"
            done += 1
    con.commit()
    out = {"read": done, "agree": agree, "agreement": round(agree / done, 4) if done else None}
    log(f"  second read: {out} ${usd:.2f}")
    return out | {"usd": round(usd, 4)}


def sample(con: psycopg.Connection, run_id: str) -> int:
    """Fifty gold mentions for the owner: up to half rotation, the rest spread over plays.

    Fixed once drawn. A newer gold run redraws it, unless the owner has already labelled any of
    the old sample: human work is never thrown away.
    """
    have = con.execute(
        """SELECT count(*), count(*) FILTER (WHERE m.run_id = %s),
                  count(*) FILTER (WHERE EXISTS (SELECT 1 FROM rt.labels l
                    WHERE l.mention_id = s.mention_id AND l.source = 'owner'))
           FROM rt.spot_checks s JOIN rt.mentions m ON m.id = s.mention_id""",
        (run_id,),
    ).fetchone()
    total, current, labelled = have if have else (0, 0, 0)
    if total and (current == total or labelled):
        return int(total)
    con.execute("DELETE FROM rt.spot_checks")
    rows = con.execute(
        "SELECT id, play FROM rt.mentions WHERE run_id = %s ORDER BY id", (run_id,)
    ).fetchall()
    rng = random.Random(SEED)
    by_play: dict[str, list[int]] = {}
    for mid, play in rows:
        by_play.setdefault(play, []).append(mid)
    rot = by_play.pop("rotation", [])
    chosen = rng.sample(rot, min(len(rot), SPOT // 2))
    rest = [m for ms in by_play.values() for m in ms]
    chosen += rng.sample(rest, min(len(rest), SPOT - len(chosen)))
    rng.shuffle(chosen)
    for i, mid in enumerate(chosen):
        con.execute("INSERT INTO rt.spot_checks (mention_id, ord) VALUES (%s, %s)", (mid, i))
    con.commit()
    return len(chosen)
