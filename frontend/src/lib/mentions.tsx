/**
 * How a mention reads everywhere (s02): the play, its direction as a glyph and a word, the
 * verbatim quote with a link to the second it was said, and the assets it is about. Stance is
 * never colour alone: ↑ bullish, ↓ bearish, · neutral, always with the word beside it or in the
 * accessible name.
 */
import { Link } from 'react-router-dom';
import type { Mention, MentionAsset, Play, Role, Stance } from './api';
import { date, dur, youtube } from './format';

export const PLAY_LABEL: Record<Play, string> = {
  rotation: 'Rotation',
  flow: 'Flow',
  valuation: 'Valuation',
  technical: 'Technical',
  regime: 'Regime',
  relative: 'Relative',
  call: 'Call',
  other: 'Other',
};

export const PLAY_NOTE: Record<Play, string> = {
  rotation: 'money moving between assets, sectors or themes',
  flow: 'positioning he reports: options, dark pools, funds, retail',
  valuation: 'cheap or expensive, fundamentally',
  technical: 'a chart or breadth judgement',
  regime: 'risk-on or risk-off, bull or bear, the macro state',
  relative: 'one asset against another',
  call: 'his own view or instruction',
  other: 'a price claim that fits none of the above',
};

export const DIRECTION_LABEL: Record<string, string> = {
  in: 'in',
  out: 'out',
  out_in: 'out → in',
  buying: 'buying',
  selling: 'selling',
  under: 'undervalued',
  over: 'overvalued',
  fair: 'fair value',
  bullish: 'bullish',
  bearish: 'bearish',
  neutral: 'neutral',
  risk_on: 'risk-on',
  risk_off: 'risk-off',
  bull: 'bull market',
  bear: 'bear market',
  a_over_b: 'beats',
  long: 'long',
  short: 'short',
  avoid: 'avoid',
  watch: 'watch',
};

const GLYPH: Record<Stance, string> = { bullish: '↑', bearish: '↓', neutral: '·' };
const ROLE: Record<Role, string> = { subject: '', from: 'out of', to: 'into', versus: 'vs' };

export function StanceGlyph({ stance, label = true }: { stance: Stance; label?: boolean }) {
  return (
    <span className={`stance ${stance}`} title={stance}>
      <span aria-hidden="true">{GLYPH[stance]}</span>
      {label ? <span className="stance-w"> {stance}</span> : <span className="sr-only">{stance}</span>}
    </span>
  );
}

export function PlayBadge({ play, direction }: { play: Play; direction: string }) {
  return (
    <span className="play-b" title={PLAY_NOTE[play]}>
      <b>{PLAY_LABEL[play]}</b> <span className="dir">{DIRECTION_LABEL[direction] ?? direction}</span>
    </span>
  );
}

export function AssetChip({ a }: { a: MentionAsset }) {
  const role = ROLE[a.role];
  const body = (
    <>
      {role && <span className="role">{role} </span>}
      <span aria-hidden="true" className={`stance ${a.stance}`}>
        {GLYPH[a.stance]}
      </span>{' '}
      {a.name ?? a.spoken}
      {a.proxy && <span className="proxy"> {a.proxy}</span>}
      <span className="sr-only"> ({a.stance})</span>
    </>
  );
  return a.asset_id ? (
    <Link className="asset-chip" to={`/assets/${encodeURIComponent(a.asset_id)}`} title={`said as “${a.spoken}”`}>
      {body}
    </Link>
  ) : (
    <span className="asset-chip unknown" title={`“${a.spoken}”: ${a.resolution}, not in the asset map`}>
      {body} <span className="badge warn">? {a.resolution}</span>
    </span>
  );
}

export function MentionRow({ m, showWeek = true }: { m: Mention; showWeek?: boolean }) {
  return (
    <li className="hit mention">
      <span className="hit-date">{showWeek ? date(m.week_friday) : `§${m.section_idx}`}</span>
      <div className="hit-body">
        <div className="m-head">
          <PlayBadge play={m.play} direction={m.direction} />
          <StanceGlyph stance={m.stance} />
        </div>
        <blockquote className="quote">“{m.quote}”</blockquote>
        <div className="m-assets">
          {m.assets.map((a, i) => (
            <AssetChip key={i} a={a} />
          ))}
        </div>
        <p className="m-meta">
          {m.speaker === 'reported' ? `reported${m.reported_source ? `: ${m.reported_source}` : ''}` : 'his view'} ·{' '}
          {m.modality} · {m.horizon === 'unspecified' ? 'no horizon' : m.horizon} · confidence {m.confidence.toFixed(2)}
          {showWeek && (
            <>
              {' '}
              · <Link to={`/weeks/${m.video_id}`}>{m.section_title || 'the week'}</Link>
            </>
          )}
        </p>
      </div>
      <a className="at hit-at" href={youtube(m.video_id, m.t_seconds)} target="_blank" rel="noreferrer" title="Hear it on YouTube at this second">
        ▶ {dur(m.t_seconds)}
      </a>
    </li>
  );
}

export function pct(v: number | null | undefined, digits = 0): string {
  return v == null ? '—' : `${(v * 100).toFixed(digits)}%`;
}

export function usd(v: number | null | undefined): string {
  return v == null ? '—' : `$${v.toFixed(2)}`;
}
