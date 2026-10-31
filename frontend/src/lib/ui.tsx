/**
 * The pieces every page shares. Colour comes only from house.css tokens (classes in styles.css);
 * every state also carries a word or a glyph, never colour alone. Bars are HTML so labels never
 * stretch; the sparkline is SVG marks with HTML numbers beside it.
 */
import { type ReactNode, useState } from 'react';
import { Link } from 'react-router-dom';
import type { ChartEntry, PriceLine, Week } from './api';
import { DASH, TOPIC_LABEL, type ThumbSize, date, dur, level, perWrap, quarter, thumb } from './format';

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

/**
 * Mentions per wrap in every quarter on record, so every row shares one x scale: the whole count
 * dotted, and the part of it inside bullish (green) and bearish (red) calls as solid lines on the
 * same y scale, so the gap under the dots is what no call classified. Lines stretch to the
 * column, a hairline marks each new year and a dot the chosen quarter. The SVG stretches; the
 * dot is HTML so it stays round. Each quarter is a hover target with all three figures.
 */
export function Spark({
  values,
  bullish = [],
  bearish = [],
  quarters,
  at,
  label,
  unit = 'mentions',
}: {
  values: number[];
  bullish?: number[];
  bearish?: number[];
  quarters: string[];
  at: number;
  label: string;
  unit?: string;
}) {
  if (values.length < 2) return <span className="spark-none">{DASH}</span>;
  const max = Math.max(...values, ...bullish, ...bearish, 0.0001);
  const x = (i: number) => (i * 100) / (values.length - 1);
  const y = (v: number) => 100 - (v / max) * 100;
  const line = (vs: number[]) => vs.map((v, i) => `${x(i)},${y(v)}`).join(' ');
  const half = 50 / (values.length - 1);
  return (
    <span className="spark" role="img" aria-label={label}>
      <svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
        {quarters.map((q, i) =>
          i > 0 && q.endsWith('-01-01') ? <line key={q} className="year" x1={x(i)} x2={x(i)} y1={0} y2={100} /> : null,
        )}
        <line className="base" x1={0} x2={100} y1={100} y2={100} />
        <polyline className="all" points={line(values)} />
        {bearish.length === values.length && <polyline className="down" points={line(bearish)} />}
        {bullish.length === values.length && <polyline className="up" points={line(bullish)} />}
      </svg>
      {at >= 0 && <span className="spark-dot" style={{ left: `${x(at)}%`, top: `${y(values[at])}%` }} />}
      {values.map((v, i) => {
        const l = Math.max(0, x(i) - half);
        const sides = bullish.length || bearish.length
          ? ` · ▲ ${perWrap(bullish[i] ?? 0)} bullish · ▼ ${perWrap(bearish[i] ?? 0)} bearish`
          : '';
        return (
          <span
            key={quarters[i] ?? i}
            className="spark-hit"
            style={{ left: `${l}%`, width: `${Math.min(100, x(i) + half) - l}%` }}
            title={`${quarters[i] ? quarter(quarters[i]) : ''}: ${perWrap(v)} ${unit} per wrap${sides}`}
          />
        );
      })}
    </span>
  );
}

/** The key to a Spark's three lines, drawn with the same strokes; and to the price strip. */
export function SparkKey({ unit = 'mentions', price = false }: { unit?: string; price?: boolean }) {
  const swatch = (cls: string) => (
    <svg className="spark-swatch" viewBox="0 0 20 8" aria-hidden="true">
      <line className={cls} x1={1} x2={19} y1={4} y2={4} />
    </svg>
  );
  const area = (
    <svg className="spark-swatch" viewBox="0 0 20 8" aria-hidden="true">
      <polygon className="px-area" points="1,3 19,1 19,8 1,8" />
      <line className="px" x1={1} x2={19} y1={3} y2={1} />
    </svg>
  );
  return (
    <span className="spark-key">
      <span>{swatch('all')} all {unit}</span>
      <span>{swatch('up')} ▲ in bullish calls</span>
      <span>{swatch('down')} ▼ in bearish calls</span>
      {price && (
        <>
          <span>{area} price, its own scale</span>
          <span>{swatch('ref')} 100 at the start, or zero</span>
        </>
      )}
    </span>
  );
}

/**
 * s03: a row's price, in its own strip under the mention lines: the same x scale (one point per
 * quarter, the quarter's last close), its own y scale, never a second axis on the Spark. A
 * performance line (Yahoo, baskets) is rebased to 100 at its first quarter and dashed at 100; a
 * level (FRED) is in its own units, dashed at zero when it crosses it. Each quarter is a hover
 * target, as on the Spark.
 */
