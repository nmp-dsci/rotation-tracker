-- rotation-tracker s03: which price series stands for each asset (ai_specs/s03_prices.md).
-- Applied as the cluster superuser by `rt db migrate`; idempotent. Created as rotation_owner so
-- 001's default privileges give rotation_ro SELECT.
--
-- Written by `rt assets seed` from assets/proxies.yaml (proxies/v2): every asset in rt.assets,
-- one primary each (a typed series, or `none` with its reason in `note`), and any companions.
-- The prices themselves live in database `market` (market-getdata) and are read over
-- postgres_fdw as market_staging, which `rt db migrate` imports after this file; no SQL file
-- holds a connection value or a password.

SET ROLE rotation_owner;

CREATE TABLE IF NOT EXISTS rt.asset_proxies (
  asset_id   text NOT NULL REFERENCES rt.assets ON DELETE CASCADE,
  series     text NOT NULL CHECK (series = 'none' OR series ~ '^(yahoo|fred|basket):[^[:space:]]+$'),
  role       text NOT NULL CHECK (role IN ('primary', 'companion')),
  ord        integer NOT NULL DEFAULT 0,   -- companions in the file's order; the primary is 0
  from_date  date,
  to_date    date,
  note       text,                         -- for `none`, the reason it is unpriced
  PRIMARY KEY (asset_id, series),
  CHECK (series <> 'none' OR (role = 'primary' AND coalesce(note, '') <> '')),
  CHECK (from_date IS NULL OR to_date IS NULL OR from_date <= to_date)
);
CREATE UNIQUE INDEX IF NOT EXISTS asset_proxies_one_primary_idx
  ON rt.asset_proxies (asset_id) WHERE role = 'primary';
CREATE INDEX IF NOT EXISTS asset_proxies_series_idx ON rt.asset_proxies (series);

RESET ROLE;
