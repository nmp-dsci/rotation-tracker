"""``rt``: the rotation-tracker command line."""

from __future__ import annotations

from pathlib import Path

import typer

from rotation_tracker import db, pipeline, supadata, tracking, youtube
from rotation_tracker.config import settings

app = typer.Typer(no_args_is_help=True, add_completion=False)
db_app = typer.Typer(no_args_is_help=True)
app.add_typer(db_app, name="db", help="Schema and connectivity.")
assets_app = typer.Typer(no_args_is_help=True)
app.add_typer(assets_app, name="assets", help="assets/v1: the asset map mentions resolve to.")
mine_app = typer.Typer(no_args_is_help=True)
app.add_typer(mine_app, name="mine", help="s02: mine the weekly wraps for asset calls.")
gold_app = typer.Typer(no_args_is_help=True)
app.add_typer(gold_app, name="gold", help="s02: the gold set the miner is measured against.")


@db_app.command("migrate")
def db_migrate() -> None:
    """Apply sql/*.sql as the superuser (idempotent)."""
    for name in db.migrate():
        typer.echo(f"applied {name}")


@db_app.command("smoke")
def db_smoke() -> None:
    """Zero-cost check: connect as the owner and the read-only role, read rt.videos."""
    for ro in (False, True):
        with db.connect(readonly=ro) as con:
            row = con.execute("SELECT current_user, count(*) FROM rt.videos").fetchone()
            typer.echo(f"{'ro   ' if ro else 'owner'} {row}")


@assets_app.command("seed")
def assets_seed(
    local: Path | None = typer.Option(
        None, help="Read <name>.{html,json,txt} for sp500, ndx, nasdaqlisted, otherlisted here."
    ),
) -> None:
    """Build rt.assets, rt.aliases and rt.asset_proxies from assets/*.yaml and the listings."""
    from rotation_tracker.mining import universe

    with db.connect() as con:
        report = universe.seed(con, local=local, log=typer.echo)
    for k, v in report.items():
        typer.echo(f"{k:15s} {v}")


# Every asset any mention points at (the miner's runs and the regex baseline alike).
MENTIONED_SQL = """SELECT s.id, s.kind, s.ticker FROM rt.assets s
                   WHERE EXISTS (SELECT 1 FROM rt.mention_assets a WHERE a.asset_id = s.id)
                   ORDER BY s.id"""


@assets_app.command("check-proxies")
def assets_check_proxies() -> None:
    """Fail unless every asset with a mention resolves to a typed series or a reasoned none."""
    from rotation_tracker.market import proxies
    from rotation_tracker.mining.universe import curated

    px = proxies.load()
    problems = proxies.check_curated(px, curated()["assets"])
    with db.connect(readonly=True) as con:
        mentioned = con.execute(MENTIONED_SQL).fetchall()
        counts, more = proxies.check(px, mentioned)
        problems += more
        seeded: dict[str, str] = dict(
            con.execute(
                """SELECT p.asset_id, p.series FROM rt.asset_proxies p
                   WHERE p.role = 'primary' AND p.asset_id = ANY(%s)""",
                ([aid for aid, _, _ in mentioned],),
            ).fetchall()
        )
    for aid, kind, ticker in mentioned:
        want = px.resolve(aid, kind, ticker)
        if want and seeded.get(aid) != want[0].series:
            problems.append(f"{aid}: rt.asset_proxies has {seeded.get(aid)}, proxies.yaml "
                            f"{want[0].series}; run `rt assets seed`")  # fmt: skip
    typer.echo(
        f"{counts['assets']} assets with a mention: {counts['priced']} priced, "
        f"{counts['none']} reasoned none, {counts['unresolved']} unresolved "
        f"({proxies.PROXIES_VERSION})"
    )
    for p in problems:
        typer.echo(f"  ✗ {p}")
    if problems:
        raise typer.Exit(1)
    typer.echo("check-proxies: ok")


