"""What the viewer reads. Every method is a read:

- Postgres schema ``rt`` as ``rotation_ro`` (read-only transactions);
- transcript·lab's Chroma store, through its SQLite file opened read-only (``chroma.py``);
- the central MLflow, for run links and the ingest runs' metrics;
- Supadata's free ``GET /v1/me``, for the credit balance (never a key).
"""

from __future__ import annotations

import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import asdict
from datetime import UTC, date, datetime
from typing import Any

import psycopg
from psycopg.rows import dict_row

from rotation_tracker import db, pipeline, supadata
from rotation_tracker.config import ROOT, settings
from rotation_tracker.mining.run import PRODUCTION
from rotation_tracker.serving import mining, themes
from rotation_tracker.serving.chroma import Chroma
from rotation_tracker.tracking import git_sha

SPEC = ROOT / "ai_specs" / "s00_data_pipeline.md"
READ_TOPICS = ("macro-flows", "untagged")  # what rotation work reads (s00)
TOPICS = ("macro-flows", "technicals", "intro-outro", "promo", "untagged")
NY = "America/New_York"

WEEKS_SQL = """
SELECT p.week_friday, p.video_id, p.reason, v.title, v.published_at, v.duration_s, v.view_count,
       t.n_segments, length(t.text) AS n_chars,
       (SELECT count(*) FROM rt.chapters c WHERE c.video_id = p.video_id) AS n_chapters
FROM rt.weekly_picks p
JOIN rt.videos v USING (video_id)
LEFT JOIN rt.transcripts t USING (video_id)
{where}
ORDER BY p.week_friday DESC
"""

SEARCH_SQL = """
WITH q AS (SELECT websearch_to_tsquery('english', %(q)s) AS q)
SELECT c.video_id, c.idx, c.title AS section, c.topic, c.start_s, p.week_friday, v.title,
       ts_rank(c.tsv, q.q) AS rank,
       ts_headline('english', c.text, q.q,
         'StartSel=«, StopSel=», MaxWords=32, MinWords=14, MaxFragments=2, FragmentDelimiter=" … "')
         AS snippet
FROM rt.transcript_chapters c
CROSS JOIN q
JOIN rt.weekly_picks p USING (video_id)
JOIN rt.videos v USING (video_id)
WHERE c.tsv @@ q.q AND c.topic = ANY(%(topics)s)
ORDER BY {order}
LIMIT %(limit)s
"""

SEARCH_BY_QUARTER_SQL = """
WITH q AS (SELECT websearch_to_tsquery('english', %(q)s) AS q)
SELECT date_trunc('quarter', p.week_friday)::date AS quarter,
       count(DISTINCT c.video_id) AS weeks, count(*) AS sections
FROM rt.transcript_chapters c
CROSS JOIN q
JOIN rt.weekly_picks p USING (video_id)
WHERE c.tsv @@ q.q AND c.topic = ANY(%(topics)s)
GROUP BY 1
"""

QUARTER_WEEKS_SQL = """
SELECT date_trunc('quarter', p.week_friday)::date, count(*)
FROM rt.weekly_picks p
WHERE EXISTS (SELECT 1 FROM rt.transcripts t WHERE t.video_id = p.video_id)
GROUP BY 1
"""

# The same keyword hits, counted only inside the quotes of the miner's current calls (s02) and
# split by the stance on the call's asset in that theme: every asset of the call whose spoken
# words or name match the theme must lean the same way, or the hits stay unclassified.
THEME_STANCE_SQL = f"""
WITH {mining.CURRENT},
m AS (
  SELECT m.id, m.stance, date_trunc('quarter', p.week_friday)::date AS quarter,
         regexp_count(m.quote, %(re)s, 1, 'i') AS hits
  FROM rt.mentions m {mining.ON_CUR}
  JOIN rt.weekly_picks p ON p.video_id = m.video_id
),
side AS (
  SELECT m.quarter, m.hits,
         (SELECT CASE WHEN bool_and(coalesce(a.stance, m.stance) = 'bullish') THEN 'bullish'
                      WHEN bool_and(coalesce(a.stance, m.stance) = 'bearish') THEN 'bearish' END
          FROM rt.mention_assets a LEFT JOIN rt.assets s ON s.id = a.asset_id
          WHERE a.mention_id = m.id
            AND (coalesce(a.spoken, '') || ' ' || coalesce(s.name, '')) ~* %(re)s) AS stance
  FROM m WHERE m.hits > 0
)
SELECT quarter, sum(hits) FILTER (WHERE stance = 'bullish') AS bullish,
       sum(hits) FILTER (WHERE stance = 'bearish') AS bearish
FROM side GROUP BY 1
"""

