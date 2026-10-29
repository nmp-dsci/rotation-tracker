/** Synthetic API responses for the route tests. Hand-written, never copied from the corpus:
 *  this repo is public and transcripts are not committed (AGENTS.md rule 8). */
import type {
  AssetDetail,
  Assets,
  Chart,
  Chunk,
  Health,
  Labels,
  Mention,
  Mentions,
  Mining,
  Overview,
  Pipeline,
  SearchResult,
  Week,
  WeekDetail,
} from '../lib/api';

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
  view: 'themes',
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
    { id: 'Semiconductors', theme: 'Semiconductors', kind: null, mentions: 130, weeks_hit: 13, rate: 10, rank: 1, prev_rank: 2, move: 'up', total: 195, history: [5, 10], bullish: [2, 6], bearish: [1, 2] },
    { id: 'Utilities', theme: 'Utilities', kind: null, mentions: 13, weeks_hit: 4, rate: 1, rank: 2, prev_rank: null, move: 'new', total: 13, history: [0, 1], bullish: [0, 0], bearish: [0, 1] },
    { id: 'China', theme: 'China', kind: null, mentions: 0, weeks_hit: 0, rate: 0, rank: null, prev_rank: 1, move: 'none', total: 260, history: [20, 0], bullish: [4, 0], bearish: [9, 0] },
  ],
  dropped: [],
  themes: [{ name: 'Semiconductors', pattern: '\\m(?:chips?)\\M' }],
  topics: ['macro-flows', 'untagged'],
};

