# s02 · Mining the weekly wraps for asset calls

Read every weekly wrap for every commentary on price and turn each into a row: on this date, at
this second of the video, he said this about that asset, with this play and this direction.
Rotation first, but not alone. Measuring the calls against prices is the next branch (s03); this
one makes the rows and proves they are right.

Plan reviewed in `.lavish/s01_text-mining-plan.html` (28 Oct 2026); results walked through in
`.lavish/s02_text-mining-results.html`.

## Decisions (28 Oct 2026)

| Question | Decision |
|---|---|
| Scope | Every commentary on price (owner: "extract every commentary on price"): seven plays plus `other` in play/v1 |
| Rotation and price | Rotation in ⇒ bullish, out ⇒ bearish on that asset; a rotation call is tested against price exactly like a bullish or bearish call. Owner's note: check in s03 that rotation in/out lines up with the proxy's price |
| Universe | Every name he mentions, resolved to any US-listed ticker (Nasdaq Trader's symbol directory), no index gate. S&P 500 and Nasdaq-100 membership, date added and GICS are tags, not a filter |
| Model | `claude-opus-5-5` for extraction and eval, adaptive thinking, structured output; the Batch API for the backfill |
| Effort | `high` (owner: "make it high"). The gold pass runs one step deeper, at `xhigh` |
| Unit | One call per week over the macro-flows and untagged sections, each behind a `[§n · start · title]` marker |
| Gold set | 12 weeks, three per year 2023–2026, fixed seed; a careful pass proposes, every rotation mention is read again by an independent call, the owner spot-checks 50 in the viewer |
| Eval targets, not a gate | Rotation precision ≥ 0.85 and recall ≥ 0.80; asset accuracy ≥ 0.90; unknown assets < 10%; dropped quotes < 3%. `rt mine eval` reports them; nothing waits on them. Planned as the gate before the backfill; the owner dropped it on 28 Oct 2026, after the results ("run all the weeks, I don't want any gating, I can always improve it later") |
| Viewer | `/mentions`, `/assets`, `/assets/:id`, the spot-check page `/label`, and `/mining` for the eval and the runs; the chart stays on themes/v0 |

## The mention

| Field | Values |
|---|---|
| play | rotation · flow · valuation · technical · regime · relative · call · other |
| direction | per play: rotation `in`/`out`/`out_in`; flow `buying`/`selling`; valuation `under`/`over`/`fair`; technical `bullish`/`bearish`/`neutral`; regime `risk_on`/`risk_off`/`bull`/`bear`/`neutral`; relative `a_over_b`; call `long`/`short`/`avoid`/`watch`; other `bullish`/`bearish`/`neutral` |
| assets | one or more, each with a role (`subject`, `from`, `to`, `versus`) and the stance it implies for that asset (`from` bearish, `to` bullish, `versus` the opposite of the claim) |
| speaker | `him` or `reported` (with who) |
| modality · horizon · confidence | observed / expected / recommended · days to years or unspecified · 0–1, lowered by hedges |
| provenance | the verbatim quote, its section, character span and `t_seconds`; the run, extractor version, prompt sha and model |

Stance is derived in code from play, direction and role (`mining/schema.py`), never asked of the
model.

## How it runs

```text
rt.transcript_chapters ─► rt mine run (one call per week, prompt cached) ─► locate ─► resolve ─► rt.mentions
                                                                              │          │      rt.mention_assets
                                                         rt.mine_drops ◄──────┘          └─► unknown queue
```

- **Locate** (`mining/locate.py`): a quote is kept only if it is found in the section text,
  exactly after normalising, else fuzzily at ≥ 0.9 over word windows. The span maps to the caption
  segment that holds it, which gives `t_seconds`. A miss is a row in `rt.mine_drops`.
- **Resolve** (`mining/resolve.py`): code, not the model. Curated aliases (`assets/themes.yaml`),
  hand-kept stock aliases and ambiguous names (`assets/extras.yaml`), company names generated
  from the S&P 500 and Nasdaq-100 lists, then the model's ticker guess against every listed
  ticker. A name that is also a word ("target", "apple", "news") resolves only when the ticker
  guess agrees. `rt mine resolve` re-resolves after aliases are added.
- **Versioning**: a run never overwrites another. The viewer and the backfill read the newest
  finished `play/v1` run per week among purposes dev, eval, backfill and new-week.
- **Baseline** play/v0 (`mining/baseline.py`): the seed keywords with a ±12-word window and an
  alias inside it, through the same gates. Free; the bar v1 has to clear.
- **Tracking**: one MLflow run per `rt mine` invocation and per eval in
  `rotation-tracker/mining`: counts, tokens, dollars, metrics. No transcript text.

## The asset map (assets/v1)

| Layer | Rows | Proxy |
|---|---|---|
| index | 6 | SPY QQQ DIA IWM ^VIX RSP |
| GICS sector | 11 | the SPDR sector ETFs |
| theme | 41 | SMH IGV MAGS KBE KRE ITB XBI GDX … ; `null` where no clean proxy exists (AI, defensives, cyclicals) |
| stock and fund | every US-listed common stock, ADR and ETF (≈ 11,700) | the ticker (Yahoo form, `BRK-B`) |
| crypto · rates · credit · commodity · FX · macro | 8 · 4 · 3 · 10 · 8 · 13 | BTC-USD … ^TNX TLT HYG GLD USO DX-Y.NYB …; macro has none |

`rt assets seed` fetches the four public sources at build time (or reads local copies with
`--local`) and records the snapshot date on every row. Assets are upserted, never deleted.

## Measuring the miner

- **Gold**: `rt gold pick` (fixed), `rt mine run --gold --purpose gold --version gold/v1 --effort xhigh --batch`,
  `rt gold second-read`, `rt gold sample`, then the owner's checks at `/label` under `rt serve --label`.
  Owner labels beat the second read; `wrong` removes a gold mention, `fix` replaces its fields.
- **Match**: same section, quote spans overlapping by ≥ 30% of the shorter, same play; one-to-one,
  best overlap first.
- **Metrics** (`rt mine eval`): precision, recall, F1 per play; direction accuracy and asset
  accuracy (identical resolved sets) on matched pairs; unknown and dropped rates; the same for
  v0; run-to-run F1 between two v1 runs on four gold weeks. Stored in `rt.evals`, logged to MLflow.

## Results (28 Oct 2026)

The viewer's `/mining` page reads the same tables live.

| Measure (12 gold weeks, play/v1 prompt `3ab4d33`, effort high) | Value | Target |
|---|---|---|
| Rotation precision · recall | 0.88 · 0.64 (7 of 11 gold calls) | ≥ 0.85 met · ≥ 0.80 **missed** |
| Asset accuracy (identical resolved sets) | 0.94; 0.99 share at least one asset | ≥ 0.90 met |
| Unknown assets · dropped quotes | 0.7% · 0.2% (1 of 558) | < 10% met · < 3% met |
| All plays precision · recall · F1 | 0.89 · 0.75 · 0.81 (play/v0: 0.46 · 0.13) | — |
| Direction right on matched calls | 96% | — |
| Run to run, 4 weeks | F1 0.85 overall, 0.75 on rotation | — |
| Second read of gold rotation calls | 8 of 13 agree (62%) | done-when ≥ 90%, not met |

Three prompts were scored (`1cc2963`: rotation P 0.64 R 0.90; `3ab4d33`: 0.88 / 0.64;
`c415e85`: 0.53 / 0.73). `3ab4d33` is kept: the strict definition stays, to improve later. Only
rotation recall misses its target, and the owner chose to run the backfill without a gate (28 Oct
2026), so the other 187 of 199 weeks were mined at effort high via Batch. Cost: $0.17 a week at
effort high via Batch (15.6k output tokens on average), so ≈ $34 for the corpus, twice the plan's
estimate; $25.86 spent in this branch before the backfill, $7.86 of it on a failed pass at effort
max.

Backfill: run `mine-20261028T080435-ed1c` (Batch `msgbatch_01FXZMNPP4sKHSaHMQxXgW1r`, MLflow run
`d021ef497de94c019ad2569566b06a4e`), 187 weeks submitted, 187 done, 0 failed, about 12 minutes
from submission to the end of the batch. 9,376 mentions kept, 2 dropped; 26–82 a week (average
50.1). Tokens 1,492,739 in, 2,965,458 out (6.7k–27.5k a week, average 15.9k), 1,048,322 cache
read. $32.75 against $36.34 estimated at submission and the plan's ≈ $17 for the corpus; $58.61
spent in all. All 199 weeks are now current, with 9,933 mentions. Triage of the unknown-asset
queue added curated rows and aliases (iron ore, aluminium, the NYSE composite, Tencent, SK Hynix,
Cardano, Trump coin, Japanese yields, Brent, the Fed's terminal rate, "US 500", SpaceX as
`stock:SPCX`) and took unknown references from 1.75% to 1.16%; a resolver fix then stopped index
and futures ticker guesses (`^DJT`, `^MOVE`, `CL=F`) matching same-letter US stocks (26
references), adding curated rows for the Dow Transports and the MOVE index; after the re-resolve,
1.10% (132 of 12,024) are unknown.

## Lessons

- **Thinking is output.** At effort `high` a week used 13k–23k output tokens, not the 7k planned,
  so the corpus costs about twice the plan's estimate. At `max`, every gold week overran a 64k
  `max_tokens` and returned no usable JSON ($7.86 lost); deeper efforts now get 96k–128k.
- **"Rotation" is the channel's word for a sector scoreboard.** The first prompt let a list of
  the day's best and worst sectors pass as rotation; an independent second read agreed with only
  half of the gold rotation calls, and rotation precision was 0.64. The prompt now asks for money
  or leadership moving, with a counter-example; the scoreboard is still extracted, as `other`
  with the same ↑/↓ stance, so nothing is lost for s03. Precision rose to 0.88 and run-to-run
  rotation F1 from 0.59 to 0.75, but the stricter reading missed turns ("a big turnaround for
  small caps against the S&P", "selling defensives for weeks, now buying them again"); a third
  revision names turns as rotation.
- **The rotation boundary is where the uncertainty lives.** Rotation is rare once the scoreboard
  is excluded (about one call a week), so twelve gold weeks hold only a dozen; one call moves
  recall by eight points. The second read and the careful pass disagree on a third of them. The
  gold set informed two prompt revisions, so its numbers lean optimistic: the owner's
  spot-checks are the independent check, and a fresh set of weeks should be labelled before s03
  relies on the rotation play specifically.

## Commands

```bash
uv run rt db migrate                                   # 002_mining.sql
uv run rt assets seed                                  # assets/v1 from the yaml files and the listings
uv run rt mine run --engine regex --all --max-usd 0    # play/v0, free
uv run rt mine run --weeks ID,ID --purpose dev --max-usd 3
uv run rt mine run --all --skip-done --batch --purpose backfill --max-usd 50
uv run rt mine collect RUN_ID                          # write a finished batch
uv run rt mine eval                                    # the targets
uv run rt mine resolve                                 # after adding aliases
uv run rt assets unknown                               # the unknown-asset queue
uv run rt serve --label                                # the viewer, with spot-checks recorded
```

New week: `rt catalog --refresh && rt refine && rt pick && rt ingest --max-credits 1 && rt sync && rt mine run --since <friday> --purpose new-week --max-usd 1`.
