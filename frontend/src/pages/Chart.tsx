import { Link, useSearchParams } from 'react-router-dom';
import { type Chart, api, useGet } from '../lib/api';
import { int, quarter } from '../lib/format';
import { Loading, Move, PageHead, Spark } from '../lib/ui';

export function ChartPage() {
  const [params, setParams] = useSearchParams();
  const wanted = params.get('quarter');
  const { data, error } = useGet<Chart>(api.chart(wanted));
  const go = (q: string | null) => {
    const next = new URLSearchParams(params);
    if (q) next.set('quarter', q);
    else next.delete('quarter');
    setParams(next, { replace: true });
  };

  return (
    <div className="page">
      <PageHead eyebrow={data ? `${quarter(data.quarter)} · ${data.version}` : 'themes/v0'} title="The chart">
        <div className="callout warn">
          <p>
            <span className="badge warn">! not a signal</span> Keyword counts over the <b>macro & flows</b> and{' '}
            <b>no chapters</b> sections: how often each theme came up per weekly wrap. They are not rotation calls.
            Extraction and the taxonomy are still open decisions, so nothing here feeds a backtest.
          </p>
        </div>
      </PageHead>

      {!data ? (
        <Loading error={error} what="the chart" />
      ) : (
        <>
          <QuarterPicker data={data} go={go} />
          <ol className="chart-rows">
            {data.entries.map((e) => (
              <li key={e.theme} className="chart-row">
                <span className="c-rank">{e.rank}</span>
                <span className="c-move">
                  <Move e={e} />
                </span>
                <span className="c-name">
                  {e.theme}
                  <span className="c-sub">
                    {int(e.mentions)} mentions · in {e.weeks_hit} of {data.weeks_in_quarter} wraps
                    {e.prev_rank ? ` · last quarter #${e.prev_rank}` : ''}
                  </span>
                </span>
                <span className="c-spark">
                  <Spark
                    values={e.history}
                    label={`${e.theme}, mentions per wrap: ${e.history
                      .map((v, i) => `${quarter(data.history_quarters[i] ?? data.quarter)} ${v.toFixed(1)}`)
                      .join(', ')}`}
                  />
                </span>
                <span className="c-rate">
                  {e.rate.toFixed(1)}
                  <small>per wrap</small>
                </span>
              </li>
            ))}
          </ol>
          {data.dropped.length > 0 && (
            <p className="dropped">
              <span className="label">Off the chart since {data.previous ? quarter(data.previous) : 'last quarter'}</span>{' '}
              {data.dropped.join(' · ')}
            </p>
          )}
          <p className="small">
            Sparklines: mentions per wrap over the last {data.history_quarters.length} quarters, from{' '}
            {quarter(data.history_quarters[0])}. Search any theme on the <Link to="/search">search page</Link> to read
            the sections behind a number.
          </p>
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
        </>
      )}
    </div>
  );
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
