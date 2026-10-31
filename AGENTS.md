# AGENTS.md — rotation-tracker

## One instruction file

This is the only agent-instruction file in the repo. Every coding agent and
harness reads this file and nothing else. Do not create tool-specific
instruction files, copies or variants. If a harness does not load `AGENTS.md`
on its own, point it at this file; never fork the content. Subdirectories may
add their own `AGENTS.md` for module-specific rules, and the nearest one wins.

## What this is

A pipeline that reads YouTube market-commentary transcripts, extracts dated
**rotation calls** (capital said to be moving out of one sector, industry,
style, theme or stock and into another), and tests whether names sold down by
a rotation rebound when it ends. Four stages: **extract → signal → backtest →
listener**. `README.md` has the thesis and the roadmap.

**Status: M2, extraction (s02); every week is backfilled (199/199, no gate). s03, prices, on
branch `prices`.** Source: FX Evolution's weekly market wrap, 2023 onwards, one video per week
(`pick/v1`). Read `ai_specs/s00_data_pipeline.md` before changing ingestion,
`ai_specs/s01_viewer.md` before changing the viewer, `ai_specs/s02_text_mining.md`
before changing the miner, its prompt or the asset map, and `ai_specs/s03_prices.md` before
changing `assets/proxies.yaml`, `assets/components.yaml`, the fdw or anything that reads prices.

## Vocabulary

| Term | Meaning |
|---|---|
| **T0** | the video's publish time; the moment a call becomes known |
| **rotation call** | one claim from one video: `out` side, `in` side (either may be empty), stated driver, horizon if given, verbatim quote, transcript timestamp |
| **category** | a node in the versioned taxonomy: sector, industry, style/factor, theme, or a single ticker. Each has a tradable proxy (ETF or basket) |
| **rotated-out candidate** | a category or ticker named on the `out` side that has also fallen meaningfully against its benchmark |
| **rotation end** | the narrative turns (sources start saying money is coming back) or price confirms it (relative strength turns up). These are tracked separately and never merged into one flag |
| **control** | what a result is measured against: benchmark, same-drawdown-no-narrative match, short-term reversal, industry momentum |

## Hard rules

1. **Point in time.** Every input to a signal is read as of T0: prices,
   constituents, earlier calls. Nothing dated after T0 may reach a signal or a
   backtest entry. A video published after the close trades at the next open.
   Keep a test that proves this for each data source.
2. **Extract what was said, not what happened.** Models know market history.
   The extractor records the speaker's claim with a verbatim quote and a
   timestamp, and is never asked whether a rotation played out, what a price did
   later, or what it "thinks". Calls without a quote are dropped.
3. **Fixed taxonomy.** Free-text categories are not signals. Every call
   resolves to a node in a versioned taxonomy file. Unresolvable calls are
   kept, flagged, and counted, never silently mapped to the nearest node.
4. **Results only against controls.** A backtest number is reported next to
   every control in the vocabulary table, net of costs, at several horizons. No
   edge is a result: report it and keep it.
5. **Sealed holdout.** A holdout date is fixed in the first backtest spec.
   Nothing after it is evaluated until the strategy is frozen and written
   down. Do not tune on it, peek at it, or move it.
6. **Survivorship.** Use constituents as of T0 where the data allows. Where it
   does not, flag the result as survivorship-exposed rather than leaving it
   unsaid.
7. **Watchlist, never orders.** The listener produces a watchlist and flags.
   No broker integration or order placement without an explicit, written
   decision in `ai_specs/`.
8. **Public repo hygiene.** Never commit keys, `.env`, raw transcripts, vendor
   price data or caches. Committed: code, the channel list, the taxonomy,
   derived labels, and small hand-labelled fixtures with short attributed
   quotes.

## Workflow

- `main` holds reviewed work only. Branch for every change, merge by pull
  request.
- Conventional commits: `feat(extract): …`, `fix(backtest): …`, `docs: …`.
- Every milestone starts with a spec, `ai_specs/sNN_<topic>.md`, holding the
  decisions and the reasoning behind them. Read the latest spec before a
  change that touches its area.
- Review artifacts (plans, result pages) go in `.lavish/sNN_<topic>.html`.
  `.lavish/` is never gitignored.
- Update `README.md` whenever commands, setup or behaviour change.

## Conventions

- Python with `uv` for everything (`uv sync`, `uv add`, `uv run`). No raw `pip`.
- `ruff format .` and `ruff check . --fix`; mypy strict.
- pytest under `tests/`. Tests are deterministic and offline: mock every model,
  YouTube and price call, and use small committed fixtures.
