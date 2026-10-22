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

**Status: M0, docs only.** No code exists yet. Follow the layout below until
real code replaces it, then follow the code.

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

## Shared platform

In the `nmp-ai-portfolio` workspace this repo uses the shared services in
`../nmp-central-ai`. Read `../nmp-central-ai/PLATFORM.md` before touching
tracking, storage or deployment.

- **MLflow** via `MLFLOW_TRACKING_URI` only. Never start a local server or fall
  back to a `sqlite:` or `file:` store. Experiments are named
  `rotation-tracker/<purpose>` (e.g. `rotation-tracker/extract`,
  `rotation-tracker/backtest`). Never hardcode an experiment id.
- **Not yet onboarded.** Before the first tracked run, add this project to
  `../nmp-central-ai/registry/projects.yaml` and follow
  `../nmp-central-ai/docs/onboarding.md` (a zero-cost `smoke` command included).
- **Postgres**, if the project needs it, is one database on the shared server,
  declared in the registry. Never add a database service to this repo.
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

## Expected layout

Guidance until code exists:

```text
channels.yaml        the sources followed; committed because the choice is worth reviewing in a diff
taxonomy/            versioned category tree with a proxy per node
src/rotation_tracker/
  config.py          settings; reads ./.env then ~/.env
  llm.py             the one module every model call goes through
  ingest/            channel catalog, publish times, transcript fetch + cache
  extract/           rotation-call schema, extractor, taxonomy resolution
  market/            prices, constituents, relative strength, drawdown (all as_of)
  signal/            per-category signal series, candidates, rotation-end detection
  backtest/          event study, controls, splits, costs, reports
  listener/          scheduled poll, incremental run, watchlist
  cli.py             one entry point per stage
data/
  seed/              hand-labelled calls for extraction evals
ai_specs/            sNN_*.md specs, the plan of record
.lavish/             review artifacts
tests/
```

## Open decisions (for the M1 spec)

- Transcript source and cost per video; reuse transcript·lab or not.
- Storage: a local DuckDB file or a database on the shared Postgres.
- Model and runtime for extraction, and its billing.
- The channel list and backfill window.
- Taxonomy: which sector, industry, style and theme nodes, and their proxies.
- Drawdown threshold, horizons, cost model and holdout date for the backtest.
