/**
 * The pieces every page shares. Colour comes only from house.css tokens (classes in styles.css);
 * every state also carries a word or a glyph, never colour alone. Bars are HTML so labels never
 * stretch; the sparkline is SVG marks with HTML numbers beside it.
 */
import { type ReactNode, useState } from 'react';
import { Link } from 'react-router-dom';
import type { ChartEntry, Week } from './api';
import { DASH, TOPIC_LABEL, type ThumbSize, date, dur, thumb } from './format';

// ── states ────────────────────────────────────────────────────────────────
export function ErrorNote({ error, what }: { error: string; what?: string }) {
  return (
    <div className="callout red" role="alert">
      <span className="badge bad">✕ error</span> {what ? `Could not load ${what}: ` : ''}
      <span className="mono">{error}</span>
    </div>
  );
}

export function Loading({ error, what }: { error: string | null; what?: string }) {
  if (error) return <ErrorNote error={error} what={what} />;
  return (
    <p className="busy" role="status" aria-live="polite">
      <span className="busy-dot" aria-hidden="true" /> Loading{what ? ` ${what}` : ''}…
    </p>
  );
}

// ── type ──────────────────────────────────────────────────────────────────
/** The template's page opener: a small label over very large uppercase type. */
export function PageHead({ eyebrow, title, children }: { eyebrow: string; title: string; children?: ReactNode }) {
  return (
    <header className="page-head">
      <p className="kicker">{eyebrow}</p>
      <h1 className="display">{title}</h1>
      {children}
    </header>
  );
}

/** Markdown `code` spans from the plan of record, as <code>. */
export function Ticks({ text }: { text: string }) {
  return (
    <>
      {text.split('`').map((part, i) =>
        i % 2 ? <code key={i}>{part}</code> : <span key={i}>{part}</span>,
      )}
    </>
  );
}

/** ts_headline output with «» around each match, as <mark>. No HTML from the server is trusted. */
export function Snippet({ text }: { text: string }) {
  const parts = text.split(/«|»/);
  return (
    <>
      {parts.map((p, i) => (i % 2 ? <mark key={i}>{p}</mark> : <span key={i}>{p}</span>))}
    </>
  );
}

export function TopicBadge({ topic }: { topic: string }) {
  const read = topic === 'macro-flows' || topic === 'untagged';
  return (
    <span className={`badge ${read ? 'ok' : ''}`} title={read ? 'read by rotation work' : 'not read by rotation work'}>
      {read ? '● ' : '○ '}
      {TOPIC_LABEL[topic] ?? topic}
    </span>
  );
}

export function KindBadge({ reason }: { reason: Week['reason'] }) {
  return (
    <span className="kind" title={reason === 'weekend' ? 'Uploaded between Friday close and Monday open' : 'No weekend upload: the last recap of the week'}>
      {reason === 'weekend' ? 'Weekend wrap' : 'Fallback'}
    </span>
  );
}

// ── covers ────────────────────────────────────────────────────────────────
/** A YouTube thumbnail, toned to the project hue until hovered. maxres falls back to hq. */
export function Cover({ id, size = 'hq', alt = '', eager = false }: { id: string; size?: ThumbSize; alt?: string; eager?: boolean }) {
  const [src, setSrc] = useState(thumb(id, size));
  return (
    <span className="cover">
      <img
        src={src}
        alt={alt}
        loading={eager ? 'eager' : 'lazy'}
        decoding="async"
        onError={() => setSrc((s) => (s.includes('maxres') ? thumb(id, 'hq') : s))}
      />
    </span>
  );
}

export function Release({ w, showYear = true }: { w: Week; showYear?: boolean }) {
  return (
    <Link className="release" to={`/weeks/${w.video_id}`}>
      <span className="art">
        <Cover id={w.video_id} />
        <KindBadge reason={w.reason} />
        <span className="play" aria-hidden="true">
          ▶
        </span>
      </span>
      <span className="r-title">{w.title}</span>
      <span className="r-meta">
        {showYear ? date(w.week_friday) : date(w.week_friday).replace(/ \d{4}$/, '')} · {dur(w.duration_s)}
      </span>
    </Link>
  );
}