export const chartAssets: Chart = {
  ...chart,
  view: 'assets',
  version: 'play/v1',
  entries: [
    { id: 'commodity:gold', theme: 'Gold', kind: 'commodity', mentions: 26, weeks_hit: 12, rate: 2, rank: 1, prev_rank: 1, move: 'same', total: 52, history: [2, 2], bullish: [1.5, 1], bearish: [0.25, 0.5] },
    { id: 'stock:NVDA', theme: 'Nvidia', kind: 'stock', mentions: 4, weeks_hit: 3, rate: 0.3077, rank: 2, prev_rank: null, move: 'new', total: 4, history: [0, 0.3077], bullish: [0, 0.2308], bearish: [0, 0] },
    { id: 'crypto:btc', theme: 'Bitcoin', kind: 'crypto', mentions: 0, weeks_hit: 0, rate: 0, rank: null, prev_rank: 2, move: 'none', total: 90, history: [6.9231, 0], bullish: [3, 0], bearish: [2, 0] },
  ],
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
// ── s02: the miner ─────────────────────────────────────────────────────────
export const mention: Mention = {
  id: 1,
  video_id: 'AAAAAAAAAAA',
  week_friday: '2026-10-23',
  title: 'A synthetic weekend wrap',
  play: 'rotation',
  direction: 'out_in',
  stance: 'bullish',
  speaker: 'him',
  reported_source: null,
  modality: 'observed',
  horizon: 'unspecified',
  confidence: 0.8,
  quote: 'a synthetic sentence where money leaves widgets for gadgets',
  section_idx: 1,
  section_title: 'Flows',
  t_seconds: 125,
  located: 'exact',
  match_score: 1,
  run_id: 'mine-test',
  assets: [
    { asset_id: 'theme:widgets', name: 'Widgets', kind: 'theme', proxy: 'WDGT', role: 'from', stance: 'bearish', spoken: 'widgets', resolution: 'alias' },
    { asset_id: null, name: null, kind: null, proxy: null, role: 'to', stance: 'bullish', spoken: 'gadgets', resolution: 'unknown' },
  ],
};
export const mentions: Mentions = {
  version: 'play/v1',
  total: 1,
  rows: [mention],
  facets: { play: { rotation: 1 }, year: { '2026': 1 }, speaker: { him: 1 }, modality: { observed: 1 }, stance: { bullish: 1 } },
  coverage: { mined: 1, weeks: 2 },
  plays: ['rotation', 'flow', 'valuation', 'technical', 'regime', 'relative', 'call', 'other'],
  directions: {
    rotation: ['in', 'out', 'out_in'],
    flow: ['buying', 'selling'],
    valuation: ['under', 'over', 'fair'],
    technical: ['bullish', 'bearish', 'neutral'],
    regime: ['risk_on', 'risk_off', 'bull', 'bear', 'neutral'],
    relative: ['a_over_b'],
    call: ['long', 'short', 'avoid', 'watch'],
    other: ['bullish', 'bearish', 'neutral'],
  },
};
export const assets: Assets = {
  rows: [
    { id: 'theme:widgets', name: 'Widgets', kind: 'theme', proxy: 'WDGT', ticker: null, gics_sector: null, sp500: false, ndx: false, mentions: 3, weeks: 2, bullish: 1, bearish: 2, rotation: 1, last_week: '2026-10-23' },
  ],
  kinds: [{ kind: 'theme', assets: 1, mentions: 3 }],
  universe: [{ kind: 'stock', n: 10 }, { kind: 'theme', n: 2 }],
};
export const asset: AssetDetail = {
  asset: { id: 'theme:widgets', kind: 'theme', name: 'Widgets', ticker: null, proxy: 'WDGT', gics_sector: null, gics_sub_industry: null, exchange: null, sp500: false, sp500_added: null, ndx: false, source: 'themes.yaml', snapshot: '2026-10-28', assets_version: 'assets/v1' },
  aliases: ['widgets', 'widget makers'],
  strip: [
    { week_friday: '2026-10-16', video_id: 'BBBBBBBBBBB', mined: false, up: 0, down: 0, flat: 0, rotation: 0 },
    { week_friday: '2026-10-23', video_id: 'AAAAAAAAAAA', mined: true, up: 0, down: 1, flat: 0, rotation: 1 },
  ],
  mentions: [mention],
  total: 1,
  by_play: { rotation: 1 },
};
const score = { tp: 1, pred: 1, gold: 1, precision: 1, recall: 1, f1: 1 };
export const mining: Mining = {
  version: 'play/v1',
  prompt_sha: 'abcdef123456',
  label_mode: false,
  coverage: { mined: 1, weeks: 2, mentions: 1, assets: 2, unknown: 1, first_week: '2026-10-23', last_week: '2026-10-23' },
  runs: [
    { run_id: 'mine-test', engine: 'llm', extractor_version: 'play/v1', prompt_sha: 'abcdef123456', model: 'claude-opus-5-5', effort: 'high', mode: 'batch', purpose: 'eval', batch_id: 'b', status: 'done', started_at: '2026-10-28T05:00:00Z', finished_at: '2026-10-28T05:20:00Z', weeks: 1, mentions: 1, dropped: 0, input_tokens: 10, output_tokens: 20, cache_read_tokens: 0, cache_write_tokens: 0, usd: 0.17, mlflow_run_id: null, detail: null },
  ],
  eval: {
    id: 1,
    run_id: 'mine-test',
    gold_run_id: 'mine-gold',
    at: '2026-10-28T06:00:00Z',
    gate_pass: false,
    mlflow_run_id: null,
    metrics: {
      per_play: { rotation: score, flow: score, valuation: score, technical: score, regime: score, relative: score, call: score, other: score },
      precision: 1, recall: 1, f1: 1, matched: 1, pred: 1, gold: 1, direction_accuracy: 1, asset_accuracy: 0.5, asset_overlap: 1,
      play_confusion: {}, rotation_precision: 1, rotation_recall: 1, dropped_rate: 0, unknown_rate: 0.5,
      gate: {
        rotation_precision: { value: 1, bar: '>= 0.85', pass: true },
        asset_accuracy: { value: 0.5, bar: '>= 0.9', pass: false },
      },
      gate_pass: false, weeks: 1, labels: {},
    },
  },
  history: [
    { at: '2026-10-28T06:00:00Z', run_id: 'mine-test', prompt_sha: 'abcdef123456', gold_run_id: 'mine-gold', gate_pass: false, rotation_precision: 1, rotation_recall: 1, rotation_run_to_run: null, f1: 1, rotation_pred: 1, rotation_gold: 1 },
  ],
  unknown: [{ spoken: 'gadgets', kind_guess: 'theme', ticker_guess: null, n: 1, weeks: 1 }],
  plays: [{ play: 'rotation', n: 1, weeks: 1, bullish: 1, bearish: 0 }],
  spend: [{ purpose: 'eval', runs: 1, usd: 0.17, weeks: 1, output_tokens: 20 }],
  gold: { weeks: [{ video_id: 'AAAAAAAAAAA', week_friday: '2026-10-23' }], labels: [], spot: { total: 1, done: 0 } },
  drops: [],
  mlflow: { experiment: null, runs: {} },
};
export const labels: Labels = {
  label_mode: false,
  items: [{ ...mention, ord: 0, before: 'synthetic words before', after: 'synthetic words after', owner: null, second_read: null }],
};

export function respond(url: string): unknown {
  const path = url.split('?')[0];
  if (path === '/healthz') return health;
  if (path === '/api/overview') return overview;
  if (path === '/api/weeks') return weeks;
  if (path === '/api/weeks/AAAAAAAAAAA') return week;
  if (path === '/api/weeks/AAAAAAAAAAA/chunks') return chunks;
  if (path === '/api/search') return search;
  if (path === '/api/chart') return url.includes('view=assets') ? chartAssets : chart;
  if (path === '/api/pipeline') return pipeline;
  if (path === '/api/mentions') return mentions;
  if (path === '/api/assets') return assets;
  if (path === `/api/assets/${encodeURIComponent('theme:widgets')}`) return asset;
  if (path === '/api/mining') return mining;
  if (path === '/api/labels') return labels;
  return undefined;
}