# The assets view: the miner's current calls per asset and quarter, split by the stance on that
# asset (its own, else the call's). A call naming an asset twice counts once.
ASSET_CALLS_SQL = f"""
WITH {mining.CURRENT}
SELECT a.asset_id, date_trunc('quarter', p.week_friday)::date AS quarter,
       count(DISTINCT m.id) AS calls, count(DISTINCT m.video_id) AS weeks,
       count(DISTINCT m.id) FILTER (WHERE coalesce(a.stance, m.stance) = 'bullish') AS bullish,
       count(DISTINCT m.id) FILTER (WHERE coalesce(a.stance, m.stance) = 'bearish') AS bearish
FROM rt.mentions m {mining.ON_CUR}
JOIN rt.mention_assets a ON a.mention_id = m.id
JOIN rt.weekly_picks p ON p.video_id = m.video_id
WHERE a.asset_id IS NOT NULL
GROUP BY 1, 2
"""

THEME_SQL = """
SELECT date_trunc('quarter', p.week_friday)::date AS quarter,
       sum(regexp_count(c.text, %(re)s, 1, 'i')) AS mentions,
       count(DISTINCT c.video_id) FILTER (WHERE c.text ~* %(re)s) AS weeks
FROM rt.transcript_chapters c
JOIN rt.weekly_picks p USING (video_id)
WHERE c.topic = ANY(%(topics)s)
GROUP BY 1
"""


def paragraphs(
    segments: list[dict[str, Any]], start: float, end: float | None, every: float = 40.0
) -> list[dict[str, Any]]:
    """The segments that start inside [start, end), joined into paragraphs of about ``every``
    seconds. A paragraph ends at a sentence once it is long enough, or regardless at 2x."""
    stop = end if end is not None else float("inf")
    out: list[dict[str, Any]] = []
    t0: float | None = None
    words: list[str] = []
    for s in segments:
        t = float(s.get("start_seconds") or 0.0)
        if not start <= t < stop:
            continue
        text = str(s.get("text", "")).strip()
        if not text:
            continue
        if t0 is None:
            t0 = t
        words.append(text)
        long_enough = t - t0 >= every
        if (long_enough and text.endswith((".", "?", "!"))) or t - t0 >= 2 * every:
            out.append({"t": t0, "text": " ".join(words)})
            t0, words = None, []
    if words and t0 is not None:
        out.append({"t": t0, "text": " ".join(words)})
    return out


def decisions() -> list[dict[str, str]]:
    """The decisions table of the plan of record, so the viewer never drifts from it."""
    m = re.search(r"## Decisions[^\n]*\n\n((?:\|[^\n]*\n)+)", SPEC.read_text())
    if not m:
        return []
    rows = []
    for line in m.group(1).splitlines()[2:]:
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 2:
            rows.append({"question": cells[0], "decision": cells[1]})
    return rows


class _Cached:
    """One value, refreshed at most every ``ttl`` seconds; a failure is cached as the error."""

    def __init__(self, ttl: float, fetch: Callable[[], Any]) -> None:
        self.ttl, self.fetch = ttl, fetch
        self.at = 0.0
        self.value: Any = None
        self.error: str | None = None
        self.lock = threading.Lock()

    def get(self) -> tuple[Any, str | None]:
        with self.lock:
            if time.time() - self.at >= self.ttl:
                self.at = time.time()
                try:
                    self.value, self.error = self.fetch(), None
                except Exception as e:  # a service being down is a state the page shows
                    self.value, self.error = None, f"{type(e).__name__}: {str(e)[:160]}"
            return self.value, self.error


