-- rotation-tracker s02: mining the weekly wraps for asset calls (ai_specs/s02_text_mining.md).
-- Applied as the cluster superuser by `rt db migrate`; idempotent. Tables are created as
-- rotation_owner so 001's default privileges give rotation_ro SELECT on each of them.
--
-- Nothing here is committed to the repo as data: mentions and labels are quotes from the
-- transcripts and live only in this database.

SET ROLE rotation_owner;

-- assets/v1: everything a mention can be about. Rows come from `rt assets seed`: the curated
-- layers in assets/themes.yaml, every US-listed ticker (Nasdaq Trader's symbol directory) tagged
-- with S&P 500 / Nasdaq-100 membership and GICS, and the hand-kept assets/extras.yaml.
CREATE TABLE IF NOT EXISTS rt.assets (
  id                 text PRIMARY KEY,
  kind               text NOT NULL CHECK (kind IN ('index', 'sector', 'theme', 'stock', 'fund',
                       'crypto', 'rates', 'credit', 'commodity', 'fx', 'macro')),
  name               text NOT NULL,
  ticker             text,
  proxy              text,
  gics_sector        text,
  gics_sub_industry  text,
  exchange           text,
  sp500              boolean NOT NULL DEFAULT false,
  sp500_added        date,
  ndx                boolean NOT NULL DEFAULT false,
  source             text NOT NULL,
  snapshot           date NOT NULL,
  assets_version     text NOT NULL
);
CREATE INDEX IF NOT EXISTS assets_ticker_idx ON rt.assets (ticker);

-- How he says it, normalised (lower case, words only). `needs_cue`: the alias is also a common
-- word ("target", "apple") and resolves only when the extractor's ticker guess agrees.
CREATE TABLE IF NOT EXISTS rt.aliases (
  alias      text NOT NULL,
  asset_id   text NOT NULL REFERENCES rt.assets ON DELETE CASCADE,
  needs_cue  boolean NOT NULL DEFAULT false,
  source     text NOT NULL,
  PRIMARY KEY (alias, asset_id)
);

-- One row per `rt mine` invocation, whatever the engine.
CREATE TABLE IF NOT EXISTS rt.mine_runs (
  run_id              text PRIMARY KEY,
  engine              text NOT NULL CHECK (engine IN ('regex', 'llm')),
  extractor_version   text NOT NULL,
  prompt_sha          text,
  model               text,
  effort              text,
  mode                text NOT NULL CHECK (mode IN ('local', 'interactive', 'batch')),
  purpose             text NOT NULL CHECK (purpose IN ('baseline', 'dev', 'gold', 'eval',
                        'agreement', 'backfill', 'new-week')),
  batch_id            text,
  status              text NOT NULL DEFAULT 'running'
                        CHECK (status IN ('running', 'submitted', 'done', 'failed')),
  started_at          timestamptz NOT NULL DEFAULT now(),
  finished_at         timestamptz,
  weeks               integer NOT NULL DEFAULT 0,
  mentions            integer NOT NULL DEFAULT 0,
  dropped             integer NOT NULL DEFAULT 0,
  input_tokens        bigint NOT NULL DEFAULT 0,
  output_tokens       bigint NOT NULL DEFAULT 0,
  cache_read_tokens   bigint NOT NULL DEFAULT 0,
  cache_write_tokens  bigint NOT NULL DEFAULT 0,
  usd                 numeric(10, 4) NOT NULL DEFAULT 0,
  mlflow_run_id       text,
  detail              text
);

-- Each week a run read: whether it finished, and what it cost.
CREATE TABLE IF NOT EXISTS rt.mine_weeks (
  run_id              text NOT NULL REFERENCES rt.mine_runs ON DELETE CASCADE,
  video_id            text NOT NULL REFERENCES rt.transcripts,
  status              text NOT NULL CHECK (status IN ('done', 'failed')),
  mentions            integer NOT NULL DEFAULT 0,
  dropped             integer NOT NULL DEFAULT 0,
  input_tokens        bigint NOT NULL DEFAULT 0,
  output_tokens       bigint NOT NULL DEFAULT 0,
  cache_read_tokens   bigint NOT NULL DEFAULT 0,
  cache_write_tokens  bigint NOT NULL DEFAULT 0,
  usd                 numeric(10, 4) NOT NULL DEFAULT 0,
  stop_reason         text,
  error               text,
  PRIMARY KEY (run_id, video_id)
);

-- A mention: one claim about one or more assets, located verbatim in its section. Rows are never
-- overwritten; a re-run writes a new run beside the old one.
CREATE TABLE IF NOT EXISTS rt.mentions (
  id               bigserial PRIMARY KEY,
  run_id           text NOT NULL REFERENCES rt.mine_runs ON DELETE CASCADE,
  video_id         text NOT NULL REFERENCES rt.transcripts,
  ord              integer NOT NULL,
  play             text NOT NULL CHECK (play IN ('rotation', 'flow', 'valuation', 'technical',
                     'regime', 'relative', 'call', 'other')),
  direction        text NOT NULL,
  stance           text NOT NULL CHECK (stance IN ('bullish', 'bearish', 'neutral')),
  speaker          text NOT NULL CHECK (speaker IN ('him', 'reported')),
  reported_source  text,
  modality         text NOT NULL CHECK (modality IN ('observed', 'expected', 'recommended')),
  horizon          text NOT NULL CHECK (horizon IN ('days', 'weeks', 'months', 'years',
                     'unspecified')),
  confidence       real NOT NULL CHECK (confidence BETWEEN 0 AND 1),
  quote            text NOT NULL,
  section_idx      integer NOT NULL,
  span_start       integer NOT NULL,
  span_end         integer NOT NULL,
  t_seconds        double precision,
  located          text NOT NULL CHECK (located IN ('exact', 'fuzzy', 'regex')),
  match_score      real NOT NULL,
  UNIQUE (run_id, video_id, ord)
);
CREATE INDEX IF NOT EXISTS mentions_video_idx ON rt.mentions (video_id, run_id);
CREATE INDEX IF NOT EXISTS mentions_play_idx ON rt.mentions (play);

-- The assets a mention is about, each with its role in the sentence and the stance it implies
-- for that asset (rotation out of A into B: A bearish, B bullish).
CREATE TABLE IF NOT EXISTS rt.mention_assets (
  mention_id    bigint NOT NULL REFERENCES rt.mentions ON DELETE CASCADE,
  ord           integer NOT NULL,
  role          text NOT NULL CHECK (role IN ('subject', 'from', 'to', 'versus')),
  spoken        text NOT NULL,
  ticker_guess  text,
  kind_guess    text,
  asset_id      text REFERENCES rt.assets,
  resolution    text NOT NULL CHECK (resolution IN ('alias', 'ticker', 'ambiguous', 'unknown')),
  stance        text NOT NULL CHECK (stance IN ('bullish', 'bearish', 'neutral')),
  PRIMARY KEY (mention_id, ord)
);
CREATE INDEX IF NOT EXISTS mention_assets_asset_idx ON rt.mention_assets (asset_id);

-- What the provenance gate threw away, so the dropped rate can be read, not just counted.
CREATE TABLE IF NOT EXISTS rt.mine_drops (
  run_id    text NOT NULL REFERENCES rt.mine_runs ON DELETE CASCADE,
  video_id  text NOT NULL,
  ord       integer NOT NULL,
  reason    text NOT NULL CHECK (reason IN ('not-located', 'bad-direction', 'no-asset')),
  play      text,
  quote     text,
  detail    jsonb,
  PRIMARY KEY (run_id, video_id, ord)
);

-- The gold set: twelve fixed weeks, three per year.
CREATE TABLE IF NOT EXISTS rt.gold_weeks (
  video_id   text PRIMARY KEY REFERENCES rt.transcripts,
  rule       text NOT NULL,
  chosen_at  timestamptz NOT NULL DEFAULT now()
);

-- Reviews of gold mentions: the independent second read of every rotation mention, and the
-- owner's spot-checks from the viewer (`rt serve --label`). `fixes` holds corrected fields.
CREATE TABLE IF NOT EXISTS rt.labels (
  id          bigserial PRIMARY KEY,
  mention_id  bigint NOT NULL REFERENCES rt.mentions ON DELETE CASCADE,
  source      text NOT NULL CHECK (source IN ('second-read', 'owner')),
  verdict     text NOT NULL CHECK (verdict IN ('correct', 'wrong', 'fix')),
  fixes       jsonb NOT NULL DEFAULT '{}',
  note        text,
  labeled_by  text NOT NULL,
  labeled_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS labels_mention_idx ON rt.labels (mention_id, source);

-- The owner's spot-check queue: a fixed sample of gold mentions, rotation first.
CREATE TABLE IF NOT EXISTS rt.spot_checks (
  mention_id  bigint PRIMARY KEY REFERENCES rt.mentions ON DELETE CASCADE,
  ord         integer NOT NULL,
  sampled_at  timestamptz NOT NULL DEFAULT now()
);

-- Every `rt mine eval`: what was scored against what, the numbers, and the gate.
CREATE TABLE IF NOT EXISTS rt.evals (
  id             bigserial PRIMARY KEY,
  run_id         text NOT NULL REFERENCES rt.mine_runs ON DELETE CASCADE,
  gold_run_id    text NOT NULL REFERENCES rt.mine_runs ON DELETE CASCADE,
  at             timestamptz NOT NULL DEFAULT now(),
  metrics        jsonb NOT NULL,
  gate_pass      boolean NOT NULL,
  mlflow_run_id  text
);

RESET ROLE;
