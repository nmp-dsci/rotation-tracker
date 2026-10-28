"""What the viewer reads from the miner (s02): mentions, assets, runs, the eval and the gold set.

Reads only, as ``rotation_ro``, except ``Labeler``: the owner's spot-checks, written as
``rotation_owner`` and only when ``rt serve --label`` turned it on.
"""

from __future__ import annotations

from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from rotation_tracker import db
from rotation_tracker.mining import extract
from rotation_tracker.mining.run import CURRENT_PURPOSES, PRODUCTION
from rotation_tracker.mining.schema import DIRECTIONS, PLAYS

# The newest finished play/v1 run per week, made with today's prompt: what every page below
# reads. Weeks mined with an earlier prompt drop out until they are mined again.
CURRENT = """
cur AS (
  SELECT DISTINCT ON (w.video_id) w.video_id, w.run_id
  FROM rt.mine_weeks w JOIN rt.mine_runs r USING (run_id)
  WHERE w.status = 'done' AND r.extractor_version = %(version)s AND r.purpose = ANY(%(purposes)s)
    AND r.prompt_sha = %(prompt)s
  ORDER BY w.video_id, r.started_at DESC
)"""

ON_CUR = "JOIN cur ON cur.video_id = m.video_id AND cur.run_id = m.run_id"

ASSETS_JSON = """
coalesce((SELECT json_agg(json_build_object(
   'asset_id', a.asset_id, 'name', s.name, 'kind', s.kind, 'proxy', s.proxy, 'role', a.role,
   'stance', a.stance, 'spoken', a.spoken, 'resolution', a.resolution) ORDER BY a.ord)
 FROM rt.mention_assets a LEFT JOIN rt.assets s ON s.id = a.asset_id
 WHERE a.mention_id = m.id), '[]') AS assets"""

MENTION_COLS = f"""m.id, m.video_id, p.week_friday, v.title, m.play, m.direction, m.stance,
  m.speaker, m.reported_source, m.modality, m.horizon, m.confidence, m.quote, m.section_idx,
  c.title AS section_title, m.t_seconds, m.located, m.match_score, m.run_id, {ASSETS_JSON}"""

MENTION_FROM = """rt.mentions m
  JOIN rt.weekly_picks p USING (video_id)
  JOIN rt.videos v USING (video_id)
  LEFT JOIN rt.transcript_chapters c ON c.video_id = m.video_id AND c.idx = m.section_idx"""


def _args(**kw: Any) -> dict[str, Any]:
    return {
        "version": PRODUCTION,
        "purposes": list(CURRENT_PURPOSES),
        "prompt": extract.prompt_sha(),
    } | kw