// ── charts ────────────────────────────────────────────────────────────────
export type Bar = { key: string; label: string; value: number; tip: string; dim?: boolean };

/** Vertical bars in HTML: thin marks, 4px rounded tops on the baseline, a 2px gap, a tooltip on
 *  hover and focus, every value also in the table view. One series, so no legend. */
export function Bars({ bars, caption, every = 1, height = 160 }: { bars: Bar[]; caption: string; every?: number; height?: number }) {
  const [on, setOn] = useState<number | null>(null);
  const max = Math.max(1, ...bars.map((b) => b.value));
  return (
    <figure className="bars-fig">
      <div className="bars" style={{ height }} role="img" aria-label={caption} onMouseLeave={() => setOn(null)}>
        {bars.map((b, i) => (
          <div
            key={b.key}
            className={`vbar${b.dim ? ' dim' : ''}${on === i ? ' on' : ''}${i < bars.length / 5 ? ' tip-l' : i >= (bars.length * 4) / 5 ? ' tip-r' : ''}`}
            tabIndex={0}
            onMouseEnter={() => setOn(i)}
            onFocus={() => setOn(i)}
            onBlur={() => setOn(null)}
            aria-label={b.tip}
          >
            <span className="fill" style={{ height: `${(b.value / max) * 100}%` }} />
            {on === i && (
              <span className="tip" role="tooltip">
                {b.tip}
              </span>
            )}
          </div>
        ))}
      </div>
      <div className="bars-axis" aria-hidden="true">
        {bars.map((b, i) => (
          <span key={b.key}>{i % every === 0 ? b.label : ''}</span>
        ))}
      </div>
      <figcaption>{caption}</figcaption>
      <details className="as-table">
        <summary>Table view</summary>
        <div className="tablewrap">
          <table>
            <tbody>
              {bars.map((b) => (
                <tr key={b.key}>
                  <td className="k">{b.label}</td>
                  <td className="n">{b.value.toLocaleString('en-US')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </figure>
  );
}

/** Mentions per wrap over the last quarters: a 2px line, the last point marked. */
export function Spark({ values, label }: { values: number[]; label: string }) {
  const w = 120;
  const h = 36;
  const pad = 4;
  if (values.length < 2) return <span className="spark-none">{DASH}</span>;
  const max = Math.max(...values, 0.0001);
  const x = (i: number) => pad + (i * (w - 2 * pad)) / (values.length - 1);
  const y = (v: number) => h - pad - (v / max) * (h - 2 * pad);
  const pts = values.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(' ');
  const last = values.length - 1;
  return (
    <svg className="spark" width={w} height={h} viewBox={`0 0 ${w} ${h}`} role="img" aria-label={label}>
      <title>{label}</title>
      <line className="base" x1={pad} x2={w - pad} y1={h - pad} y2={h - pad} />
      <polyline points={pts} />
      <circle cx={x(last)} cy={y(values[last])} r={4} />
    </svg>
  );
}

export function Move({ e }: { e: ChartEntry }) {
  if (e.move === 'new') return <span className="badge rec">New</span>;
  if (e.move === 'same')
    return (
      <span className="move" title="Same place as last quarter">
        <span aria-hidden="true">=</span>
        <span className="sr-only">no change</span>
      </span>
    );
  const by = Math.abs((e.prev_rank ?? e.rank) - e.rank);
  return (
    <span className={`move ${e.move}`} title={`${e.move === 'up' ? 'Up' : 'Down'} ${by} from #${e.prev_rank}`}>
      <span aria-hidden="true">{e.move === 'up' ? '▲' : '▼'}</span> {by}
      <span className="sr-only">{e.move === 'up' ? ' places up' : ' places down'}</span>
    </span>
  );
}