class Mlflow:
    """Whether the central MLflow answers, this project's experiment id, and its runs."""

    def __init__(self) -> None:
        self._up = _Cached(30, self._health)
        self._exp = _Cached(300, self._experiment)
        self._mining = _Cached(300, lambda: self._experiment(settings().mining_experiment))

    def _call(self, path: str, body: dict[str, Any] | None = None) -> Any:
        base = settings().mlflow_tracking_uri.rstrip("/")
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(f"{base}{path}", data=data)
        if data:
            req.add_header("content-type", "application/json")
        with urllib.request.urlopen(req, timeout=2) as r:  # noqa: S310 - the platform URL
            raw = r.read()
        return json.loads(raw or b"{}") if path.startswith("/api/") else raw

    def _health(self) -> bool:
        self._call("/health")
        return True

    def _experiment(self, name: str | None = None) -> str:
        q = urllib.parse.quote(name or settings().experiment)
        doc = self._call(f"/api/2.0/mlflow/experiments/get-by-name?experiment_name={q}")
        return str(doc["experiment"]["experiment_id"])

    def mining_urls(self, run_ids: list[str | None]) -> dict[str, Any]:
        """Links into the mining experiment: the experiment and each run that logged."""
        exp, _ = self._mining.get() if self.up else (None, None)
        base = settings().mlflow_tracking_uri.rstrip("/")
        if not exp:
            return {"experiment": None, "runs": {}}
        return {
            "experiment": f"{base}/#/experiments/{exp}",
            "runs": {r: f"{base}/#/experiments/{exp}/runs/{r}" for r in run_ids if r},
        }

    @property
    def up(self) -> bool:
        return bool(self._up.get()[0])

    def experiment_url(self) -> str | None:
        exp, _ = self._exp.get() if self.up else (None, None)
        base = settings().mlflow_tracking_uri.rstrip("/")
        return f"{base}/#/experiments/{exp}" if exp else None

    def runs(self) -> list[dict[str, Any]]:
        exp, _ = self._exp.get() if self.up else (None, None)
        if not exp:
            return []
        try:
            doc = self._call(
                "/api/2.0/mlflow/runs/search",
                {
                    "experiment_ids": [exp],
                    "max_results": 25,
                    "order_by": ["attributes.start_time DESC"],
                },
            )
        except (urllib.error.URLError, OSError, ValueError):
            return []
        base = settings().mlflow_tracking_uri.rstrip("/")
        out = []
        for r in doc.get("runs", []):
            info, data = r["info"], r.get("data", {})
            tags = {t["key"]: t["value"] for t in data.get("tags", [])}
            out.append(
                {
                    "run_id": info["run_id"],
                    "name": info.get("run_name") or tags.get("mlflow.runName"),
                    "kind": tags.get("kind"),
                    "status": info.get("status"),
                    "started": datetime.fromtimestamp(int(info["start_time"]) / 1000, tz=UTC),
                    "metrics": {m["key"]: m["value"] for m in data.get("metrics", [])},
                    "url": f"{base}/#/experiments/{exp}/runs/{info['run_id']}",
                }
            )
        return out


def _credits() -> list[dict[str, Any]]:
    return [
        {"key": b.n, "plan": b.plan, "left": b.left, "max": b.max_credits}
        for b in supadata.balances()
    ]


