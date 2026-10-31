# s03 · A price for everything he talks about

Every asset the miner found gets a price series, at the category level (Software → IGV) and one
level down (the names inside Software). The prices are fetched by a new sibling repo,
`market-getdata`, into its own database `market` on the central Postgres. This repo reads them
over `postgres_fdw` and never fetches a price itself. Measuring the calls against the prices is
the next branch; this one makes sure every price is there and joinable.

Plan reviewed in `.lavish/s03_price-pipeline-plan.html` (31 Oct 2026). Delivery walked through in
`.lavish/s04_price-pipeline-delivery.html`.

## Decisions (31 Oct 2026)

| Question | Decision |
|---|---|
| Home | A: a new sibling repo `market-getdata`, **the same setup as `propertyiq_getdata`** (owner's note), database `market`, roles `market_owner` / `market_ro`, registry P12. Consumers import `staging` over `postgres_fdw` as `market_staging` |
| Universe | Every proxy and companion series, every S&P 500 and Nasdaq-100 constituent, and every stock or ETF he has named: about 750 symbols |
| History | Proxies, indexes, ETFs, basket members and FRED series from their first available date; individual stocks (constituents and named) from 2015-01-01. The owner asked whether 2015 for everything was better; the split stands because the pre-2015 regimes (2000–02, 2008, 2020) exist only in the proxies and cost ≈ 450k rows, and extending a start date later is one backfill run |
| Fills | The 23 unpriced assets filled as proposed: `yahoo:`, `fred:` and `basket:` series, five explicit `none` (tariffs, geopolitics, earnings, debt, stablecoins) |
| Cadence | **Weekly, Saturday 09:00 Sydney** (owner's choice over the daily recommendation), launchd on the owner's Mac. The US Friday close is in by 07:00–08:00 Sydney; the wrap itself publishes on Sunday afternoon Sydney time, so the week it discusses is already loaded. Constituents refresh in the same run |
| Components | GICS sub-industry plus the names he says, now; issuer ETF holdings in phase 2 |

## The contract between the two repos

### Series keys

A price series is named by a typed key, the same string in both repos:

| Key | Meaning | Value used for charts and returns |
|---|---|---|
| `yahoo:<SYMBOL>` | a Yahoo Finance symbol, Yahoo spelling (`BRK-B`, `^VIX`, `BTC-USD`, `CL=F`, `DX-Y.NYB`) | `adj_close` |
| `fred:<SERIES_ID>` | a FRED series, latest vintage | `value` (a level: a yield, a spread, an index) |
| `basket:<id>` | an equal-weight basket defined in `market-getdata/baskets.yaml` | `value`, rebased to 100 |
| `none` | deliberately unpriced; the reason is in `assets/proxies.yaml` | — |

### What rotation-tracker hands over

`rt assets export-symbols` writes `market-getdata/instruments/rotation-tracker.txt`, committed in
that repo, so the feed never imports tracker code or reads the `rotation` database. One line per
series, tab-separated, `#` comments and blank lines ignored:

```
<typed key>\t<kind>\t<reasons>
yahoo:SMH	fund	proxy
yahoo:NVDA	stock	named,companion
fred:DGS10	rates	proxy
basket:defensives	basket	proxy
```

`kind` is the `rt.assets` kind (`stock`, `fund`, `index`, `sector`, `theme`, `rates`, `credit`,
`commodity`, `fx`, `crypto`, `macro`) or `basket` / `fred` where the series has no asset of its
own. `reasons` is a comma list from `proxy` (a primary series of some asset), `companion`,
`named` (a stock or ETF he names in at least one mention). Constituents are not in the file: the
feed fetches the two index lists itself.

### What market-getdata serves

Database `market`, schema `staging`, dbt tables (not views), readable by `market_ro`:

| Table | Grain | Columns |
|---|---|---|
| `instruments` | one row per series key | `series` (typed key, unique), `source` (`yahoo`\|`fred`\|`basket`), `symbol` (the bare symbol or id), `name`, `type` (`stock`\|`etf`\|`index`\|`future`\|`fx`\|`crypto`\|`fred`\|`basket`), `currency`, `first_date`, `last_date`, `reasons` (text[]: `proxy`, `companion`, `named`, `constituent`, `basket_member`), `history_from` (the start the fetch asked for) |
| `prices_daily` | Yahoo symbol × trading day | `symbol`, `date`, `open`, `high`, `low`, `close`, `adj_close`, `volume`; unadjusted and adjusted closes both kept |
| `actions` | Yahoo symbol × event day | `symbol`, `date`, `dividend`, `split_ratio` |
| `series_daily` | FRED series × observation | `series_id`, `date`, `value`, `freq` (`d`\|`w`\|`m`), `asof`; the latest vintage |
| `series_vintages` | FRED series × observation × vintage | the same, every `asof` kept |
| `baskets` | basket × member | `basket_id`, `symbol`, `weight`, `from_date`, `to_date` |
| `basket_prices_daily` | basket × trading day | `basket_id`, `date`, `value` |
| `constituents` | index × symbol × snapshot | `index_id` (`spx`\|`ndx`), `symbol` (Yahoo spelling), `name`, `gics_sector`, `gics_sub_industry`, `date_added`, `snapshot_date` |
| `series_values` | series key × date | `series`, `date`, `value`, `close` (raw close for Yahoo, null otherwise). The one table a consumer needs for a chart: Yahoo → `adj_close`, FRED → `value`, basket → `value` |

`meta.load_state` and `meta.pipeline_runs` as in propertyiq. `raw` is never readable by `market_ro`.

### How rotation-tracker reads it

`rt db migrate` creates, in database `rotation`, as the superuser: a foreign server `market`
(`postgres_fdw`, `fetch_size 10000`), a user mapping `FOR PUBLIC` as `market_ro`, schema
`market_staging`, and `IMPORT FOREIGN SCHEMA staging FROM SERVER market INTO market_staging`.
Connection values come from the environment, never from code: `MARKET_FDW_HOST` (default
`localhost`; `postgres` from a compose stack), `MARKET_FDW_PORT` (5432), `MARKET_FDW_DBNAME`
(`market`), `MARKET_RO_USER` (`market_ro`), `MARKET_RO_PASSWORD` (default = the user). When the
variables are absent the step is skipped with a notice, and the viewer runs without prices.

`rt.asset_proxies` (`sql/003_proxies.sql`), written by `rt assets seed` from `assets/proxies.yaml`:
`asset_id`, `series` (typed key or `none`), `role` (`primary`\|`companion`), `from_date`,
`to_date`, `note`. One primary per asset. The old `rt.assets.proxy` column stays as the primary's
bare Yahoo symbol for compatibility.

## Baskets

Equal weight, rebalanced monthly, total return through `adj_close`, rebased to 100 on the first
day any member has a price. A member joins at the first month start after its history begins.

| Basket | Members |
|---|---|
| `defensives` | XLP, XLU, XLV |
| `cyclicals` | XLI, XLB, XLY, XLF, XLE |
| `mag7` | AAPL, MSFT, GOOGL, AMZN, META, NVDA, TSLA |
| `crypto` | BTC-USD, ETH-USD |
| `alts` | ETH-USD, SOL-USD, XRP-USD, ADA-USD, DOGE-USD |
| `hardware` | today's S&P 500 members in GICS "Technology Hardware, Storage & Peripherals" (survivorship noted) |
| `meme` | GME, AMC |

## History rule

`history_from` is the earliest available date (`period="max"`) for everything except a common
stock whose only reasons are `constituent` and/or `named`; those start at 2015-01-01. A stock that
is also a `proxy`, `companion` or `basket_member` gets its full history.

## Schedule

`market-getdata/scripts/update.sh` (fetch all sources, `db update`, `audit`) runs from
`~/Library/LaunchAgents/com.nmp-dsci.market-update.plist`, Saturday 09:00 local time, logs under
`~/.market/`. `scripts/install-launchd.sh` writes and loads it; `--uninstall` removes it. A run on
a day with nothing new exits clean. launchd runs a missed Saturday job once on wake.

## Out of scope

Measuring calls against prices (the next branch). Issuer ETF holdings, constituent change
history, net liquidity, CoinGecko totals (phase 2 in market-getdata). Miner validation (deferred
by the owner, 30 Oct 2026).