@assets_app.command("export-symbols")
def assets_export_symbols(
    out: Path = typer.Option(
        None, help="Where to write (default ../market-getdata/instruments/rotation-tracker.txt)."
    ),
) -> None:
    """Write the series market-getdata fetches: every proxy and companion, every name he says."""
    from rotation_tracker.market import proxies
    from rotation_tracker.mining.universe import curated

    path = out or proxies.EXPORT_DEFAULT
    px = proxies.load()
    cur = [(a["id"], a["kind"]) for a in curated()["assets"]]
    with db.connect(readonly=True) as con:
        mentioned = con.execute(MENTIONED_SQL).fetchall()
        listing = {
            proxies.yahoo_spelling(t): k
            for t, k in con.execute(
                "SELECT ticker, kind FROM rt.assets WHERE kind IN ('stock', 'fund') "
                "AND ticker IS NOT NULL"
            ).fetchall()
        }
    lines = proxies.export(px, cur, mentioned, listing)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(proxies.render(lines))
    by: dict[str, int] = {}
    for ln in lines:
        key = ",".join(ln.reasons)
        by[key] = by.get(key, 0) + 1
    typer.echo(f"wrote {len(lines)} series to {path}")
    for key, n in sorted(by.items(), key=lambda kv: -kv[1]):
        typer.echo(f"  {n:4d}  {key}")
    for r in proxies.REASONS:
        typer.echo(f"  {sum(r in ln.reasons for ln in lines):4d}  with {r}")


@assets_app.command("components")
def assets_components(
    asset_id: str = typer.Argument(..., help="A category, e.g. theme:software."),
) -> None:
    """What is inside a category: its GICS list, his names by mentions, holdings (phase 2)."""
    from rotation_tracker.market import components, proxies

    with db.connect(readonly=True) as con:
        row = con.execute(
            "SELECT id, name, kind, ticker FROM rt.assets WHERE id = %s", (asset_id,)
        ).fetchone()
        if row is None:
            raise typer.BadParameter(f"{asset_id} is not in rt.assets")
        c = components.components(con, asset_id)
    aid, name, kind, ticker = row
    primary = proxies.load().resolve(aid, kind, ticker)
    typer.echo(f"{aid} · {name} · priced by {primary[0].series if primary else 'nothing'}")
    if not c["defined"]:
        typer.echo("no component list: assets/components.yaml maps GICS sub-industries, sectors")
        typer.echo("and the two indexes to categories, and this asset is not one of them")
        typer.echo(c["holdings"])
        return
    typer.echo(f"members ({'; '.join(c['basis'])}): {len(c['gics'])} names")
    tickers = [g["ticker"] for g in c["gics"]]
    for i in range(0, len(tickers), 16):
        typer.echo("  " + " ".join(tickers[i : i + 16]))
    typer.echo(f"his names, by mentions (play/v1, today's prompt): {len(c['named'])}")
    for n in c["named"]:
        via = "" if n["via"] == "gics" else f"  ({n['via']})"
        typer.echo(f"  {n['ticker'] or n['asset_id']:8s} {n['mentions']:4d}{via}")
    typer.echo(c["holdings"])


def _pick_weeks(
    con: object,
    weeks: str | None,
    gold: bool,
    all_: bool,
    since: str | None,
    skip_done: bool,
    limit: int | None,
) -> list[str]:
    from datetime import date

    from rotation_tracker.mining import corpus, run

    ids = [w for w in (weeks or "").split(",") if w]
    if gold:
        ids += [v for (v,) in con.execute("SELECT video_id FROM rt.gold_weeks")]  # type: ignore[attr-defined]
    if not (ids or all_ or since):
        raise typer.BadParameter("name the weeks: --weeks, --gold, --since or --all")
    chosen = corpus.weeks(
        con,  # type: ignore[arg-type]
        since=date.fromisoformat(since) if since else None,
        ids=ids or None,
    )
    out = [v for v, _ in chosen]
    if skip_done:
        done = run.current_weeks(con)  # type: ignore[arg-type]
        out = [v for v in out if v not in done]
    return out[:limit] if limit else out


