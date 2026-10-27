-- rotation-tracker: schema `rt` in database `rotation` on the central Postgres.
-- Applied as the cluster superuser by `rt db migrate` (D16); idempotent.
--
--   rotation_owner  the pipeline: owns the schema and every table in it.
--   rotation_ro     notebooks and analysis: SELECT only, read-only transactions.
--
-- Nothing scraped is committed to the repo. Transcripts and chapters live here and
-- in transcript·lab's Chroma store, which stays the source of truth for raw text.

CREATE SCHEMA IF NOT EXISTS rt AUTHORIZATION rotation_owner;

GRANT USAGE ON SCHEMA rt TO rotation_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA rt TO rotation_ro;
ALTER DEFAULT PRIVILEGES FOR ROLE rotation_owner IN SCHEMA rt
  GRANT SELECT ON TABLES TO rotation_ro;

ALTER ROLE rotation_ro SET search_path = rt;
ALTER ROLE rotation_ro SET statement_timeout = '30s';
ALTER ROLE rotation_ro SET default_transaction_read_only = on;
REVOKE ALL ON SCHEMA public FROM rotation_ro;
ALTER ROLE rotation_owner SET search_path = rt, public;

-- Tables are created as the owner so default privileges reach rotation_ro.
SET ROLE rotation_owner;

-- Every upload on the channel's three tabs. `published_at` is exact (per-video
-- lookup); `approx_published_at` is the flat listing's "N weeks ago" guess.
CREATE TABLE IF NOT EXISTS rt.videos (
  video_id             text PRIMARY KEY,
  tab                  text NOT NULL CHECK (tab IN ('videos', 'streams', 'shorts')),
  listing_pos          integer NOT NULL,
  title                text NOT NULL,
  duration_s           integer,
  view_count           bigint,
  approx_published_at  timestamptz,
  published_at         timestamptz,
  live_status          text,
  has_auto_captions    boolean,
  listed_at            timestamptz NOT NULL DEFAULT now(),
  refined_at           timestamptz
);
CREATE INDEX IF NOT EXISTS videos_tab_published_idx ON rt.videos (tab, published_at);

-- Chapters as YouTube shows them, for the weekly picks only.
CREATE TABLE IF NOT EXISTS rt.chapters (
  video_id  text NOT NULL REFERENCES rt.videos ON DELETE CASCADE,
  idx       integer NOT NULL,
  start_s   double precision NOT NULL,
  end_s     double precision,
  title     text NOT NULL,
  PRIMARY KEY (video_id, idx)
);

-- One video per trading week, keyed by that week's Friday (pick rule in pick.py).
CREATE TABLE IF NOT EXISTS rt.weekly_picks (
  week_friday   date PRIMARY KEY,
  video_id      text NOT NULL REFERENCES rt.videos,
  reason        text NOT NULL CHECK (reason IN ('weekend', 'fallback')),
  rule_version  text NOT NULL,
  picked_at     timestamptz NOT NULL DEFAULT now()
);

-- One row per transcript·lab run, success or not.
CREATE TABLE IF NOT EXISTS rt.ingest_log (
  id           bigserial PRIMARY KEY,
  batch_id     text NOT NULL,
  video_id     text NOT NULL,
  started_at   timestamptz NOT NULL,
  finished_at  timestamptz,
  returncode   integer,
  status       text NOT NULL CHECK (status IN ('indexed', 'failed')),
  detail       text
);

-- A copy of transcript·lab's raw transcript, read-only from its Chroma store.
CREATE TABLE IF NOT EXISTS rt.transcripts (
  video_id    text PRIMARY KEY REFERENCES rt.videos,
  source_id   text NOT NULL,
  segments    jsonb NOT NULL,
  n_segments  integer NOT NULL,
  text        text NOT NULL,
  tsv         tsvector GENERATED ALWAYS AS (to_tsvector('english', text)) STORED,
  sha256      text NOT NULL,
  synced_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS transcripts_tsv_idx ON rt.transcripts USING gin (tsv);

-- The transcript cut at its chapters and tagged by topic (topics.py). A video
-- without chapters is one `untagged` section.
CREATE TABLE IF NOT EXISTS rt.transcript_chapters (
  video_id            text NOT NULL REFERENCES rt.transcripts ON DELETE CASCADE,
  idx                 integer NOT NULL,
  start_s             double precision NOT NULL,
  end_s               double precision,
  title               text,
  topic               text NOT NULL
                        CHECK (topic IN ('macro-flows', 'technicals', 'promo', 'intro-outro', 'untagged')),
  topic_rule_version  text NOT NULL,
  text                text NOT NULL,
  tsv                 tsvector GENERATED ALWAYS AS (to_tsvector('english', text)) STORED,
  PRIMARY KEY (video_id, idx)
);
CREATE INDEX IF NOT EXISTS transcript_chapters_tsv_idx ON rt.transcript_chapters USING gin (tsv);

RESET ROLE;