class Store:
    def __init__(self) -> None:
        self.mlflow = Mlflow()
        self._credits = _Cached(600, _credits)
        self._themes = _Cached(600, self._theme_counts)  # the corpus changes once a week
        self._assets = _Cached(600, self._asset_counts)  # ... and the miner with it
        self.chroma = Chroma(settings().transcript_lab_chroma)
        self.code_sha = git_sha()

    # ── plumbing ──────────────────────────────────────────────────────────────
    @contextmanager
    def _con(self) -> Iterator[psycopg.Connection]:
        with db.connect(readonly=True) as con:
            yield con

    # ── routes ────────────────────────────────────────────────────────────────
    def health(self) -> dict[str, Any]:
        def check(f: Callable[[], object]) -> str:
            try:
                f()
                return "up"
            except Exception:
                return "down"

        def pg() -> None:
            with self._con() as con:
                con.execute("SELECT 1")

        return {
            "ok": True,
            "code_sha": self.code_sha,
            "postgres": check(pg),
            "chroma": check(lambda: self.chroma.count("raw_transcripts")),
            "mlflow": "up" if self.mlflow.up else "down",
        }

    def weeks(self) -> list[dict[str, Any]]:
        with self._con() as con, con.cursor(row_factory=dict_row) as cur:
            return cur.execute(WEEKS_SQL.format(where="")).fetchall()

    def overview(self) -> dict[str, Any]:
        with self._con() as con, con.cursor(row_factory=dict_row) as cur:
            status = pipeline.status(con)
            totals = cur.execute(
                """SELECT sum(length(t.text)) AS chars,
                          sum(array_length(string_to_array(t.text, ' '), 1)) AS words,
                          sum(t.n_segments) AS segments, sum(v.duration_s) AS seconds
                   FROM rt.transcripts t JOIN rt.videos v USING (video_id)"""
            ).fetchone()
            topics = dict(
                con.execute(
                    "SELECT topic, count(*) FROM rt.transcript_chapters GROUP BY 1"
                ).fetchall()
            )
            latest = cur.execute(WEEKS_SQL.format(where="") + " LIMIT 8").fetchall()
        return {
            "status": status,
            "totals": totals,
            "topics": {t: topics.get(t, 0) for t in TOPICS},
            "latest": latest,
            "channel": {"name": settings().channel_name, "handle": settings().channel},
        }

    def week(self, video_id: str) -> dict[str, Any] | None:
        with self._con() as con, con.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                WEEKS_SQL.format(where="WHERE p.video_id = %s"), (video_id,)
            ).fetchone()
            if row is None:
                return None
            t = cur.execute(
                "SELECT segments, sha256, synced_at FROM rt.transcripts WHERE video_id = %s",
                (video_id,),
            ).fetchone()
            sections = cur.execute(
                """SELECT idx, start_s, end_s, title, topic, topic_rule_version,
                          length(text) AS n_chars
                   FROM rt.transcript_chapters WHERE video_id = %s ORDER BY idx""",
                (video_id,),
            ).fetchall()
            ingest = cur.execute(
                """SELECT batch_id, started_at, finished_at, returncode, status
                   FROM rt.ingest_log WHERE video_id = %s ORDER BY started_at""",
                (video_id,),
            ).fetchall()
            near = cur.execute(
                """SELECT
                     (SELECT video_id FROM rt.weekly_picks WHERE week_friday < %(f)s
                      ORDER BY week_friday DESC LIMIT 1) AS prev,
                     (SELECT video_id FROM rt.weekly_picks WHERE week_friday > %(f)s
                      ORDER BY week_friday LIMIT 1) AS next""",
                {"f": row["week_friday"]},
            ).fetchone()
        segments = (t or {}).get("segments") or []
        for s in sections:
            s["paragraphs"] = paragraphs(segments, s["start_s"] or 0.0, s["end_s"])
        try:
            n_chunks = self.chroma.count_where("transcript_chunks", "video_id", [video_id])
        except Exception:
            n_chunks = None
        return {
            **row,
            "sections": sections,
            "ingest": ingest,
            "prev": (near or {}).get("prev"),
            "next": (near or {}).get("next"),
            "stored": {
                "sha256": (t or {}).get("sha256"),
                "synced_at": (t or {}).get("synced_at"),
                "chroma_raw_id": f"raw_transcript:{video_id}",
                "chroma_chunks": n_chunks,
            },
            "mlflow_url": self.mlflow.experiment_url(),
        }

    def chunks(self, video_id: str) -> list[dict[str, Any]]:
        return self.chroma.chunks(video_id)

    def search(self, q: str, topics: list[str], order: str, limit: int) -> dict[str, Any]:
        q = q.strip()
        topics = [t for t in topics if t in TOPICS] or list(READ_TOPICS)
        params = {"q": q, "topics": topics, "limit": limit}
        by = "rank DESC, p.week_friday DESC" if order == "rank" else "p.week_friday DESC, c.idx"
        with self._con() as con, con.cursor(row_factory=dict_row) as cur:
            weeks = dict(con.execute(QUARTER_WEEKS_SQL).fetchall())
            if not q:
                return {"q": q, "topics": topics, "hits": [], "quarters": [], "total": None}
            hits = cur.execute(SEARCH_SQL.format(order=by), params).fetchall()
            per_q = cur.execute(SEARCH_BY_QUARTER_SQL, params).fetchall()
        found = {r["quarter"]: r for r in per_q}
        quarters = [
            {
                "quarter": qd,
                "weeks": found.get(qd, {}).get("weeks", 0),
                "sections": found.get(qd, {}).get("sections", 0),
                "of": n,
            }
            for qd, n in sorted(weeks.items())
        ]
        total = {
            "sections": sum(r["sections"] for r in per_q),
            "weeks": sum(r["weeks"] for r in per_q),
            "of": sum(weeks.values()),
        }
        return {"q": q, "topics": topics, "hits": hits, "quarters": quarters, "total": total}

    def _theme_counts(self) -> dict[str, Any]:
        mentions: dict[str, dict[date, int]] = {}
        hit: dict[str, dict[date, int]] = {}
        bullish: dict[str, dict[date, int]] = {}
        bearish: dict[str, dict[date, int]] = {}
        with self._con() as con:
            weeks: dict[date, int] = dict(con.execute(QUARTER_WEEKS_SQL).fetchall())
            for name, body in themes.THEMES:
                args = {"re": themes.pattern(body), "topics": list(READ_TOPICS)}
                rows = con.execute(THEME_SQL, args).fetchall()
                mentions[name] = {q: int(m or 0) for q, m, _ in rows}
                hit[name] = {q: int(w or 0) for q, _, w in rows}
                sides = con.execute(THEME_STANCE_SQL, mining._args(re=args["re"])).fetchall()
                bullish[name] = {q: int(u or 0) for q, u, _ in sides}
                bearish[name] = {q: int(d or 0) for q, _, d in sides}
        return {
            "weeks": weeks,
            "mentions": mentions,
            "hit": hit,
            "bullish": bullish,
            "bearish": bearish,
        }

    def _asset_counts(self) -> dict[str, Any]:
        calls: dict[str, dict[date, int]] = {}
        hit: dict[str, dict[date, int]] = {}
        bullish: dict[str, dict[date, int]] = {}
        bearish: dict[str, dict[date, int]] = {}
        with self._con() as con:
            weeks: dict[date, int] = dict(con.execute(QUARTER_WEEKS_SQL).fetchall())
            for aid, q, n, w, up, down in con.execute(ASSET_CALLS_SQL, mining._args()).fetchall():
                calls.setdefault(aid, {})[q] = n
                hit.setdefault(aid, {})[q] = w
                bullish.setdefault(aid, {})[q] = up
                bearish.setdefault(aid, {})[q] = down
            names = {
                i: (name, kind)
                for i, name, kind in con.execute(
                    "SELECT id, name, kind FROM rt.assets WHERE id = ANY(%s)", [list(calls)]
                ).fetchall()
            }
        return {
            "weeks": weeks, "mentions": calls, "hit": hit, "bullish": bullish,
            "bearish": bearish, "names": names,
        }  # fmt: skip

    def chart(self, quarter: date | None, view: str = "themes") -> dict[str, Any]:
        counts, error = (self._assets if view == "assets" else self._themes).get()
        if counts is None:
            raise RuntimeError(error)
        weeks: dict[date, int] = counts["weeks"]
        quarters = sorted(weeks)
        today = date.today()

        def closed(q: date) -> bool:
            end = date(q.year + (q.month + 3 > 12), (q.month + 2) % 12 + 1, 1)
            return end <= today

        complete = [q for q in quarters if closed(q)]
        if quarter not in weeks:
            quarter = complete[-1] if complete else quarters[-1]
        entries, dropped = themes.rank(
            counts["mentions"], counts["hit"], weeks, quarter, size=None,
            bullish=counts["bullish"], bearish=counts["bearish"],
        )  # fmt: skip
        names: dict[str, tuple[str, str]] = counts.get("names", {})
        prev = [q for q in quarters if q < quarter]
        return {
            "view": view,
            "version": themes.THEMES_VERSION if view == "themes" else PRODUCTION,
            "quarter": quarter,
            "previous": prev[-1] if prev else None,
            "quarters": [{"quarter": q, "weeks": weeks[q], "closed": closed(q)} for q in quarters],
            "history_quarters": quarters,
            "weeks_in_quarter": weeks[quarter],
            # On the assets view an entry is ranked by id; it carries the asset's name and kind.
            "entries": [
                {
                    **asdict(e),
                    "id": e.theme,
                    "theme": names.get(e.theme, (e.theme, None))[0],
                    "kind": names.get(e.theme, (None, None))[1],
                }
                for e in entries
            ],  # fmt: skip
            "dropped": [names.get(d, (d, None))[0] for d in dropped],
            "themes": [{"name": n, "pattern": themes.pattern(b)} for n, b in themes.THEMES],
            "topics": list(READ_TOPICS),
        }

    def pipeline(self) -> dict[str, Any]:
        with self._con() as con, con.cursor(row_factory=dict_row) as cur:
            status = pipeline.status(con)
            tables = []
            for name in (
                "videos",
                "chapters",
                "weekly_picks",
                "ingest_log",
                "transcripts",
                "transcript_chapters",
            ):
                n = con.execute(f"SELECT count(*) FROM rt.{name}").fetchone()
                size = con.execute(
                    "SELECT pg_total_relation_size(%s::regclass)", (f"rt.{name}",)
                ).fetchone()
                tables.append(
                    {
                        "name": f"rt.{name}",
                        "rows": n[0] if n else 0,
                        "bytes": size[0] if size else 0,
                    }
                )
            batches = cur.execute(
                """SELECT batch_id, count(*) AS n,
                          count(*) FILTER (WHERE status = 'indexed') AS indexed,
                          min(started_at) AS started, max(finished_at) AS finished
                   FROM rt.ingest_log GROUP BY 1 ORDER BY started"""
            ).fetchall()
            hours = dict(
                con.execute(
                    f"""SELECT extract(hour FROM published_at AT TIME ZONE '{NY}')::int, count(*)
                        FROM rt.videos WHERE tab = 'videos' AND published_at IS NOT NULL
                        GROUP BY 1"""
                ).fetchall()
            )
            pick_days = dict(
                con.execute(
                    f"""SELECT extract(isodow FROM v.published_at AT TIME ZONE '{NY}')::int,
                               count(*)
                        FROM rt.weekly_picks p JOIN rt.videos v USING (video_id) GROUP BY 1"""
                ).fetchall()
            )
            years = cur.execute(
                """SELECT extract(year FROM week_friday)::int AS year, count(*) AS weeks,
                          count(*) FILTER (WHERE reason = 'weekend') AS weekend
                   FROM rt.weekly_picks GROUP BY 1 ORDER BY 1"""
            ).fetchall()
            pick_ids = [r[0] for r in con.execute("SELECT video_id FROM rt.weekly_picks")]
        chroma: dict[str, Any] = {"path": str(settings().transcript_lab_chroma)}
        try:
            raw = [f"raw_transcript:{v}" for v in pick_ids]
            chroma["raw_total"] = self.chroma.count("raw_transcripts")
            chroma["raw_ours"] = self.chroma.count("raw_transcripts", raw)
            chroma["chunks_total"] = self.chroma.count("transcript_chunks")
            chroma["chunks_ours"] = self.chroma.count_where(
                "transcript_chunks", "video_id", pick_ids
            )
        except Exception as e:
            chroma["error"] = f"{type(e).__name__}: {str(e)[:160]}"
        credits, credits_error = self._credits.get()
        return {
            "status": status,
            "tables": tables,
            "chroma": chroma,
            "batches": batches,
            "runs": self.mlflow.runs(),
            "mlflow_url": self.mlflow.experiment_url(),
            "credits": credits,
            "credits_error": credits_error,
            "hours_et": [hours.get(h, 0) for h in range(24)],
            "pick_weekdays": [pick_days.get(d, 0) for d in range(1, 8)],
            "years": years,
            "decisions": decisions(),
            "experiment": settings().experiment,
        }

    # ── s02: the miner ──────────────────────────────────────────────────────────────────
    def mentions(self, **filters: Any) -> dict[str, Any]:
        with self._con() as con:
            return mining.mentions(con, **filters)

    def assets(self, kind: str | None, q: str | None) -> dict[str, Any]:
        with self._con() as con:
            return mining.assets(con, kind, q)

    def asset(self, asset_id: str) -> dict[str, Any] | None:
        with self._con() as con:
            return mining.asset(con, asset_id)

    def mining(self) -> dict[str, Any]:
        with self._con() as con:
            out = mining.summary(con)
        out["mlflow"] = self.mlflow.mining_urls(
            [r["mlflow_run_id"] for r in out["runs"]]
            + ([out["eval"]["mlflow_run_id"]] if out["eval"] else [])
        )
        return out

    def spot_checks(self) -> list[dict[str, Any]]:
        with self._con() as con:
            return mining.spot_checks(con)