@mine_app.command("run")
def mine_run(
    engine: str = typer.Option("llm", help="llm (play/v1) or regex (play/v0, free)."),
    weeks: str | None = typer.Option(None, help="Comma-separated video ids."),
    gold: bool = typer.Option(False, help="The twelve gold weeks (rt.gold_weeks)."),
    all_: bool = typer.Option(False, "--all", help="Every week with a transcript."),
    since: str | None = typer.Option(None, help="Weeks whose Friday is on or after this date."),
    skip_done: bool = typer.Option(False, help="Leave out weeks that already have play/v1 rows."),
    limit: int | None = typer.Option(None, help="At most this many weeks, newest first."),
    batch: bool = typer.Option(False, help="Submit through the Message Batches API (half price)."),
    purpose: str = typer.Option("dev", help="dev, gold, eval, agreement, backfill, new-week."),
    effort: str = typer.Option("high", help="Claude effort: low, medium, high, xhigh, max."),
    version: str | None = typer.Option(None, help="Extractor version (default play/v1)."),
    max_usd: float = typer.Option(
        ..., help="Hard cap in dollars; the run refuses an estimate over it."
    ),
) -> None:
    """Run an extractor over weeks and write rt.mentions (versioned, never overwritten)."""
    from rotation_tracker.mining import run

    with db.connect() as con:
        ids = _pick_weeks(con, weeks, gold, all_, since, skip_done, limit)
        if not ids:
            typer.echo("no weeks to mine")
            return
        if engine == "regex":
            summary = run.mine_regex(con, ids, purpose="baseline", log=typer.echo)
        else:
            spec = run.Spec(
                purpose=purpose,
                effort=effort,
                mode="batch" if batch else "interactive",
                max_usd=max_usd,
                version=version or run.PRODUCTION,
            )
            if batch:
                run.submit_batch(con, spec, ids, log=typer.echo)
                return
            summary = run.mine_interactive(con, spec, ids, log=typer.echo)
    _print_summary(summary)


@mine_app.command("collect")
def mine_collect(run_id: str = typer.Argument(..., help="A batch run's id.")) -> None:
    """Write a finished batch's results (prints the state while it is still processing)."""
    from rotation_tracker.mining import run

    with db.connect() as con:
        summary = run.collect(con, run_id, log=typer.echo)
    if summary is None:
        raise typer.Exit(2)
    _print_summary(summary)


@mine_app.command("resolve")
def mine_resolve(
    all_: bool = typer.Option(
        False, "--all", help="Also re-resolve model-extracted assets that already resolved."
    ),
) -> None:
    """Resolve unknown and ambiguous assets again after editing assets/*.yaml and re-seeding."""
    from rotation_tracker.mining import run

    with db.connect() as con:
        run.reresolve(con, every=all_, log=typer.echo)


@assets_app.command("unknown")
def assets_unknown(limit: int = typer.Option(40, help="Rows to show.")) -> None:
    """The unknown-asset queue: spoken forms no alias or ticker resolved, most frequent first."""
    with db.connect(readonly=True) as con:
        rows = con.execute(
            """SELECT a.spoken, a.kind_guess, a.ticker_guess, count(*) AS n,
                      count(DISTINCT m.video_id) AS weeks
               FROM rt.mention_assets a JOIN rt.mentions m ON m.id = a.mention_id
               JOIN rt.mine_runs r USING (run_id)
               WHERE a.asset_id IS NULL AND r.engine = 'llm'
               GROUP BY 1, 2, 3 ORDER BY n DESC, 1 LIMIT %s""",
            (limit,),
        ).fetchall()
    for spoken, kind, ticker, n, weeks in rows:
        typer.echo(f"{n:4d} {weeks:3d}w  {kind or '-':9s} {ticker or '-':10s} {spoken}")


@gold_app.command("pick")
def gold_pick() -> None:
    """Choose the twelve gold weeks (three per year, fixed seed); a no-op once chosen."""
    from rotation_tracker.mining import gold

    with db.connect() as con:
        for v in gold.pick(con):
            typer.echo(v)


@gold_app.command("second-read")
def gold_second_read(
    effort: str = typer.Option("high", help="Claude effort for the verifier."),
) -> None:
    """Read every rotation mention of the gold pass again, independently (rt.labels)."""
    from rotation_tracker.mining import gold

    with db.connect() as con:
        run_id = gold.gold_run(con)
        if run_id is None:
            raise typer.BadParameter("no finished gold/v1 run: rt mine run --gold --purpose gold")
        gold.second_read(con, run_id, effort=effort, log=typer.echo)