def mentions(
    con: psycopg.Connection,
    play: str | None = None,
    direction: str | None = None,
    stance: str | None = None,
    asset: str | None = None,
    kind: str | None = None,
    year: int | None = None,
    speaker: str | None = None,
    modality: str | None = None,
    week: str | None = None,
    q: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    where = ["true"]
    a = _args(limit=limit, offset=offset)
    filters = (
        ("m.play", play),
        ("m.direction", direction),
        ("m.stance", stance),
        ("m.speaker", speaker),
        ("m.modality", modality),
        ("m.video_id", week),
    )
    for col, val in filters:
        if val:
            key = col.split(".")[1]
            where.append(f"{col} = %({key})s")
            a[key] = val
    if year:
        where.append("extract(year FROM p.week_friday) = %(year)s")
        a["year"] = year
    if asset:
        where.append(
            "EXISTS (SELECT 1 FROM rt.mention_assets x WHERE x.mention_id = m.id"
            " AND x.asset_id = %(asset)s)"
        )
        a["asset"] = asset
    if kind:
        where.append(
            "EXISTS (SELECT 1 FROM rt.mention_assets x JOIN rt.assets s ON s.id = x.asset_id"
            " WHERE x.mention_id = m.id AND s.kind = %(kind)s)"
        )
        a["kind"] = kind
    if q:
        where.append("m.quote ILIKE %(q)s")
        a["q"] = f"%{q}%"
    cond = " AND ".join(where)
    with con.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(
            f"""WITH {CURRENT}
                SELECT {MENTION_COLS} FROM {MENTION_FROM} {ON_CUR}
                WHERE {cond}
                ORDER BY p.week_friday DESC, m.section_idx, m.span_start
                LIMIT %(limit)s OFFSET %(offset)s""",
            a,
        ).fetchall()
        total = cur.execute(
            f"""WITH {CURRENT}
                SELECT count(*) AS n FROM {MENTION_FROM} {ON_CUR}
                WHERE {cond}""",
            a,
        ).fetchone()
        facets: dict[str, dict[str, int]] = {}
        for name, expr in (("play", "m.play"), ("year", "extract(year FROM p.week_friday)::int"),
                           ("speaker", "m.speaker"), ("modality", "m.modality"),
                           ("stance", "m.stance")):  # fmt: skip
            got = cur.execute(
                f"""WITH {CURRENT}
                    SELECT {expr} AS k, count(*) AS n FROM {MENTION_FROM}
                    {ON_CUR} GROUP BY 1 ORDER BY 1""",
                a,
            ).fetchall()
            facets[name] = {str(r["k"]): r["n"] for r in got}
        cov = cur.execute(
            f"""WITH {CURRENT}
                SELECT (SELECT count(*) FROM cur) AS mined,
                       (SELECT count(*) FROM rt.weekly_picks p
                        JOIN rt.transcripts USING (video_id)) AS weeks""",
            a,
        ).fetchone()
    return {
        "version": PRODUCTION,
        "total": (total or {}).get("n", 0),
        "rows": rows,
        "facets": facets,
        "coverage": cov,
        "plays": list(PLAYS),
        "directions": DIRECTIONS,
    }


def assets(
    con: psycopg.Connection, kind: str | None = None, q: str | None = None
) -> dict[str, Any]:
    a = _args(kind=kind, q=f"%{q}%" if q else None)
    with con.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(
            f"""WITH {CURRENT}
                SELECT s.id, s.name, s.kind, s.proxy, s.ticker, s.gics_sector, s.sp500, s.ndx,
                       count(*) AS mentions, count(DISTINCT m.video_id) AS weeks,
                       count(*) FILTER (WHERE x.stance = 'bullish') AS bullish,
                       count(*) FILTER (WHERE x.stance = 'bearish') AS bearish,
                       count(*) FILTER (WHERE m.play = 'rotation') AS rotation,
                       max(p.week_friday) AS last_week
                FROM rt.mention_assets x
                JOIN rt.mentions m ON m.id = x.mention_id
                {ON_CUR}
                JOIN rt.weekly_picks p ON p.video_id = m.video_id
                JOIN rt.assets s ON s.id = x.asset_id
                WHERE (%(kind)s::text IS NULL OR s.kind = %(kind)s)
                  AND (%(q)s::text IS NULL OR s.name ILIKE %(q)s OR s.id ILIKE %(q)s)
                GROUP BY s.id ORDER BY mentions DESC, s.name LIMIT 300""",
            a,
        ).fetchall()
        kinds = cur.execute(
            f"""WITH {CURRENT}
                SELECT s.kind, count(DISTINCT s.id) AS assets, count(*) AS mentions
                FROM rt.mention_assets x JOIN rt.mentions m ON m.id = x.mention_id
                {ON_CUR} JOIN rt.assets s ON s.id = x.asset_id
                GROUP BY 1 ORDER BY 3 DESC""",
            a,
        ).fetchall()
        universe = cur.execute(
            "SELECT kind, count(*) AS n FROM rt.assets GROUP BY 1 ORDER BY 2 DESC"
        ).fetchall()
    return {"rows": rows, "kinds": kinds, "universe": universe}


def asset(con: psycopg.Connection, asset_id: str) -> dict[str, Any] | None:
    a = _args(asset=asset_id)
    with con.cursor(row_factory=dict_row) as cur:
        row = cur.execute("SELECT * FROM rt.assets WHERE id = %(asset)s", a).fetchone()
        if row is None:
            return None
        aliases = [
            r["alias"]
            for r in cur.execute(
                "SELECT alias FROM rt.aliases WHERE asset_id = %(asset)s ORDER BY length(alias)",
                a,
            )
        ]
        strip = cur.execute(
            f"""WITH {CURRENT}
                SELECT p.week_friday, p.video_id, (cur.run_id IS NOT NULL) AS mined,
                       count(x.mention_id) FILTER (WHERE x.stance = 'bullish') AS up,
                       count(x.mention_id) FILTER (WHERE x.stance = 'bearish') AS down,
                       count(x.mention_id) FILTER (WHERE x.stance = 'neutral') AS flat,
                       count(x.mention_id) FILTER (WHERE m.play = 'rotation') AS rotation
                FROM rt.weekly_picks p
                JOIN rt.transcripts USING (video_id)
                LEFT JOIN cur ON cur.video_id = p.video_id
                LEFT JOIN rt.mentions m ON m.video_id = p.video_id AND m.run_id = cur.run_id
                LEFT JOIN rt.mention_assets x ON x.mention_id = m.id AND x.asset_id = %(asset)s
                GROUP BY p.week_friday, p.video_id, cur.run_id ORDER BY p.week_friday""",
            a,
        ).fetchall()
    found = mentions(con, asset=asset_id, limit=500)
    return {
        "asset": row,
        "aliases": aliases,
        "strip": strip,
        "mentions": found["rows"],
        "total": found["total"],
        "by_play": _count(found["rows"], "play"),
    }


def _count(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in rows:
        out[r[key]] = out.get(r[key], 0) + 1
    return out


def summary(con: psycopg.Connection) -> dict[str, Any]:
    a = _args()
    with con.cursor(row_factory=dict_row) as cur:
        runs = cur.execute(
            """SELECT run_id, engine, extractor_version, prompt_sha, model, effort, mode, purpose,
                      batch_id, status, started_at, finished_at, weeks, mentions, dropped,
                      input_tokens, output_tokens, cache_read_tokens, cache_write_tokens,
                      usd::float AS usd, mlflow_run_id, detail
               FROM rt.mine_runs ORDER BY started_at DESC LIMIT 40"""
        ).fetchall()
        # The eval of today's prompt; the latest eval of every run, in the order the runs were
        # made, for the history of prompt revisions.
        ev = cur.execute(
            """SELECT e.id, e.run_id, e.gold_run_id, e.at, e.metrics, e.gate_pass, e.mlflow_run_id
               FROM rt.evals e JOIN rt.mine_runs r USING (run_id)
               WHERE r.prompt_sha = %(prompt)s ORDER BY e.at DESC LIMIT 1""",
            a,
        ).fetchone()
        history = cur.execute(
            """SELECT * FROM (SELECT DISTINCT ON (e.run_id) e.at, r.started_at, e.run_id,
                      r.prompt_sha, e.gold_run_id, e.gate_pass,
                      (e.metrics->>'rotation_precision')::float AS rotation_precision,
                      (e.metrics->>'rotation_recall')::float AS rotation_recall,
                      (e.metrics->'agreement'->>'rotation_f1')::float AS rotation_run_to_run,
                      (e.metrics->>'f1')::float AS f1,
                      (e.metrics->'per_play'->'rotation'->>'pred')::int AS rotation_pred,
                      (e.metrics->'per_play'->'rotation'->>'gold')::int AS rotation_gold
               FROM rt.evals e JOIN rt.mine_runs r USING (run_id)
               ORDER BY e.run_id, e.at DESC) h ORDER BY started_at"""
        ).fetchall()
        cov = cur.execute(
            f"""WITH {CURRENT}
                SELECT (SELECT count(*) FROM cur) AS mined,
                       (SELECT count(*) FROM rt.weekly_picks JOIN rt.transcripts USING (video_id))
                         AS weeks,
                       (SELECT count(*) FROM rt.mentions m {ON_CUR})
                         AS mentions,
                       (SELECT count(*) FROM rt.mention_assets x JOIN rt.mentions m
                          ON m.id = x.mention_id {ON_CUR}) AS assets,
                       (SELECT count(*) FROM rt.mention_assets x JOIN rt.mentions m
                          ON m.id = x.mention_id {ON_CUR}
                        WHERE x.asset_id IS NULL) AS unknown,
                       (SELECT min(p.week_friday) FROM cur JOIN rt.weekly_picks p USING (video_id))
                         AS first_week,
                       (SELECT max(p.week_friday) FROM cur JOIN rt.weekly_picks p USING (video_id))
                         AS last_week""",
            a,
        ).fetchone()
        unknown = cur.execute(
            f"""WITH {CURRENT}
                SELECT x.spoken, x.kind_guess, x.ticker_guess, count(*) AS n,
                       count(DISTINCT m.video_id) AS weeks
                FROM rt.mention_assets x JOIN rt.mentions m ON m.id = x.mention_id
                {ON_CUR} WHERE x.asset_id IS NULL
                GROUP BY 1, 2, 3 ORDER BY n DESC, 1 LIMIT 20""",
            a,
        ).fetchall()
        plays = cur.execute(
            f"""WITH {CURRENT}
                SELECT m.play, count(*) AS n, count(DISTINCT m.video_id) AS weeks,
                       count(*) FILTER (WHERE m.stance = 'bullish') AS bullish,
                       count(*) FILTER (WHERE m.stance = 'bearish') AS bearish
                FROM rt.mentions m {ON_CUR} GROUP BY 1 ORDER BY 2 DESC""",
            a,
        ).fetchall()
        spend = cur.execute(
            """SELECT purpose, count(*) AS runs, sum(usd)::float AS usd, sum(weeks) AS weeks,
                      sum(output_tokens) AS output_tokens
               FROM rt.mine_runs WHERE engine = 'llm' GROUP BY 1 ORDER BY 3 DESC"""
        ).fetchall()
        gold = cur.execute(
            """SELECT g.video_id, p.week_friday FROM rt.gold_weeks g
               JOIN rt.weekly_picks p USING (video_id) ORDER BY p.week_friday"""
        ).fetchall()
        labels = cur.execute(
            "SELECT source, verdict, count(*) AS n FROM rt.labels GROUP BY 1, 2 ORDER BY 1, 2"
        ).fetchall()
        spot = cur.execute(
            """SELECT count(*) AS total,
                      count(*) FILTER (WHERE EXISTS (SELECT 1 FROM rt.labels l
                        WHERE l.mention_id = s.mention_id AND l.source = 'owner')) AS done
               FROM rt.spot_checks s"""
        ).fetchone()
        drops = cur.execute(
            f"""WITH {CURRENT}
                SELECT d.reason, d.play, d.quote, p.week_friday, d.video_id
                FROM rt.mine_drops d JOIN cur ON cur.video_id = d.video_id AND cur.run_id = d.run_id
                JOIN rt.weekly_picks p ON p.video_id = d.video_id
                ORDER BY p.week_friday DESC LIMIT 20""",
            a,
        ).fetchall()
    return {
        "version": PRODUCTION,
        "prompt_sha": a["prompt"],
        "coverage": cov,
        "runs": runs,
        "eval": ev,
        "history": history,
        "unknown": unknown,
        "plays": plays,
        "spend": spend,
        "gold": {"weeks": gold, "labels": labels, "spot": spot},
        "drops": drops,
    }


CONTEXT = 420


def spot_checks(con: psycopg.Connection) -> list[dict[str, Any]]:
    with con.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(
            f"""SELECT s.ord, {MENTION_COLS},
                       substr(c.text, greatest(m.span_start - {CONTEXT}, 0) + 1,
                              m.span_start - greatest(m.span_start - {CONTEXT}, 0)) AS before,
                       substr(c.text, m.span_end + 1, {CONTEXT}) AS after,
                       (SELECT json_build_object('verdict', l.verdict, 'fixes', l.fixes,
                                                 'note', l.note, 'at', l.labeled_at)
                        FROM rt.labels l WHERE l.mention_id = m.id AND l.source = 'owner'
                        ORDER BY l.labeled_at DESC LIMIT 1) AS owner,
                       (SELECT json_build_object('verdict', l.verdict, 'fixes', l.fixes,
                                                 'note', l.note)
                        FROM rt.labels l WHERE l.mention_id = m.id AND l.source = 'second-read'
                        ORDER BY l.labeled_at DESC LIMIT 1) AS second_read
                FROM rt.spot_checks s JOIN {MENTION_FROM} ON m.id = s.mention_id
                ORDER BY s.ord"""
        ).fetchall()
    return rows


class Labeler:
    """The one write path in the viewer: an owner spot-check on a sampled gold mention."""

    VERDICTS = ("correct", "wrong", "fix")
    FIX_KEYS = ("play", "direction", "asset_id", "role")

    def save(
        self, mention_id: int, verdict: str, fixes: dict[str, Any], note: str | None
    ) -> dict[str, Any]:
        if verdict not in self.VERDICTS:
            raise ValueError(f"verdict must be one of {self.VERDICTS}")
        fixes = {k: v for k, v in (fixes or {}).items() if k in self.FIX_KEYS and v}
        play = fixes.get("play")
        if play and play not in PLAYS:
            raise ValueError(f"unknown play {play!r}")
        if "direction" in fixes:
            allowed = DIRECTIONS.get(play or "", ())
            if play and fixes["direction"] not in allowed:
                raise ValueError(f"direction {fixes['direction']!r} does not fit play {play!r}")
        with db.connect() as con:
            hit = con.execute(
                "SELECT 1 FROM rt.spot_checks WHERE mention_id = %s", (mention_id,)
            ).fetchone()
            if hit is None:
                raise LookupError(f"mention {mention_id} is not in the spot-check queue")
            if fixes.get("asset_id"):
                ok = con.execute(
                    "SELECT 1 FROM rt.assets WHERE id = %s", (fixes["asset_id"],)
                ).fetchone()
                if ok is None:
                    raise ValueError(f"unknown asset {fixes['asset_id']!r}")
            row = con.execute(
                """INSERT INTO rt.labels (mention_id, source, verdict, fixes, note, labeled_by)
                   VALUES (%s, 'owner', %s, %s, %s, 'owner')
                   RETURNING id, mention_id, verdict, fixes, note, labeled_at""",
                (mention_id, verdict, Jsonb(fixes), (note or "")[:1000] or None),
            ).fetchone()
            con.commit()
        assert row is not None
        keys = ("id", "mention_id", "verdict", "fixes", "note", "labeled_at")
        return dict(zip(keys, row, strict=True))
