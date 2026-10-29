"""``rt mine``: run an extractor over weeks and write versioned rows.

Every invocation is one ``rt.mine_runs`` row and one MLflow run (experiment
``rotation-tracker/mining``; counts, tokens and dollars only, never transcript text). Each
week's mentions pass the gates in order: the direction fits the play, the quote is found in the
text (``locate``), and each asset is resolved through the alias table (``resolve``). What fails a
gate is kept in ``rt.mine_drops`` with the reason.
"""

from __future__ import annotations

import secrets
import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from rotation_tracker import tracking
from rotation_tracker.config import settings
from rotation_tracker.mining import corpus, extract
from rotation_tracker.mining.locate import locate
from rotation_tracker.mining.resolve import Resolver
from rotation_tracker.mining.resolve import load as load_resolver
from rotation_tracker.mining.schema import (
    EXTRACTOR_VERSION,
    Mention,
    asset_stance,
    check,
    mention_stance,
)

Log = Callable[[str], None]
PRODUCTION = EXTRACTOR_VERSION
CURRENT_PURPOSES = ("dev", "eval", "backfill", "new-week")  # what the viewer reads
IN_FLIGHT = 4


@dataclass(frozen=True)
class Spec:
    engine: str = "llm"  # 'llm' | 'regex'
    purpose: str = "dev"
    version: str = EXTRACTOR_VERSION
    model: str | None = extract.MODEL
    effort: str | None = "high"
    mode: str = "interactive"  # 'interactive' | 'batch' | 'local'
    max_usd: float = 5.0