@gold_app.command("sample")
def gold_sample() -> None:
    """Draw the owner's fifty spot-checks from the gold pass (rotation first); fixed once drawn."""
    from rotation_tracker.mining import gold

    with db.connect() as con:
        run_id = gold.gold_run(con)
        if run_id is None:
            raise typer.BadParameter("no finished gold/v1 run")
        typer.echo(f"{gold.sample(con, run_id)} spot-checks queued from {run_id}")


@mine_app.command("eval")
def mine_eval(
    run_id: str | None = typer.Option(
        None, help="The play/v1 run to score (default: newest eval)."
    ),
    agreement: str | None = typer.Option(None, help="A second play/v1 run for run-to-run F1."),
) -> None:
    """Score a run against the gold set; log to MLflow; print the targets met and missed."""
    import json

    from rotation_tracker.mining import evaluate, gold
    from rotation_tracker.mining.resolve import load

    def newest(where: str) -> str | None:
        row = con.execute(
            f"SELECT run_id FROM rt.mine_runs WHERE status = 'done' AND {where} "
            "ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        return row[0] if row else None

    with db.connect() as con:
        gold_run = gold.gold_run(con)
        run_id = run_id or newest("purpose = 'eval' AND extractor_version = 'play/v1'")
        if not (gold_run and run_id):
            raise typer.BadParameter("need a finished gold/v1 run and a play/v1 eval run")
        agreement = agreement or newest("purpose = 'agreement'")
        m = evaluate.evaluate(
            con,
            run_id,
            gold_run,
            load(con),
            baseline_run_id=newest("extractor_version = 'play/v0'"),
            agreement_run_id=agreement,
            log=typer.echo,
        )
    typer.echo(f"run {run_id} against gold {gold_run} ({m['gold']} gold, {m['pred']} predicted)")
    typer.echo(f"{'play':10s} {'P':>6s} {'R':>6s} {'F1':>6s}   v0 P   v0 R")
    for play, sc in m["per_play"].items():
        b = (m.get("baseline") or {}).get("per_play", {}).get(play, {})

        def f(x: object) -> str:
            return f"{x:6.2f}" if isinstance(x, float) else f"{'—':>6s}"

        typer.echo(
            f"{play:10s} {f(sc['precision'])} {f(sc['recall'])} {f(sc['f1'])} "
            f"{f(b.get('precision'))} {f(b.get('recall'))}"
        )
    for k, g in m["gate"].items():  # targets, reported only; `gate` is the stored key
        typer.echo(
            f"target {k:20s} {g['value']!s:8s} {g['bar']:8s} {'met' if g['pass'] else 'MISSED'}"
        )
    missed = sum(not g["pass"] for g in m["gate"].values())
    met = "all met" if m["gate_pass"] else f"{missed} MISSED"
    typer.echo(f"targets {met}; agreement {m.get('agreement')}")
    typer.echo(json.dumps({"confusion": m["play_confusion"], "labels": m["labels"]}))


def _print_summary(summary: dict[str, object]) -> None:
    for k in ("run_id", "extractor_version", "purpose", "weeks_done", "weeks_failed", "mentions",
              "dropped", "dropped_rate", "unknown_rate", "input_tokens", "output_tokens",
              "cache_read_tokens", "usd", "mlflow_run_id"):  # fmt: skip
        if k in summary:
            typer.echo(f"{k:18s} {summary[k]}")


@app.command()
def smoke() -> None:
    """Zero-cost MLflow check: log one kind=smoke run, no network calls, no credits."""
    run_id = tracking.log_run("central-smoke", "smoke", {"note": "no-cost smoke"}, {"ok": 1.0})
    typer.echo(f"run_id {run_id}")


@app.command()
def catalog(
    refresh: bool = typer.Option(False, help="Re-list the tabs instead of using the cache."),
) -> None:
    """① List the channel's Videos, Streams and Shorts tabs (free)."""
    with db.connect() as con:
        typer.echo(pipeline.catalog(con, refresh=refresh))


@app.command()
def refine(
    workers: int = typer.Option(2, help="Parallel lookups; YouTube bot-checks above a few."),
    seed: Path | None = typer.Option(None, help="Seed the cache with the s00 lookups first."),
) -> None:
    """② Exact publish times for the Videos tab back to the first week in scope (free)."""
    if seed:
        typer.echo(f"seeded {youtube.seed_from(seed)} records from {seed}")
    with db.connect() as con:
        typer.echo(pipeline.refine(con, workers=workers, log=typer.echo))


@app.command()
def pick() -> None:
    """③ One video per trading week (pick/v1)."""
    with db.connect() as con:
        picks = pipeline.pick(con, log=typer.echo)
    weekend = sum(p.reason == "weekend" for p in picks)
    if picks:
        typer.echo(
            f"{len(picks)} picks, {weekend} weekend, {len(picks) - weekend} fallback, "
            f"{picks[0].week_friday} → {picks[-1].week_friday}"
        )
    else:
        typer.echo("0 picks")


@app.command()
def ingest(
    limit: int | None = typer.Option(None, help="At most this many videos (e.g. 8 for the pilot)."),
    max_credits: int = typer.Option(..., help="Hard cap on videos sent to Supadata in this run."),
    workers: int = typer.Option(
        1, help="Keep at 1: parallel index-rag runs collide in transcript·lab's Chroma store."
    ),
) -> None:
    """④ Fetch transcripts for pending picks through transcript·lab (1 Supadata credit each)."""
    with db.connect() as con:
        res = pipeline.ingest(
            con, limit=limit, max_credits=max_credits, workers=workers, log=typer.echo
        )
    metrics = {
        k: float(res[k])
        for k in ("attempted", "indexed", "credits_before", "credits_after", "credits_spent")
    }
    metrics["failed"] = float(len(res["failed"]))
    run_id = tracking.log_run(
        f"ingest-{res['batch_id']}",
        "ingest",
        {
            "limit": limit,
            "max_credits": max_credits,
            "workers": workers,
            "batch_id": res["batch_id"],
        },
        metrics,
    )
    typer.echo({**res, "mlflow_run_id": run_id})


@app.command()
def sync() -> None:
    """⑤ Copy transcripts from transcript·lab into rt.transcripts and cut them at chapters."""
    with db.connect() as con:
        res = pipeline.sync(con, log=typer.echo)
    if res["skipped"]:
        raise typer.Exit(1)


@app.command()
def credits() -> None:
    """Supadata credits left per key (free call)."""
    for b in supadata.balances():
        typer.echo(f"key {b.n}: {b.plan:16s} {b.left:4d} left of {b.max_credits}")


@app.command()
def serve(
    port: int = typer.Option(8089, help="Port on 127.0.0.1."),
    reload: bool = typer.Option(False, help="Reload on code changes (development)."),
    label: bool = typer.Option(
        False, help="Turn on the one write path: your spot-checks of gold mentions (rt.labels)."
    ),
) -> None:
    """The viewer: a read-only API, and the UI once `npm run build` has run in frontend/."""
    import os

    import uvicorn

    if label:
        os.environ["RT_LABEL"] = "1"  # read by create_app, also in a --reload worker

    uvicorn.run(
        "rotation_tracker.serving.app:create_app",
        factory=True,
        host="127.0.0.1",
        port=port,
        reload=reload,
    )


@app.command()
def status() -> None:
    """The funnel: listed → dated → picked → ingested → synced."""
    from rotation_tracker.serving import mining

    with db.connect(readonly=True) as con:
        for k, v in pipeline.status(con).items():
            typer.echo(f"{k:15s} {v}")
        cov = mining.summary(con)["coverage"]
    typer.echo(f"{'credits_left':15s} {supadata.credits_left()}")
    unknown = f"{cov['unknown'] / cov['assets']:.1%}" if cov["assets"] else "-"
    typer.echo(f"{'mined':15s} {cov['mined']} of {cov['weeks']} weeks (play/v1, today's prompt)")
    typer.echo(f"{'mentions':15s} {cov['mentions']}, unknown assets {unknown}")
    typer.echo(f"{'chroma':15s} {settings().transcript_lab_chroma}")