export function PriceStrip({ line, quarters, at, href }: { line: PriceLine; quarters: string[]; at: number; href?: string | null }) {
  const name = href ? <Link to={href}>{line.label}</Link> : line.label;
  const head = (right: string, title?: string) => (
    <span className="price-head">
      <span className="price-lab">{name}</span>
      <span title={title}>{right}</span>
    </span>
  );
  if (line.mode === 'none')
    return <span className="price-strip none">{head('not priced', line.reason ?? undefined)}</span>;
  const pts = line.points;
  const known = pts.filter((v): v is number => v != null);
  if (known.length === 0 || quarters.length < 2 || pts.length !== quarters.length)
    return <span className="price-strip nodata">{head('no prices yet')}</span>;
  const perf = line.mode === 'performance';
  const showRef = perf || (Math.min(...known) < 0 && Math.max(...known) > 0);
  const ref = perf ? 100 : 0;
  let lo = Math.min(...known, ...(showRef ? [ref] : []));
  let hi = Math.max(...known, ...(showRef ? [ref] : []));
  if (hi - lo < 1e-9) {
    hi += 1;
    lo -= 1;
  }
  const x = (i: number) => (i * 100) / (quarters.length - 1);
  const y = (v: number) => 100 - ((v - lo) / (hi - lo)) * 100;
  // Consecutive quarters with a value; a gap breaks the line. Each run also fills down to the
  // strip's floor, so the price reads as an area and never as one more stance line.
  const runs: [number, number][][] = [];
  let run: [number, number][] = [];
  pts.forEach((v, i) => {
    if (v == null) {
      if (run.length) runs.push(run);
      run = [];
    } else run.push([x(i), y(v)]);
  });
  if (run.length) runs.push(run);
  const path = (r: [number, number][]) => r.map(([a, b]) => `${a},${b}`).join(' ');
  const base = pts.findIndex((v) => v != null);
  const fmt = (v: number) => (perf ? v.toFixed(0) : level(v));
  const what = perf ? `rebased, 100 = ${quarter(quarters[base])}` : 'a level';
  const tip = (v: number | null, i: number) =>
    `${quarter(quarters[i])}: ${line.label} ${v == null ? 'no price' : fmt(v)} · last close in the quarter, ${what}`;
  const half = 50 / (quarters.length - 1);
  const atV = at >= 0 ? pts[at] : null;
  return (
    <span
      className="price-strip"
      role="img"
      aria-label={`${line.label}, ${what}: ${pts.map((v, i) => `${quarter(quarters[i])} ${v == null ? 'none' : fmt(v)}`).join('; ')}`}
    >
      {head(`${fmt(known[0])} → ${fmt(known[known.length - 1])}`, line.name ?? undefined)}
      <span className="price-plot">
        <svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
          {runs.map((r) => (
            <polygon key={`a${path(r)}`} className="px-area" points={`${path(r)} ${r[r.length - 1][0]},100 ${r[0][0]},100`} />
          ))}
          {quarters.map((q, i) =>
            i > 0 && q.endsWith('-01-01') ? <line key={q} className="year" x1={x(i)} x2={x(i)} y1={0} y2={100} /> : null,
          )}
          {showRef && <line className="ref" x1={0} x2={100} y1={y(ref)} y2={y(ref)} />}
          {runs.map((r) => (
            <polyline key={path(r)} className="px" points={path(r)} />
          ))}
        </svg>
        {atV != null && <span className="spark-dot" style={{ left: `${x(at)}%`, top: `${y(atV)}%` }} />}
        {pts.map((v, i) => {
          const l = Math.max(0, x(i) - half);
          return (
            <span
              key={quarters[i] ?? i}
              className="spark-hit"
              style={{ left: `${l}%`, width: `${Math.min(100, x(i) + half) - l}%` }}
              title={tip(v, i)}
            />
          );
        })}
      </span>
    </span>
  );
}

/** The years along a column of Sparks, on the same x scale. */
export function SparkAxis({ quarters }: { quarters: string[] }) {
  if (quarters.length < 2) return null;
  return (
    <span className="spark-axis" aria-hidden="true">
      {quarters.map((q, i) =>
        q.endsWith('-01-01') ? (
          <span key={q} style={{ left: `${(i * 100) / (quarters.length - 1)}%` }}>
            {q.slice(0, 4)}
          </span>
        ) : null,
      )}
    </span>
  );
}

export function Move({ e }: { e: ChartEntry }) {
  if (e.move === 'none' || e.rank === null)
    return (
      <span className="move" title="Not mentioned this quarter">
        {DASH}
      </span>
    );
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
