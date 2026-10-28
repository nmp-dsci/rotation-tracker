import type { Status } from './api';
import { int } from './format';

export type Stage = {
  n: number;
  name: string;
  cmd: string | null;
  did: string;
  store: string | null;
  state: 'built' | 'next' | 'planned';
};

/** The pipeline as built (M1, ai_specs/s00) and the roadmap after it (README). */
export function stages(s: Status): Stage[] {
  return [
    {
      n: 1,
      name: 'Catalog',
      cmd: 'rt catalog',
      did: `${int(s.videos + s.streams + s.shorts)} uploads listed with yt-dlp: ${int(s.videos)} videos, ${int(s.streams)} streams, ${int(s.shorts)} shorts`,
      store: 'rt.videos',
      state: 'built',
    },
    {
      n: 2,
      name: 'Refine',
      cmd: 'rt refine',
      did: `${int(s.videos_dated)} exact publish times, back to the first week in scope`,
      store: 'rt.videos.published_at',
      state: 'built',
    },
    {
      n: 3,
      name: 'Pick',
      cmd: 'rt pick',
      did: `${int(s.picks)} weeks, one video each: ${int(s.picks_weekend)} weekend wraps, ${int(s.picks - s.picks_weekend)} fallbacks`,
      store: 'rt.weekly_picks',
      state: 'built',
    },
    {
      n: 4,
      name: 'Ingest',
      cmd: 'rt ingest',
      did: `${int(s.ingested)} transcripts from Supadata through transcript·lab, 1 credit each`,
      store: 'Chroma raw_transcripts · rt.ingest_log',
      state: 'built',
    },
    {
      n: 5,
      name: 'Sync',
      cmd: 'rt sync',
      did: `${int(s.transcripts)} transcripts cut into ${int(s.sections)} chapter sections, ${int(s.macro_flows)} of them macro & flows`,
      store: 'rt.transcripts · rt.transcript_chapters',
      state: 'built',
    },
    { n: 6, name: 'Prices', cmd: null, did: "Copy value-invest-agent's yfinance loader", store: null, state: 'next' },
    { n: 7, name: 'Extract', cmd: null, did: 'Rotation calls, each with a verbatim quote and a timestamp', store: null, state: 'planned' },
    { n: 8, name: 'Signal', cmd: null, did: 'Rotated-out candidates, resolved to a fixed taxonomy', store: null, state: 'planned' },
    { n: 9, name: 'Backtest', cmd: null, did: 'Rebounds measured against controls, with a sealed holdout', store: null, state: 'planned' },
    { n: 10, name: 'Listener', cmd: null, did: 'A forward watchlist. Never orders', store: null, state: 'planned' },
  ];
}