- Every model call goes through one module, so model choice, caching, cost and
  tracing live in one place.
- Cache every paid or rate-limited fetch on disk, keyed so a re-run costs
  nothing.
- Secrets come from the environment (`./.env`, then `~/.env`), never from code
  or config files.
- The viewer (`frontend/`, React + Vite) is styled only by the house UI in
  `.lavish/` (`house.css`, `project.css`, `fonts/`). No colour literal, no `--hue`
  and no font size under `--t-2` in `frontend/src`: `npm run lint:design` fails on
  them. Its API (`rt serve`) binds to 127.0.0.1 and is read-only, with one exception:
  `POST /api/labels` (the owner's gold spot-checks), off unless `rt serve --label`.
  Frontend tests use synthetic fixtures, never corpus text.
- Every Claude call goes through `mining/extract.py`; every paid command takes `--max-usd`
  and refuses an estimate over it. Thinking tokens bill as output: size `max_tokens` for
  the effort (s02 lessons).
- Changing `mining/prompt.md` changes `prompt_sha`; re-run the gold pass, the second read
  and `rt mine eval` to measure it against the targets before trusting runs made with it. The
  targets are reported, not a gate: nothing waits on them.
- **Prices (s03): this repo never fetches a price.** The sibling `../market-getdata` loads them
  into database `market`; `rt db migrate` imports its `staging` schema here as `market_staging`
  over postgres_fdw, and the viewer reads it as `rotation_ro`. What prices an asset is
  `assets/proxies.yaml` (proxies/v2): typed series keys `yahoo:<SYMBOL>` (Yahoo spelling),
  `fred:<ID>`, `basket:<id>`, or `none` with a reason; one primary per asset, any companions. A
  listed stock or fund defaults to its own ticker. Every curated asset in `themes.yaml` needs a
  row there (`rt assets seed` refuses otherwise). After editing it: `rt assets seed`,
  `rt assets check-proxies`, `rt assets export-symbols` (which writes the instrument list into
  `../market-getdata/instruments/rotation-tracker.txt`; commit it in that repo, nothing else).
- The viewer must boot with `market_staging` absent or empty: a notice, never a 500. Chart price
  strips sit under the mention lines on the same x scale with their own y scale (never a second
  axis on a plot); the price is neutral ink (`--ink`) with a tinted area, because this project's hue sits next
  to the bearish red. Green and red mean stance and nothing else.

## Shared platform

In the `nmp-ai-portfolio` workspace this repo uses the shared services in
`../nmp-central-ai`. Read `../nmp-central-ai/PLATFORM.md` before touching
tracking, storage or deployment.

- **MLflow** via `MLFLOW_TRACKING_URI` only. Never start a local server or fall
  back to a `sqlite:` or `file:` store. Experiments are named
  `rotation-tracker/<purpose>` (e.g. `rotation-tracker/extract`,
  `rotation-tracker/backtest`). Never hardcode an experiment id.
- **Onboarded as P11** in `../nmp-central-ai/registry/projects.yaml`. Smokes:
  `uv run rt smoke` (MLflow) and `uv run rt db smoke` (Postgres). Check with
  `make -C ../nmp-central-ai check ARGS="--only P11"`.
- **Postgres** is database `rotation`, schema `rt`. `rotation_owner` runs the
  pipeline, `rotation_ro` is for analysis, and the superuser URL is for
  `rt db migrate` only. URLs come from `../nmp-central-ai/.db-urls.env` into `.env`.
  Never add a database service to this repo.
- **market_staging** (s03) holds only foreign tables over postgres_fdw: server `market`, one user
  mapping `FOR PUBLIC` as the read-only `market_ro`, `IMPORT FOREIGN SCHEMA staging`. `rt db
  migrate` drops and re-imports it each run (`market/fdw.py`), with values from `MARKET_FDW_HOST`,
  `_PORT`, `_DBNAME`, `MARKET_RO_USER`, `_PASSWORD` in `.env`; it skips with a notice when they are
  unset, when `market` is unreachable or has no `staging` yet. No password goes in a SQL file.
  `localhost` is the container's own loopback, which pg_hba trusts, so the mapping sets
  `password_required 'false'` there (superuser-only; it maps to the read-only role). Never write
  to `market`, and never build anything in `market_staging`: it is re-created by every migrate.
- **Transcripts** come from Supadata through transcript·lab's
  `index-rag --metadata-json` (1 credit each). Never call its HTTP ingest endpoints
  or `bulk-index` (2–3 credits each), and never write to its Chroma store.
- Outside the workspace, point `MLFLOW_TRACKING_URI` at any MLflow 3 server.

## Prior art in the workspace

Reuse before rebuilding. Decide per item, in the M1 spec, whether to depend on
it, copy it, or write it fresh.

- **`../transcript-rag-agent`** (transcript·lab): YouTube transcript fetch with
  a disk cache, channel catalog and polling design (`channels.yaml`), chunking
  and retrieval.
- **`../value-invest-agent`**: the closest relative. Dated stock calls extracted
  from a YouTube channel, yfinance loaders, point-in-time `as_of` reads,
  forward-return validation against a benchmark, a hand-labelled seed set with
  an extractor-vs-critic agreement check.
- **`../ConvFinQA-agent`**: the single model-call module pattern and MLflow
  tracking helpers.

## Layout

```text
src/rotation_tracker/
  config.py          settings; reads ~/.env then ./.env, exports nothing
  db.py              connections; `rt db migrate` applies sql/*.sql as the superuser, then
                     imports market_staging over postgres_fdw (market/fdw.py)
  youtube.py         yt-dlp: tab listings, per-video publish time + chapters, cached in .rt/ytdlp/
  pick.py            pick/v1, the weekly pick rule (pure, tested)
  transcript_lab.py  index-rag subprocess + chromadb client on raw_transcripts (ingest, sync)
  supadata.py        credit balance (GET /v1/me, free)
  topics.py          topic/v1 chapter tags and the cut of a transcript at its chapters
  pipeline.py        catalog → refine → pick → ingest → sync, status
  tracking.py        MLflow runs (experiments rotation-tracker/ingest and /mining)
  mining/            s02: universe.py (assets/v1 seed), resolve.py (alias → asset), corpus.py
                     (a week as read), prompt.md + schema.py (play/v1), extract.py (every Claude
                     call), locate.py (the provenance gate), baseline.py (play/v0), run.py
                     (rt mine), gold.py (gold set, second read, spot-checks), evaluate.py
  market/            s03, prices read from market-getdata: proxies.py (proxies/v2: resolve, seed
                     rt.asset_proxies, check, the export), components.py (components/v1: a
                     category's GICS list and his names), fdw.py (market_staging), prices.py (the
                     viewer's reads of market_staging and the chart's price lines)
  serving/           the viewer's API (`rt serve`): app.py routes, store.py
                     reads, chroma.py Chroma's SQLite read with mode=ro (no chromadb client), themes.py the chart's keyword themes (themes/v0, not signals; each pinned to an asset from s03), mining.py the miner's reads and the one label write
  cli.py             `rt`
frontend/            the viewer: React + Vite on the house UI, design lint, vitest
sql/                 001_rt.sql: schema rt; 002_mining.sql: assets, aliases, runs, mentions,
                     labels, evals; 003_proxies.sql: rt.asset_proxies. Idempotent
assets/              themes.yaml (curated layers, aliases), extras.yaml (stock nicknames,
                     mishearings, names that need a ticker cue), proxies.yaml (proxies/v2: the
                     series that price each asset), components.yaml (GICS → category)
tests/               pick rule, topic tags, chapter cut, viewer API, the miner, prices (offline,
                     a fake market; no Postgres)
ai_specs/            sNN_*.md specs, the plan of record
.lavish/             house.css, project.css (hue 15) and fonts from nmp-central-ai;
                     review artifacts
showcase.yaml        what a portfolio-site build of the viewer may freeze, and what it may not
.rt/                 caches and seed data, gitignored
```

Still to come, per the roadmap: the measurement of calls against prices (the branch after s03),
`signal/`, `backtest/`, `listener/`.

## Open decisions

- s03: the rotation entry in `../nmp-central-ai/registry/projects.yaml` declaring
  `extensions: [postgres_fdw]` (provisioned on the platform branch `feat/registry-p12-market`).
- s03: `rt.assets.proxy` is the primary's bare Yahoo symbol, so it is empty where a FRED series or
  a basket is the primary (e.g. `rates:us10y`, which was `^TNX`); read `rt.asset_proxies` instead.

- Drawdown threshold, horizons, cost model and holdout date for the backtest.
- s02: committing the branch and opening its pull request.
- s02: adding experiment `rotation-tracker/mining` to P11 in
  `../nmp-central-ai/registry/projects.yaml` (it lists only `rotation-tracker/ingest`).
- Decided 28 Oct 2026: the rotation definition stays strict (prompt `3ab4d33`), to improve
  later; every remaining week was backfilled at effort `high`, without a gate, and is done.