def new_run(con: psycopg.Connection, spec: Spec, weeks: int, batch_id: str | None = None) -> str:
    run_id = f"mine-{datetime.now(UTC):%Y%m%dT%H%M%S}-{secrets.token_hex(2)}"
    con.execute(
        """INSERT INTO rt.mine_runs (run_id, engine, extractor_version, prompt_sha, model, effort,
                                     mode, purpose, batch_id, status, weeks)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        (
            run_id,
            spec.engine,
            spec.version,
            extract.prompt_sha() if spec.engine == "llm" else None,
            spec.model if spec.engine == "llm" else None,
            spec.effort if spec.engine == "llm" else None,
            spec.mode,
            spec.purpose,
            batch_id,
            "submitted" if batch_id else "running",
            weeks,
        ),
    )
    con.commit()
    return run_id


def write_week(
    con: psycopg.Connection,
    run_id: str,
    week: corpus.Week,
    mentions: list[Mention],
    resolver: Resolver,
    usage: extract.Usage | None = None,
    usd: float = 0.0,
    stop_reason: str | None = None,
) -> tuple[int, int]:
    """Gate and write one week's mentions. Returns (kept, dropped)."""
    kept = dropped = 0
    read = week.read
    with con.cursor() as cur:
        for ord_, m in enumerate(mentions):
            reason = check(m)
            hit = None if reason else locate(m.quote, m.section, read)
            if reason is None and hit is None:
                reason = "not-located"
            if reason or hit is None:
                cur.execute(
                    """INSERT INTO rt.mine_drops
                         (run_id, video_id, ord, reason, play, quote, detail)
                       VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING""",
                    (
                        run_id,
                        week.video_id,
                        ord_,
                        reason,
                        m.play,
                        m.quote[:600],
                        Jsonb(m.model_dump(exclude={"quote"})),
                    ),
                )
                dropped += 1
                continue
            sec, found = hit
            roles = [a.role for a in m.assets]
            row = cur.execute(
                """INSERT INTO rt.mentions (run_id, video_id, ord, play, direction, stance, speaker,
                     reported_source, modality, horizon, confidence, quote, section_idx,
                     span_start, span_end, t_seconds, located, match_score)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   RETURNING id""",
                (
                    run_id,
                    week.video_id,
                    ord_,
                    m.play,
                    m.direction,
                    mention_stance(m.play, m.direction, roles),
                    m.speaker,
                    m.reported_source if m.speaker == "reported" else None,
                    m.modality,
                    m.horizon,
                    min(max(m.confidence, 0.0), 1.0),
                    sec.text[found.start : found.end],
                    sec.idx,
                    found.start,
                    found.end,
                    sec.t_at(found.start),
                    found.how,
                    found.score,
                ),
            ).fetchone()
            assert row is not None
            for j, a in enumerate(m.assets):
                r = resolver.resolve(a.spoken, a.ticker, a.kind)
                cur.execute(
                    """INSERT INTO rt.mention_assets (mention_id, ord, role, spoken, ticker_guess,
                         kind_guess, asset_id, resolution, stance)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    (
                        row[0],
                        j,
                        a.role,
                        a.spoken[:200],
                        a.ticker,
                        a.kind,
                        r.asset_id,
                        r.how,
                        asset_stance(m.play, m.direction, a.role),
                    ),
                )
            kept += 1
        u = usage or extract.Usage()
        cur.execute(
            """INSERT INTO rt.mine_weeks (run_id, video_id, status, mentions, dropped, input_tokens,
                 output_tokens, cache_read_tokens, cache_write_tokens, usd, stop_reason)
               VALUES (%s, %s, 'done', %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                run_id,
                week.video_id,
                kept,
                dropped,
                u.input_tokens,
                u.output_tokens,
                u.cache_read_tokens,
                u.cache_write_tokens,
                usd,
                stop_reason,
            ),
        )
    con.commit()
    return kept, dropped


def fail_week(con: psycopg.Connection, run_id: str, res: extract.Result, usd: float) -> None:
    u = res.usage
    con.execute(
        """INSERT INTO rt.mine_weeks (run_id, video_id, status, input_tokens, output_tokens,
             cache_read_tokens, cache_write_tokens, usd, stop_reason, error)
           VALUES (%s, %s, 'failed', %s, %s, %s, %s, %s, %s, %s)""",
        (
            run_id,
            res.video_id,
            u.input_tokens,
            u.output_tokens,
            u.cache_read_tokens,
            u.cache_write_tokens,
            usd,
            res.stop_reason,
            res.error,
        ),
    )
    con.commit()


def finish(con: psycopg.Connection, run_id: str, log: Log = print) -> dict[str, Any]:
    """Roll the weeks up into the run, mark it done, log it to MLflow."""
    con.execute(
        """UPDATE rt.mine_runs r SET
             status = CASE WHEN w.weeks_done = 0 THEN 'failed' ELSE 'done' END,
             finished_at = now(),
             mentions = w.mentions, dropped = w.dropped, input_tokens = w.i, output_tokens = w.o,
             cache_read_tokens = w.cr, cache_write_tokens = w.cw, usd = w.usd,
             detail = CASE WHEN w.failed > 0 THEN w.failed || ' weeks failed' END
           FROM (SELECT coalesce(sum(mentions), 0) AS mentions,
                        coalesce(sum(dropped), 0) AS dropped,
                        coalesce(sum(input_tokens), 0) AS i, coalesce(sum(output_tokens), 0) AS o,
                        coalesce(sum(cache_read_tokens), 0) AS cr,
                        coalesce(sum(cache_write_tokens), 0) AS cw, coalesce(sum(usd), 0) AS usd,
                        count(*) FILTER (WHERE status = 'failed') AS failed,
                        count(*) FILTER (WHERE status = 'done') AS weeks_done
                 FROM rt.mine_weeks WHERE run_id = %(r)s) w
           WHERE r.run_id = %(r)s""",
        {"r": run_id},
    )
    con.commit()
    summary = summarise(con, run_id)
    try:
        mid = tracking.log_run(
            run_id,
            f"mine-{summary['purpose']}",
            {
                k: summary[k]
                for k in ("engine", "extractor_version", "prompt_sha", "model", "effort", "mode")
            }
            | {"purpose": summary["purpose"]},
            {
                k: float(summary[k] or 0)
                for k in (
                    "weeks_done",
                    "weeks_failed",
                    "mentions",
                    "dropped",
                    "dropped_rate",
                    "unknown_rate",
                    "input_tokens",
                    "output_tokens",
                    "cache_read_tokens",
                    "cache_write_tokens",
                    "usd",
                )
            },
            experiment=settings().mining_experiment,
            billing="anthropic" if summary["engine"] == "llm" else "none",
        )
        con.execute("UPDATE rt.mine_runs SET mlflow_run_id = %s WHERE run_id = %s", (mid, run_id))
        con.commit()
        summary["mlflow_run_id"] = mid
    except Exception as e:  # the rows are the record; a down MLflow is reported, not fatal
        log(f"  MLflow logging failed: {type(e).__name__}: {str(e)[:160]}")
    return summary


def summarise(con: psycopg.Connection, run_id: str) -> dict[str, Any]:
    cols = [
        "run_id",
        "engine",
        "extractor_version",
        "prompt_sha",
        "model",
        "effort",
        "mode",
        "purpose",
        "batch_id",
        "status",
        "mentions",
        "dropped",
        "input_tokens",
        "output_tokens",
        "cache_read_tokens",
        "cache_write_tokens",
        "usd",
    ]
    row = con.execute(f"SELECT {', '.join(cols)} FROM rt.mine_runs WHERE run_id = %s", (run_id,))
    found = row.fetchone()
    if found is None:
        raise KeyError(run_id)
    s = dict(zip(cols, found, strict=True))
    s["usd"] = float(s["usd"])
    w = con.execute(
        """SELECT count(*) FILTER (WHERE status = 'done'), count(*) FILTER (WHERE status = 'failed')
           FROM rt.mine_weeks WHERE run_id = %s""",
        (run_id,),
    ).fetchone()
    s["weeks_done"], s["weeks_failed"] = w if w else (0, 0)
    total = (s["mentions"] or 0) + (s["dropped"] or 0)
    s["dropped_rate"] = round((s["dropped"] or 0) / total, 4) if total else 0.0
    u = con.execute(
        """SELECT count(*), count(*) FILTER (WHERE a.asset_id IS NULL)
           FROM rt.mention_assets a JOIN rt.mentions m ON m.id = a.mention_id
           WHERE m.run_id = %s""",
        (run_id,),
    ).fetchone()
    s["assets"], s["unknown"] = u if u else (0, 0)
    s["unknown_rate"] = round(s["unknown"] / s["assets"], 4) if s["assets"] else 0.0
    return s


# ── engines ───────────────────────────────────────────────────────────────────────────────
def mine_interactive(
    con: psycopg.Connection, spec: Spec, video_ids: list[str], log: Log = print
) -> dict[str, Any]:
    weeks = [corpus.load(con, v) for v in video_ids]
    est = extract.estimate(weeks, spec.effort or "high", batch=False, model=spec.model or "")
    log(f"  {len(weeks)} weeks, estimate ≤ ${est:.2f} (cap ${spec.max_usd:.2f})")
    if est > spec.max_usd:
        raise SystemExit(f"estimate ${est:.2f} is over --max-usd {spec.max_usd:.2f}; not run")
    resolver = load_resolver(con)
    run_id = new_run(con, spec, len(weeks))
    log(f"  run {run_id}")
    cl = extract.client()
    by_id = {w.video_id: w for w in weeks}
    pending = list(weeks)
    spent = 0.0
    with ThreadPoolExecutor(IN_FLIGHT) as pool:
        live: dict[Future[extract.Result], str] = {}
        while pending or live:
            while pending and len(live) < IN_FLIGHT and spent < spec.max_usd:
                w = pending.pop(0)
                live[pool.submit(extract.call, cl, w, spec.effort or "high", spec.model or "")] = (
                    w.video_id
                )
            if not live:
                log(f"  stopped: ${spent:.2f} spent reached the cap; {len(pending)} weeks not run")
                break
            done = next(iter(f for f in list(live) if f.done()), None)
            if done is None:
                time.sleep(0.5)
                continue
            vid = live.pop(done)
            res = done.result()
            usd = res.usage.usd(spec.model or extract.MODEL)
            spent += usd
            if res.mentions is None:
                fail_week(con, run_id, res, usd)
                log(f"  {vid} FAILED ({res.error}) ${usd:.3f}")
                continue
            kept, dropped = write_week(
                con, run_id, by_id[vid], res.mentions.mentions, resolver, res.usage, usd,
                res.stop_reason,
            )  # fmt: skip
            log(
                f"  {by_id[vid].week_friday} {vid} {kept:3d} kept {dropped:2d} dropped "
                f"in {res.usage.input_tokens + res.usage.cache_read_tokens:6d} "
                f"out {res.usage.output_tokens:6d} ${usd:.3f}"
            )
    return finish(con, run_id, log)


def submit_batch(
    con: psycopg.Connection, spec: Spec, video_ids: list[str], log: Log = print
) -> str:
    weeks = [corpus.load(con, v) for v in video_ids]
    est = extract.estimate(weeks, spec.effort or "high", batch=True, model=spec.model or "")
    log(f"  {len(weeks)} weeks through the Batch API, estimate ≤ ${est:.2f} (cap ${spec.max_usd})")
    if est > spec.max_usd:
        raise SystemExit(f"estimate ${est:.2f} is over --max-usd {spec.max_usd:.2f}; not submitted")
    batch_id = extract.submit(extract.client(), weeks, spec.effort or "high", spec.model or "")
    run_id = new_run(con, spec, len(weeks), batch_id=batch_id)
    log(f"  run {run_id} batch {batch_id}: collect with `rt mine collect {run_id}`")
    return run_id


def collect(con: psycopg.Connection, run_id: str, log: Log = print) -> dict[str, Any] | None:
    """Write a finished batch's results; None while it is still processing."""
    row = con.execute(
        "SELECT batch_id, status, model FROM rt.mine_runs WHERE run_id = %s", (run_id,)
    ).fetchone()
    if row is None or row[0] is None:
        raise SystemExit(f"{run_id}: not a batch run")
    batch_id, status, model = row
    if status in ("done", "failed"):
        return summarise(con, run_id)
    cl = extract.client()
    state, counts = extract.batch_status(cl, batch_id)
    log(f"  {batch_id}: {state} {counts}")
    if state != "ended":
        return None
    resolver = load_resolver(con)
    seen = {
        v for (v,) in con.execute("SELECT video_id FROM rt.mine_weeks WHERE run_id = %s", (run_id,))
    }
    for res in extract.batch_results(cl, batch_id):
        if res.video_id in seen:
            continue
        usd = res.usage.usd(model or extract.MODEL, batch=True)
        if res.mentions is None:
            fail_week(con, run_id, res, usd)
            log(f"  {res.video_id} FAILED ({res.error})")
            continue
        week = corpus.load(con, res.video_id)
        write_week(
            con, run_id, week, res.mentions.mentions, resolver, res.usage, usd, res.stop_reason
        )
    return finish(con, run_id, log)


def mine_regex(
    con: psycopg.Connection, video_ids: list[str], purpose: str = "baseline", log: Log = print
) -> dict[str, Any]:
    from rotation_tracker.mining import baseline

    spec = Spec(engine="regex", purpose=purpose, version=baseline.VERSION, mode="local")
    resolver = load_resolver(con)
    scanner = baseline.Scanner.from_db(con)
    run_id = new_run(con, spec, len(video_ids))
    for vid in video_ids:
        week = corpus.load(con, vid)
        write_week(con, run_id, week, scanner.scan(week), resolver)
    return finish(con, run_id, log)


def current_weeks(con: psycopg.Connection, version: str = PRODUCTION) -> set[str]:
    """Weeks that already have a finished run of ``version`` with today's prompt."""
    return {
        v
        for (v,) in con.execute(
            """SELECT DISTINCT w.video_id FROM rt.mine_weeks w JOIN rt.mine_runs r USING (run_id)
               WHERE w.status = 'done' AND r.extractor_version = %s AND r.purpose = ANY(%s)
                 AND r.prompt_sha = %s""",
            (version, list(CURRENT_PURPOSES), extract.prompt_sha()),
        )
    }


def reresolve(con: psycopg.Connection, every: bool = False, log: Log = print) -> dict[str, int]:
    """Resolve unknown and ambiguous assets again, after aliases were added.

    ``every`` also re-resolves model-extracted assets that already resolved (an alias moved, or
    the resolver changed). A regex run's are left: its spoken forms are the alias table it was
    scanned with, so it is re-run instead.
    """
    resolver = load_resolver(con)
    rows = con.execute(
        """SELECT a.mention_id, a.ord, a.spoken, a.ticker_guess, a.kind_guess, a.asset_id,
                  a.resolution
           FROM rt.mention_assets a JOIN rt.mentions m ON m.id = a.mention_id
           JOIN rt.mine_runs r USING (run_id)
           WHERE a.resolution IN ('unknown', 'ambiguous') OR (%s AND r.engine = 'llm')""",
        (every,),
    ).fetchall()
    fixed = moved = unresolved = 0
    with con.cursor() as cur:
        for mid, ord_, spoken, ticker, kind, was, how in rows:
            r = resolver.resolve(spoken, ticker, kind)
            unresolved += r.asset_id is None
            if (r.asset_id, r.how) == (was, how) or not (r.asset_id or was):
                continue
            cur.execute(
                """UPDATE rt.mention_assets SET asset_id = %s, resolution = %s
                   WHERE mention_id = %s AND ord = %s""",
                (r.asset_id, r.how, mid, ord_),
            )
            if was:
                moved += was != r.asset_id
            else:
                fixed += 1
    con.commit()
    out = {"checked": len(rows), "resolved": fixed, "moved": moved, "still_unknown": unresolved}
    log(f"  {out}")
    return out
