# s01 · The viewer: a local site over what M1 built

A browser view of the corpus and the pipeline, so the work to date can be seen rather than
queried. It reads what M1 wrote and writes nothing.

## Decisions (27 Oct 2026)

| Question | Decision |
|---|---|
| Look | The Lovable "Sonora" musician template: full-bleed imagery under a scrim, very large uppercase type set tight, pill buttons, a transparent header over the hero, cover grids, numbered tracklists, a ranked chart with NEW and up/down marks, a slide-out menu, an oversized footer wordmark |
| Design system | The portfolio house UI (nmp-central-ai D25–D32): `.lavish/house.css`, `fonts/` (IBM Plex) and `project.css`. The template's look is layout, type and imagery only; every colour is a house token |
| Hue | 15, provisional and hand-written in `.lavish/project.css`. No hue is left 30° clear of the other ten projects, and 15 is P9 finance-rag-sft's; the owner chose to share it to keep the warm blush (28 Oct 2026), so registry P11 has no `ui:` block until the separation rule (D8) settles. It sits near the status red, so every status in the viewer carries a word and a glyph |
| Theme | Dark first, as the template is; light is one click away and remembered per browser |
| Stack | As the sibling viewers (tau-telecom-sft, finance-rag-sft): React 18 + Vite + react-router, a FastAPI API serving the built SPA from the same origin, `SHOWCASE_BASE` for a portfolio-site build, `design_lint.mjs`, vitest |
| Ports | API `127.0.0.1:8089` (`rt serve`), UI dev server `127.0.0.1:5178`. Neither is used by another project |
| Data | Postgres `rt.*` as `rotation_ro`; transcript·lab's Chroma (`raw_transcripts`, `transcript_chunks`) read from its `chroma.sqlite3` with `mode=ro`, not through the chromadb client (see below); MLflow for run links and the ingest runs' metrics; Supadata `GET /v1/me` for the balance (never a key) |
| Chroma access (28 Oct 2026) | The viewer needs documents and metadata, never vectors. chromadb's client loads a collection's HNSW index on first read and replays any log it is behind on; when another writer left `transcript_chunks`' index 134 writes behind, every read crashed the process (SIGBUS/SIGSEGV), which Python cannot catch. SQLite holds every document and metadata value, current with the log, so `serving/chroma.py` reads it read-only: no index, no writes, errors are exceptions. The schema is chromadb 1.5.9's, pinned in pyproject; `tests/test_chroma.py` checks the reader against a store that version writes |
| Imagery | YouTube thumbnails from `i.ytimg.com`, linked, never stored. Toned to the hue until hovered |
| The chart | `themes/v0`: 18 fixed keyword themes, ranked by mentions per weekly wrap over the macro-and-flows and no-chapters sections, by quarter. Labelled on the page as not a signal. Weeks-mentioned was tried first and saturates (most themes come up in 13 of 13 wraps) |

## Pages

| Path | Template idea | Shows |
|---|---|---|
| `/` | editorial home | a tilted wall of the latest 120 covers behind the headline, corpus figures, the latest 8 wraps, the chart's top 5, the pipeline stages |
| `/weeks` | discography | all 199 picks by year, filter by year, weekend or fallback, title |
| `/weeks/:id` | album page | the video, its pick, its chapters as a tracklist that opens into timed paragraphs (each timestamp plays YouTube from there), Chroma's chunks, and where every part is stored |
| `/search` | — | Postgres full-text search over the sections, matches marked, weeks per quarter that mention the query |
| `/chart` | chart rankings | the quarterly theme chart with moves, sparklines and what fell off |
| `/pipeline` | liner notes | stages and commands, Supadata credits, Postgres tables, Chroma collections, ingest batches, MLflow runs, the upload-time evidence for the pick rule, the decisions table of s00 (read from that file) |

## Guards

- Read-only throughout: `rotation_ro` has read-only transactions; Chroma's SQLite file is opened
  with `mode=ro`, and the viewer never starts a chromadb client.
- 127.0.0.1 only. `showcase.yaml` marks the transcript routes private: a portfolio-site build
  may freeze counts, the chart and the pipeline, never transcript text.
- Frontend tests use synthetic fixtures; no corpus text is committed.
- `npm run lint:design` fails on any colour literal, `--hue` or font size under `--t-2`.
