# rotation-tracker

Read what market commentators on YouTube say about money moving between sectors,
turn it into dated, structured rotation calls, and test whether the stocks and
sectors that get sold *because of a rotation* bounce back when the rotation ends.

> **Status: M0, docs only.** This commit holds the README and `AGENTS.md`; there
> is no code yet. The first build happens on a branch off `main`.
>
> Research code, not investment advice. Nothing here places orders.

## The idea

A **rotation** is capital leaving one part of the market for another: megacap
tech into small caps, growth into value, cyclicals into defensives, semis into
software. A stock caught on the wrong side can fall hard with nothing wrong in
its own business. The selling is about flows, not fundamentals, and when the
rotation runs out or reverses, the money can come back.

Market commentators describe these flows as they happen, and they publish on a
date. That gives a dated record of *which* categories were said to be rotating,
*in which direction*, and *why*. This repo turns that record into:

1. **Rotation calls**: a structured, quote-grounded extraction from each
   transcript. What is rotating out, what is rotating in, the stated driver, and
   the tickers or categories named.
2. **A rotation signal**: those calls rolled up over time per category. How
   many sources say it, whether they agree, and when the narrative turns.
3. **A backtest** of the bounce: after a category or stock is named as rotated
   out *and* has fallen meaningfully, what does it return next, and does it beat
   the same drawdown with no rotation story attached?
4. **A listener**: the same pipeline run forward on new videos, producing a
   watchlist of rotated-out names and flagging when a rotation looks to be ending.

### The question the backtest has to answer

Losers bouncing is not new. Short-term reversal says recent losers tend to
recover whatever the reason, and industry momentum says sectors that have been
falling for months tend to keep falling. The question here is narrower:

> **Does knowing a drawdown was rotation-driven predict the rebound better than
> knowing the drawdown happened?**

So every result is reported against controls: the benchmark, a matched set of
names with the same drawdown and no rotation narrative, plain short-term
reversal, and industry momentum. "No edge over the control" is a valid finding
and gets reported like any other.

## How it works

```mermaid
flowchart LR
  subgraph ING["Ingest"]
    CH["channels file<br/>(committed)"] --> CAT["video catalog<br/>+ publish times"]
    CAT --> TR["transcripts"]
  end
  subgraph EXT["Extract"]
    TR --> RC["rotation calls<br/>out → in · driver · quote · timestamp"]
    RC --> RES["resolve to taxonomy<br/>sector · industry · style · theme · ticker"]
  end
  subgraph SIG["Signal"]
    RES --> AGG["per-category signal over time<br/>volume · consensus · narrative turn"]
    PX["prices<br/>(point-in-time)"] --> RS["relative strength<br/>+ drawdown vs benchmark"]
    AGG --> CAND["rotated-out candidates"]
    RS --> CAND
  end
  subgraph USE["Use"]
    CAND --> BT["backtest<br/>forward excess returns vs controls"]
    CAND --> LIS["listener<br/>new videos → watchlist + rotation-end flags"]
  end
```

**Point in time throughout.** A rotation call is dated to the video's publish
time (T0). Prices, constituents and every other input are read *as of* T0, and a
video published after the close becomes tradable at the next open.

## Roadmap

| Milestone | Builds | Done when |
|---|---|---|
| **M0** | README, `AGENTS.md`, public repo | this commit |
| **M1 corpus** | committed channel list, video catalog with exact publish times, transcripts | a backfill of the chosen channels is cataloged and fetched, with a cache so nothing is paid for twice |
| **M2 extraction** | rotation-call schema, taxonomy, extractor, hand-labelled seed set | extraction is scored against the seed set (claim recall and precision, category and ticker resolution accuracy) and every call carries a verbatim quote |
| **M3 signal** | price loader, relative strength and drawdown per category, rotation signal series | the signal for a known historical rotation lines up with what prices did |
| **M4 backtest** | event study with controls, walk-forward splits, sealed holdout | excess returns at several horizons, with costs, reported against every control |
| **M5 listener** | scheduled poll of new videos, incremental extraction, watchlist, rotation-end flags | a new video flows to an updated watchlist with no manual step |

Each milestone starts with a short spec in `ai_specs/` and lands through a pull
request.

## Working on this repo

- **`AGENTS.md` is the one instruction file for coding agents**, whatever the
  harness. Read it before changing anything. There are no tool-specific copies.
- Branch off `main` for every piece of work; merge through a pull request.
- Python, managed with `uv`; Ruff for lint and format; mypy strict; pytest.
- Experiment tracking goes to the shared MLflow server in the parent
  `nmp-ai-portfolio` workspace (`MLFLOW_TRACKING_URI`). Outside that workspace,
  point the variable at any MLflow 3 server.
- Keys live in `.env` (gitignored) or `~/.env`, never in the repo.

## Disclaimer

This is a research project. Nothing in it is a recommendation to buy or sell
any security, and it does not execute trades. Commentary is summarised with
short attributed quotes. Transcripts and vendor price data are not
redistributed here.

## License

MIT. See [`LICENSE`](LICENSE).
