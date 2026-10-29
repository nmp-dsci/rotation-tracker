/**
 * The API contract, typed: src/rotation_tracker/serving/app.py. Every route is a read over what
 * the pipeline built (Postgres schema rt, transcript·lab's Chroma store, MLflow, Supadata).
 */
import { useEffect, useState } from 'react';

export type Topic = 'macro-flows' | 'technicals' | 'intro-outro' | 'promo' | 'untagged';
export const TOPICS: Topic[] = ['macro-flows', 'untagged', 'technicals', 'intro-outro', 'promo'];
export const READ_TOPICS: Topic[] = ['macro-flows', 'untagged'];

export type Health = {
  ok: true;
  code_sha: string;
  postgres: 'up' | 'down';
  chroma: 'up' | 'down';
  mlflow: 'up' | 'down';
};

export type Status = {
  videos: number;
  streams: number;
  shorts: number;
  videos_dated: number;
  picks: number;
  picks_weekend: number;
  first_week: string;
  last_week: string;
  ingested: number;
  transcripts: number;
  sections: number;
  macro_flows: number;
};

export type Week = {
  week_friday: string;
  video_id: string;
  reason: 'weekend' | 'fallback';
  title: string;
  published_at: string;
  duration_s: number | null;
  view_count: number | null;
  n_segments: number | null;
  n_chars: number | null;
  n_chapters: number;
};

export type Overview = {
  status: Status;
  totals: { chars: number; words: number; segments: number; seconds: number };
  topics: Record<Topic, number>;
  latest: Week[];
  channel: { name: string; handle: string };
};

export type Paragraph = { t: number; text: string };
export type Section = {
  idx: number;
  start_s: number;
  end_s: number | null;
  title: string | null;
  topic: Topic;
  topic_rule_version: string;
  n_chars: number;
  paragraphs: Paragraph[];
};
export type IngestRow = {
  batch_id: string;
  started_at: string;
  finished_at: string | null;
  returncode: number | null;
  status: string;
};
export type WeekDetail = Week & {
  sections: Section[];
  ingest: IngestRow[];
  prev: string | null;
  next: string | null;
  stored: { sha256: string | null; synced_at: string | null; chroma_raw_id: string; chroma_chunks: number | null };
  mlflow_url: string | null;
};
export type Chunk = { idx: number; start_s: number | null; end_s: number | null; text: string };

export type Hit = {
  video_id: string;
  idx: number;
  section: string | null;
  topic: Topic;
  start_s: number;
  week_friday: string;
  title: string;
  rank: number;
  snippet: string;
};
export type QuarterCount = { quarter: string; weeks: number; sections: number; of: number };
export type SearchResult = {
  q: string;
  topics: Topic[];
  hits: Hit[];
  quarters: QuarterCount[];
  total: { sections: number; weeks: number; of: number } | null;
};

export type ChartEntry = {
  id: string; // the theme's name, or the asset id on the assets view
  theme: string; // what to show: the theme, or the asset's name
  kind: string | null; // the asset's layer on the assets view
  mentions: number;
  weeks_hit: number;
  rate: number;
  rank: number | null; // null: not mentioned in the quarter
  prev_rank: number | null;
  move: 'new' | 'up' | 'down' | 'same' | 'none';
  total: number; // mentions in every quarter on record
  history: number[];
  bullish: number[];
  bearish: number[];
};
export type Chart = {
  view: 'themes' | 'assets';
  version: string;
  quarter: string;
  previous: string | null;
  quarters: { quarter: string; weeks: number; closed: boolean }[];
  history_quarters: string[];
  weeks_in_quarter: number;
  entries: ChartEntry[];
  dropped: string[];
  themes: { name: string; pattern: string }[];
  topics: Topic[];
};

export type Run = {
  run_id: string;
  name: string | null;
  kind: string | null;
  status: string | null;
  started: string;
  metrics: Record<string, number>;
  url: string;
};
export type Pipeline = {
  status: Status;
  tables: { name: string; rows: number; bytes: number }[];
  chroma: {
    path: string;
    raw_total?: number;
    raw_ours?: number;
    chunks_total?: number;
    chunks_ours?: number;
    error?: string;
  };
  batches: { batch_id: string; n: number; indexed: number; started: string; finished: string | null }[];
  runs: Run[];
  mlflow_url: string | null;
  credits: { key: number; plan: string; left: number; max: number }[] | null;
  credits_error: string | null;
  hours_et: number[];
  pick_weekdays: number[];
  years: { year: number; weeks: number; weekend: number }[];
  decisions: { question: string; decision: string }[];
  experiment: string;
};

