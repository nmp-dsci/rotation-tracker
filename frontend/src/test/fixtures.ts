/** Synthetic API responses for the route tests. Hand-written, never copied from the corpus:
 *  this repo is public and transcripts are not committed (AGENTS.md rule 8). */
import type { Chart, Chunk, Health, Overview, Pipeline, SearchResult, Week, WeekDetail } from '../lib/api';

const status = {
  videos: 10,
  streams: 2,
  shorts: 1,
  videos_dated: 8,
  picks: 2,
  picks_weekend: 1,
  first_week: '2026-10-16',
  last_week: '2026-10-23',
  ingested: 2,
  transcripts: 2,
  sections: 3,
  macro_flows: 2,
};

export const weeks: Week[] = [
  {
    week_friday: '2026-10-23',
    video_id: 'AAAAAAAAAAA',
    reason: 'weekend',
    title: 'A synthetic weekend wrap',
    published_at: '2026-10-24T01:30:00Z',
    duration_s: 1500,
    view_count: 1000,
    n_segments: 10,
    n_chars: 500,
    n_chapters: 2,
  },
  {
    week_friday: '2026-10-16',
    video_id: 'BBBBBBBBBBB',
    reason: 'fallback',
    title: 'A synthetic Thursday recap',
    published_at: '2026-10-16T01:00:00Z',
    duration_s: 900,
    view_count: 500,
    n_segments: 8,
    n_chars: 300,
    n_chapters: 0,
  },
];

export const health: Health = { ok: true, code_sha: 'abc1234', postgres: 'up', chroma: 'up', mlflow: 'down' };

export const overview: Overview = {
  status,
  totals: { chars: 800, words: 150, segments: 18, seconds: 2400 },
  topics: { 'macro-flows': 2, technicals: 1, 'intro-outro': 0, promo: 0, untagged: 0 },
  latest: weeks,
  channel: { name: 'Example channel', handle: '@example' },
};

export const week: WeekDetail = {
  ...weeks[0],
  sections: [
    {
      idx: 0,
      start_s: 0,
      end_s: 60,
      title: 'Money moving between sectors',
      topic: 'macro-flows',
      topic_rule_version: 'topic/v1',
      n_chars: 40,
      paragraphs: [{ t: 0, text: 'A synthetic paragraph about flows.' }],
    },
    {
      idx: 1,
      start_s: 60,
      end_s: 120,
      title: 'Chart levels',
      topic: 'technicals',
      topic_rule_version: 'topic/v1',
      n_chars: 20,
      paragraphs: [{ t: 60, text: 'A synthetic paragraph about levels.' }],
    },
  ],
  ingest: [{ batch_id: 'b1', started_at: '2026-10-27T06:00:00Z', finished_at: '2026-10-27T06:00:35Z', returncode: 0, status: 'indexed' }],
  prev: 'BBBBBBBBBBB',
  next: null,
  stored: { sha256: 'f'.repeat(64), synced_at: '2026-10-27T08:00:00Z', chroma_raw_id: 'raw_transcript:AAAAAAAAAAA', chroma_chunks: 3 },
  mlflow_url: null,
};

export const chunks: Chunk[] = [{ idx: 0, start_s: 0, end_s: 40, text: 'A synthetic chunk.' }];

export const search: SearchResult = {
  q: 'rotation',
  topics: ['macro-flows', 'untagged'],
  hits: [
    {
      video_id: 'AAAAAAAAAAA',
      idx: 0,
      section: 'Money moving between sectors',
      topic: 'macro-flows',
      start_s: 0,
      week_friday: '2026-10-23',
      title: 'A synthetic weekend wrap',
      rank: 0.1,
      snippet: 'the «rotation» out of growth',
    },
  ],
  quarters: [{ quarter: '2026-10-01', weeks: 1, sections: 1, of: 2 }],
  total: { sections: 1, weeks: 1, of: 2 },
};

export const chart: Chart = {
  version: 'themes/v0',
  quarter: '2026-07-01',
  previous: '2026-04-01',
  quarters: [
    { quarter: '2026-04-01', weeks: 13, closed: true },
    { quarter: '2026-07-01', weeks: 13, closed: true },
  ],
  history_quarters: ['2026-04-01', '2026-07-01'],
  weeks_in_quarter: 13,
  entries: [
    { theme: 'Semiconductors', mentions: 130, weeks_hit: 13, rate: 10, rank: 1, prev_rank: 2, move: 'up', history: [5, 10] },
    { theme: 'Utilities', mentions: 13, weeks_hit: 4, rate: 1, rank: 2, prev_rank: null, move: 'new', history: [0, 1] },
  ],
  dropped: ['China'],
  themes: [{ name: 'Semiconductors', pattern: '\\m(?:chips?)\\M' }],
  topics: ['macro-flows', 'untagged'],
};

export const pipeline: Pipeline = {
  status,
  tables: [{ name: 'rt.videos', rows: 13, bytes: 8192 }],
  chroma: { path: '/tmp/chroma', raw_total: 5, raw_ours: 2, chunks_total: 50, chunks_ours: 6 },
  batches: [{ batch_id: 'b1', n: 2, indexed: 2, started: '2026-10-27T06:00:00Z', finished: '2026-10-27T06:01:10Z' }],
  runs: [],
  mlflow_url: null,
  credits: [{ key: 1, plan: 'Basic', left: 98, max: 100 }],
  credits_error: null,
  hours_et: Array.from({ length: 24 }, (_, h) => (h >= 19 ? 5 : 0)),
  pick_weekdays: [0, 0, 0, 0, 1, 1, 0],
  years: [{ year: 2026, weeks: 2, weekend: 1 }],
  decisions: [{ question: 'Source', decision: 'An example channel, `@example`' }],
  experiment: 'rotation-tracker/ingest',
};

/** URL path → body, for the fetch mock. */
export function respond(url: string): unknown {
  const path = url.split('?')[0];
  if (path === '/healthz') return health;
  if (path === '/api/overview') return overview;
  if (path === '/api/weeks') return weeks;
  if (path === '/api/weeks/AAAAAAAAAAA') return week;
  if (path === '/api/weeks/AAAAAAAAAAA/chunks') return chunks;
  if (path === '/api/search') return search;
  if (path === '/api/chart') return chart;
  if (path === '/api/pipeline') return pipeline;
  return undefined;
}
