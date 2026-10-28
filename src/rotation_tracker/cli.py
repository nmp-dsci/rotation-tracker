"""``rt``: the rotation-tracker command line."""

from __future__ import annotations

from pathlib import Path

import typer

from rotation_tracker import db, pipeline, supadata, tracking, youtube
from rotation_tracker.config import settings

app = typer.Typer(no_args_is_help=True, add_completion=False)
db_app = typer.Typer(no_args_is_help=True)
app.add_typer(db_app, name="db", help="Schema and connectivity.")


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
) -> None:
    """The viewer: a read-only API, and the UI once `npm run build` has run in frontend/."""
    import uvicorn

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
    with db.connect(readonly=True) as con:
        for k, v in pipeline.status(con).items():
            typer.echo(f"{k:15s} {v}")
    typer.echo(f"{'credits_left':15s} {supadata.credits_left()}")
    typer.echo(f"{'chroma':15s} {settings().transcript_lab_chroma}")