// ── s02: the miner ─────────────────────────────────────────────────────────
export type Play = 'rotation' | 'flow' | 'valuation' | 'technical' | 'regime' | 'relative' | 'call' | 'other';
export const PLAYS: Play[] = ['rotation', 'flow', 'valuation', 'technical', 'regime', 'relative', 'call', 'other'];
export type Stance = 'bullish' | 'bearish' | 'neutral';
export type Role = 'subject' | 'from' | 'to' | 'versus';

export type MentionAsset = {
  asset_id: string | null;
  name: string | null;
  kind: string | null;
  proxy: string | null;
  role: Role;
  stance: Stance;
  spoken: string;
  resolution: 'alias' | 'ticker' | 'ambiguous' | 'unknown';
};
export type Mention = {
  id: number;
  video_id: string;
  week_friday: string;
  title: string;
  play: Play;
  direction: string;
  stance: Stance;
  speaker: 'him' | 'reported';
  reported_source: string | null;
  modality: 'observed' | 'expected' | 'recommended';
  horizon: string;
  confidence: number;
  quote: string;
  section_idx: number;
  section_title: string | null;
  t_seconds: number | null;
  located: string;
  match_score: number;
  run_id: string;
  assets: MentionAsset[];
};
export type Mentions = {
  version: string;
  total: number;
  rows: Mention[];
  facets: Record<'play' | 'year' | 'speaker' | 'modality' | 'stance', Record<string, number>>;
  coverage: { mined: number; weeks: number };
  plays: Play[];
  directions: Record<Play, string[]>;
};
export type AssetRow = {
  id: string;
  name: string;
  kind: string;
  proxy: string | null;
  ticker: string | null;
  gics_sector: string | null;
  sp500: boolean;
  ndx: boolean;
  mentions: number;
  weeks: number;
  bullish: number;
  bearish: number;
  rotation: number;
  last_week: string;
};
export type Assets = {
  rows: AssetRow[];
  kinds: { kind: string; assets: number; mentions: number }[];
  universe: { kind: string; n: number }[];
};
export type StripCell = {
  week_friday: string;
  video_id: string;
  mined: boolean;
  up: number;
  down: number;
  flat: number;
  rotation: number;
};
export type AssetDetail = {
  asset: {
    id: string;
    kind: string;
    name: string;
    ticker: string | null;
    proxy: string | null;
    gics_sector: string | null;
    gics_sub_industry: string | null;
    exchange: string | null;
    sp500: boolean;
    sp500_added: string | null;
    ndx: boolean;
    source: string;
    snapshot: string;
    assets_version: string;
  };
  aliases: string[];
  strip: StripCell[];
  mentions: Mention[];
  total: number;
  by_play: Record<string, number>;
};
export type MineRun = {
  run_id: string;
  engine: 'llm' | 'regex';
  extractor_version: string;
  prompt_sha: string | null;
  model: string | null;
  effort: string | null;
  mode: string;
  purpose: string;
  batch_id: string | null;
  status: string;
  started_at: string;
  finished_at: string | null;
  weeks: number;
  mentions: number;
  dropped: number;
  input_tokens: number;
  output_tokens: number;
  cache_read_tokens: number;
  cache_write_tokens: number;
  usd: number;
  mlflow_run_id: string | null;
  detail: string | null;
};
export type PlayScore = { tp: number; pred: number; gold: number; precision: number | null; recall: number | null; f1: number | null };
export type GateRow = { value: number | null; bar: string; pass: boolean };
export type EvalMetrics = {
  per_play: Record<Play, PlayScore>;
  precision: number | null;
  recall: number | null;
  f1: number | null;
  matched: number;
  pred: number;
  gold: number;
  direction_accuracy: number | null;
  asset_accuracy: number | null;
  asset_overlap: number | null;
  play_confusion: Record<string, number>;
  rotation_precision: number | null;
  rotation_recall: number | null;
  dropped_rate: number | null;
  unknown_rate: number | null;
  gate: Record<string, GateRow>;
  gate_pass: boolean;
  weeks: number;
  labels: Record<string, number>;
  baseline?: { run_id: string; precision: number | null; recall: number | null; f1: number | null; rotation_precision: number | null; rotation_recall: number | null; per_play: Record<Play, PlayScore> };
  agreement?: { run_id: string; weeks: number; f1: number | null; rotation_f1: number | null };
};
export type Mining = {
  version: string;
  prompt_sha: string;
  label_mode: boolean;
  coverage: { mined: number; weeks: number; mentions: number; assets: number; unknown: number; first_week: string | null; last_week: string | null };
  runs: MineRun[];
  eval: { id: number; run_id: string; gold_run_id: string; at: string; metrics: EvalMetrics; gate_pass: boolean; mlflow_run_id: string | null } | null;
  history: {
    at: string;
    run_id: string;
    prompt_sha: string;
    gold_run_id: string;
    gate_pass: boolean;
    rotation_precision: number | null;
    rotation_recall: number | null;
    rotation_run_to_run: number | null;
    f1: number | null;
    rotation_pred: number;
    rotation_gold: number;
  }[];
  unknown: { spoken: string; kind_guess: string | null; ticker_guess: string | null; n: number; weeks: number }[];
  plays: { play: Play; n: number; weeks: number; bullish: number; bearish: number }[];
  spend: { purpose: string; runs: number; usd: number; weeks: number; output_tokens: number }[];
  gold: {
    weeks: { video_id: string; week_friday: string }[];
    labels: { source: string; verdict: string; n: number }[];
    spot: { total: number; done: number };
  };
  drops: { reason: string; play: string; quote: string; week_friday: string; video_id: string }[];
  mlflow: { experiment: string | null; runs: Record<string, string> };
};
export type OwnerLabel = { verdict: 'correct' | 'wrong' | 'fix'; fixes: Record<string, string>; note: string | null; at?: string };
export type SpotCheck = Mention & {
  ord: number;
  before: string;
  after: string;
  owner: OwnerLabel | null;
  second_read: OwnerLabel | null;
};
export type Labels = { label_mode: boolean; items: SpotCheck[] };
export type MentionFilters = Partial<Record<'play' | 'direction' | 'stance' | 'asset' | 'kind' | 'year' | 'speaker' | 'modality' | 'week' | 'q' | 'limit', string | number | null>>;

