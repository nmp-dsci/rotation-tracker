import { Link, useSearchParams } from 'react-router-dom';
import { type Chart, type ChartEntry, api, useGet } from '../lib/api';
import { DASH, int, perWrap, quarter } from '../lib/format';
import { Loading, Move, PageHead, Spark, SparkAxis, SparkKey } from '../lib/ui';
import { KIND_LABEL } from './Assets';

/**
 * Everything, not a top ten: every keyword theme, or every asset the miner found a call on,
 * each with its three lines over all time. Sorted by this quarter (what is talked about now)
 * or by all time (what has been, spikes included); filtered by layer and by name.
 */
export function ChartPage() {
  const [params, setParams] = useSearchParams();
  const wanted = params.get('quarter');
  const view = params.get('view') === 'assets' ? 'assets' : 'themes';
  const order = params.get('order') === 'all' ? 'all' : 'quarter';
  const kind = params.get('kind');
  const q = params.get('q') ?? '';
  const { data, error } = useGet<Chart>(api.chart(wanted, view === 'assets' ? view : null));
  const set = (changes: Record<string, string | null>) => {
    const next = new URLSearchParams(params);
    for (const [k, v] of Object.entries(changes)) {
      if (v) next.set(k, v);
      else next.delete(k);
    }
    setParams(next, { replace: true });
  };
  const unit = view === 'assets' ? 'calls' : 'mentions';
  const rows = data ? pick(data.entries, kind, q, order) : [];
  const kinds = data && view === 'assets' ? count(data.entries) : [];

  return (
    <div className="page">
      <PageHead
        eyebrow={data ? `${quarter(data.quarter)} · ${data.version}` : 'the chart'}
        title="The chart"
      >
        <div className="callout warn">
          <p>
            <span className="badge warn">! not a signal</span> <b>Keyword themes</b> count how often each theme came up
            per weekly wrap in the <b>macro & flows</b> and <b>no chapters</b> sections. <b>Assets</b> count{' '}
            <Link to="/mentions">the miner's calls</Link> on each asset per wrap. Green and red split either by the
            stance of those calls; none of it is checked against prices yet, so nothing here feeds a backtest.
          </p>
        </div>
      </PageHead>

      <div className="filters" role="group" aria-label="What the chart lists">
        <div className="chips-row" role="group" aria-label="List">
          <button type="button" className="chip-btn" aria-pressed={view === 'themes'} onClick={() => set({ view: null, kind: null })}>
            Keyword themes
          </button>
          <button type="button" className="chip-btn" aria-pressed={view === 'assets'} onClick={() => set({ view: 'assets' })}>
            Assets the miner found
          </button>
        </div>
        <div className="chips-row" role="group" aria-label="Order">
          <button type="button" className="chip-btn" aria-pressed={order === 'quarter'} onClick={() => set({ order: null })}>
            This quarter first
          </button>
          <button type="button" className="chip-btn" aria-pressed={order === 'all'} onClick={() => set({ order: 'all' })}>
            All time first
          </button>
        </div>
        <label className="find">
          <span className="sr-only">Find a {view === 'assets' ? 'asset' : 'theme'}</span>
          <input
            type="text"
            value={q}
            placeholder={`Find ${view === 'assets' ? 'an asset' : 'a theme'}…`}
            onChange={(e) => set({ q: e.target.value || null })}
          />
        </label>
      </div>
      {kinds.length > 0 && (
        <div className="chips-row chart-kinds" role="group" aria-label="Layer">
          <button type="button" className="chip-btn" aria-pressed={!kind} onClick={() => set({ kind: null })}>
            Every layer
          </button>
          {kinds.map(([k, n]) => (
            <button key={k} type="button" className="chip-btn" aria-pressed={kind === k} onClick={() => set({ kind: kind === k ? null : k })}>
              {KIND_LABEL[k] ?? k} {int(n)}
            </button>
          ))}
        </div>
      )}

      {!data ? (
        <Loading error={error} what="the chart" />
      ) : (
        <>
          <QuarterPicker data={data} go={(qq) => set({ quarter: qq })} />
          <p className="small chart-count">
            {int(rows.length)} of {int(data.entries.length)} {view === 'assets' ? 'assets' : 'themes'}, ranked by{' '}
            {unit} per wrap in {quarter(data.quarter)}
            {order === 'all' ? `, listed by ${unit} over all time` : ''}. # is the rank this quarter; {DASH} means not
            mentioned in it.
          </p>
          <div className="chart-row chart-axis">
            <span className="c-name">
              <span className="c-sub">{view === 'assets' ? 'Calls' : 'Mentions'} per wrap, every quarter</span>
              <SparkKey unit={unit} />
            </span>
            <span className="c-spark">
              <SparkAxis quarters={data.history_quarters} />
            </span>
          </div>
          <ol className="chart-rows">
            {rows.map((e) => (
              <li key={e.id} className={`chart-row${e.rank === null ? ' quiet' : ''}`}>
                <span className="c-rank">{e.rank ?? DASH}</span>
                <span className="c-move">
                  <Move e={e} />
                </span>
                <span className="c-name">
                  {view === 'assets' ? <Link to={`/assets/${encodeURIComponent(e.id)}`}>{e.theme}</Link> : e.theme}
                  <span className="c-sub">
                    {e.kind && <>{KIND_LABEL[e.kind] ?? e.kind} · </>}
                    {e.rank === null
                      ? `none in ${quarter(data.quarter)}`
                      : `${int(e.mentions)} ${unit} · in ${e.weeks_hit} of ${data.weeks_in_quarter} wraps${e.prev_rank ? ` · last quarter #${e.prev_rank}` : ''}`}
                    {` · ${int(e.total)} all time`}
                  </span>
                </span>
                <span className="c-spark">
                  <Spark
                    values={e.history}
                    bullish={e.bullish}
                    bearish={e.bearish}
                    quarters={data.history_quarters}
                    at={data.history_quarters.indexOf(data.quarter)}
                    unit={unit}
                    label={`${e.theme}, ${unit} per wrap, then in bullish and bearish calls: ${e.history
                      .map(
                        (v, i) =>
                          `${quarter(data.history_quarters[i] ?? data.quarter)} ${perWrap(v)}, ${perWrap(e.bullish[i] ?? 0)} up, ${perWrap(e.bearish[i] ?? 0)} down`,
                      )
                      .join('; ')}`}
                  />
                </span>
                <span className="c-rate">
                  {e.rank === null ? DASH : perWrap(e.rate)}
                  <small>per wrap</small>
                </span>
              </li>
            ))}
          </ol>
          {rows.length === 0 && <p className="empty">Nothing matches.</p>}
          <p className="small">
            Sparklines: all {data.history_quarters.length} quarters, {quarter(data.history_quarters[0])} to{' '}
            {quarter(data.history_quarters[data.history_quarters.length - 1])}, on one time scale down the page; each
            row has its own height scale, shared by its three lines.{' '}
            {view === 'assets' ? (
              <>
                Dotted: every call naming the asset, per wrap. Green: the calls bullish on it; red: bearish. The gap
                under the dots is neutral calls.
              </>
            ) : (
              <>
                Dotted: every mention per wrap. Green: the mentions inside a call the miner read as bullish on that
                theme's asset; red: bearish. The gap under the dots is mentions in neutral or mixed calls, or in no
                call at all.
              </>
            )}{' '}
            The dot marks {quarter(data.quarter)}; hover a line for any quarter's figures.
            {view === 'themes' && (
              <>
                {' '}
                Search any theme on the <Link to="/search">search page</Link> to read the sections behind a number.
              </>
            )}
          </p>
          {view === 'themes' && (
            <details className="facts">
              <summary>How each theme is matched</summary>
              <div className="tablewrap">
                <table>
                  <thead>
                    <tr>
                      <th>Theme</th>
                      <th>Whole-word pattern, case-insensitive</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.themes.map((t) => (
                      <tr key={t.name}>
                        <td>{t.name}</td>
                        <td className="k">{t.pattern}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </details>
          )}
        </>
      )}
    </div>
  );
}

/** The rows to show: filtered by layer and name, in the chosen order (the API sends this quarter's). */
function pick(entries: ChartEntry[], kind: string | null, q: string, order: 'quarter' | 'all'): ChartEntry[] {
  const needle = q.trim().toLowerCase();
  const out = entries.filter(
    (e) => (!kind || e.kind === kind) && (!needle || e.theme.toLowerCase().includes(needle) || e.id.toLowerCase().includes(needle)),
  );
  return order === 'all' ? [...out].sort((a, b) => b.total - a.total || a.theme.localeCompare(b.theme)) : out;
}

/** Layers on the list, most assets first. */
function count(entries: ChartEntry[]): [string, number][] {
  const n = new Map<string, number>();
  for (const e of entries) if (e.kind) n.set(e.kind, (n.get(e.kind) ?? 0) + 1);
  return [...n].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
}

function QuarterPicker({ data, go }: { data: Chart; go: (q: string | null) => void }) {
  const i = data.quarters.findIndex((q) => q.quarter === data.quarter);
  const prev = data.quarters[i - 1];
  const next = data.quarters[i + 1];
  const here = data.quarters[i];
  return (
    <div className="qpick">
      <button type="button" className="pill ghost" disabled={!prev} onClick={() => prev && go(prev.quarter)}>
        ← {prev ? quarter(prev.quarter) : 'start'}
      </button>
      <label>
        <span className="sr-only">Quarter</span>
        <select value={data.quarter} onChange={(e) => go(e.target.value)}>
          {data.quarters.map((q) => (
            <option key={q.quarter} value={q.quarter}>
              {quarter(q.quarter)} · {q.weeks} wraps{q.closed ? '' : ' · in progress'}
            </option>
          ))}
        </select>
      </label>
      <button type="button" className="pill ghost" disabled={!next} onClick={() => next && go(next.quarter)}>
        {next ? quarter(next.quarter) : 'latest'} →
      </button>
      {here && !here.closed && <span className="badge info">◔ in progress: {here.weeks} weeks so far</span>}
    </div>
  );
}
