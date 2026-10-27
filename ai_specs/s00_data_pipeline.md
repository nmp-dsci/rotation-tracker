# s00 · Data pipeline: weekly FX Evolution wraps, 2023 onwards

Plan of record for the `data-pipeline` branch. The reviewable page with the evidence
(charts, sampled weeks, budget) is `.lavish/s00_data-pipeline-plan.html`.

## Decisions (27 Oct 2026)

| Question | Decision |
|---|---|
| Source | FX Evolution – Trading Academy, `@fxevolutionvideo`, channel `UCvJZEG5x-DVYZKTz--pS39w` |
| One video per week | `pick/v1`: the last Videos-tab upload before Monday's 09:30 New York open, tagged `weekend` (after Friday's 16:00 close) or `fallback` |
| Depth | 2023 onwards: weeks from the one ending Fri 6 Jan 2023, newest first. Nothing earlier |
| Focus | Macro and flows. Transcripts are cut at chapters and tagged by `topic/v1`; rotation work reads `macro-flows` and `untagged` sections |
| Transcripts | Supadata only, through transcript-rag-agent `index-rag --metadata-json` (1 credit per video). Its Chroma store stays the source of truth; this repo copies read-only |
| Storage | Central Postgres, database `rotation`, schema `rt`, roles `rotation_owner` / `rotation_ro` (registry P9) |
| Prices (next) | Copy value-invest-agent's yfinance loader into this repo |
| Daily videos | Weekly only. Dailies are listed and dated so the pick rule can run; no daily chapters or transcripts |

## Why the pick rule

Measured on 480 exact publish times (s00 analysis, `.rt/seed/`): 85% of uploads land
19:00–02:00 New York time, i.e. the next morning in Australia, so each video recaps the
session that just closed. In 84 of 97 fully sampled weeks exactly one upload falls between
Friday's close and Monday's open, and its chapters open with "Market week overview". The
other 13 weeks fall back to the Thursday or Friday recap. The weekly technical series
"Buy Now, Wait or Sell The Stock Market This Week?" runs to 6 Jan 2023, which is why the
scope starts there.

## Commands

| Step | Command | Writes | Cost |
|---|---|---|---|
| ① catalog | `rt catalog` | `rt.videos` (all three tabs) | free |
| ② refine | `rt refine --seed .rt/seed/exact_sample.json` | `rt.videos.published_at` back to the first week | free; stops on a bot-check, re-run resumes |
| ③ pick | `rt pick` | `rt.weekly_picks` | free |
| ④ ingest | `rt ingest --limit 8 --max-credits 8` (pilot), then `rt ingest --max-credits 205` | transcript·lab Chroma, `rt.ingest_log`, an MLflow run | 1 Supadata credit per video |
| ⑤ sync | `rt sync` | `rt.transcripts`, `rt.chapters`, `rt.transcript_chapters` | free |
| status | `rt status`, `rt credits` | — | free |

## Guards

- Every yt-dlp lookup is cached in `.rt/ytdlp/`; a bot-check stops the run, not the cache.
- `index-rag` runs with `YT_AGENT_SUMMARY_SOURCE=description`, so no LLM is called.
- Credits are read from Supadata `GET /v1/me` before and after each ingest batch.
- Nothing scraped is committed: `.rt/` and `.env` are gitignored.

## Known side effects in transcript-rag-agent

Each `index-rag` run logs to transcript·lab's own MLflow store and rewrites its
`dashboard/rag_pipeline.html` and `dashboard/chunk_space/*.json`. Both are that repo's
behaviour; this repo never writes to its Chroma store directly.

## Backfill result (27 Oct 2026)

| | |
|---|---|
| Weeks | 199 picks, 6 Jan 2023 → 23 Oct 2026, no empty week (182 `weekend`, 17 `fallback`) |
| Ingest | pilot 8 + backfill 191, all indexed, none failed; one at a time, about 35 s each |
| Credits | 199 spent (452 → 253). Key 1 has 53 left; keys 2 and 3 are untouched |
| Transcripts | 199 in `rt.transcripts`, 13k–43k characters (mean about 30k) |
| Sections | 2,999: 2,562 `macro-flows`, 349 `technicals`, 44 `intro-outro`, 27 `promo`, 17 `untagged` (videos with no chapters: 7 in 2023, 3 in 2024, 1 in 2025, 6 in 2026) |
| First look | "rotation/rotating/rotate" appears in macro and untagged sections of 118 of 199 videos |
| MLflow | experiment `rotation-tracker/ingest`, run `ingest-20261027T062432Z-cf8401` |

Run two ingest workers at once and Chroma fails with "Error finding id" (it happened once in
the pilot, and the transcript was still stored). That is why `--workers` defaults to 1.
A new week costs 1 credit: `rt catalog --refresh && rt refine && rt pick && rt ingest --max-credits 1 && rt sync`.