const seg = (s: string) => encodeURIComponent(s);
function qs(p: Record<string, string | number | null | undefined>): string {
  const e = Object.entries(p).filter(([, v]) => v != null && v !== '');
  return e.length ? `?${new URLSearchParams(e.map(([k, v]) => [k, String(v)])).toString()}` : '';
}

export const api = {
  health: () => '/healthz',
  overview: () => '/api/overview',
  weeks: () => '/api/weeks',
  week: (id: string) => `/api/weeks/${seg(id)}`,
  chunks: (id: string) => `/api/weeks/${seg(id)}/chunks`,
  search: (q: string, topics: Topic[], order: 'recent' | 'rank') =>
    `/api/search${qs({ q, topics: topics.join(','), order })}`,
  chart: (quarter?: string | null, view?: string | null) => `/api/chart${qs({ quarter, view })}`,
  pipeline: () => '/api/pipeline',
  mentions: (f: MentionFilters) => `/api/mentions${qs(f)}`,
  assets: (kind?: string | null, q?: string | null) => `/api/assets${qs({ kind, q })}`,
  asset: (id: string) => `/api/assets/${seg(id)}`,
  mining: () => '/api/mining',
  labels: () => '/api/labels',
};

// SHOWCASE_BASE (nmp-central-ai s06) puts the app under a sub-path; API paths follow it.
const BASE = import.meta.env.BASE_URL.replace(/\/$/, '');
const abs = (url: string) => `${BASE}${url}`;

async function read<T>(r: Response, url: string): Promise<T> {
  if (!r.ok) {
    let detail = `${r.status} ${r.statusText}`;
    try {
      const body = (await r.json()) as { detail?: unknown };
      if (typeof body.detail === 'string') detail = body.detail;
    } catch {
      // not JSON: keep the status line
    }
    throw new HttpError(r.status, `${url}: ${detail}`);
  }
  return (await r.json()) as T;
}

export class HttpError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

export async function get<T>(url: string): Promise<T> {
  return read<T>(await fetch(abs(url)), url);
}

/** The viewer's one write: an owner spot-check (only under `rt serve --label`). */
export async function post<T>(url: string, body: unknown): Promise<T> {
  return read<T>(
    await fetch(abs(url), { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) }),
    url,
  );
}

/** GET a URL whenever it changes; `url: null` fetches nothing. Stale data stays until the new arrives. */
export function useGet<T>(url: string | null): { data: T | null; error: string | null; status: number | null } {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<number | null>(null);
  useEffect(() => {
    if (!url) {
      setData(null);
      return;
    }
    let live = true;
    setError(null);
    get<T>(url)
      .then((d) => {
        if (live) {
          setData(d);
          setStatus(200);
        }
      })
      .catch((e: unknown) => {
        if (live) {
          setError(e instanceof Error ? e.message : String(e));
          setStatus(e instanceof HttpError ? e.status : null);
        }
      });
    return () => {
      live = false;
    };
  }, [url]);
  return { data, error, status };
}
