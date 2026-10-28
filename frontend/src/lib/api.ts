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
  theme: string;
  mentions: number;
  weeks_hit: number;
  rate: number;
  rank: number;
  prev_rank: number | null;
  move: 'new' | 'up' | 'down' | 'same';
  history: number[];
};
export type Chart = {
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
  chart: (quarter?: string | null) => `/api/chart${qs({ quarter })}`,
  pipeline: () => '/api/pipeline',
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
