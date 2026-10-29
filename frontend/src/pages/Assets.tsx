import { Link, useSearchParams } from 'react-router-dom';
import { type Assets as AssetsT, api, useGet } from '../lib/api';
import { date, int, plural } from '../lib/format';
import { Loading, PageHead } from '../lib/ui';

export const KIND_LABEL: Record<string, string> = {
  index: 'Indexes',
  sector: 'GICS sectors',
  theme: 'Themes',
  stock: 'Stocks',
  fund: 'Funds',
  crypto: 'Crypto',
  rates: 'Rates',
  credit: 'Credit',
  commodity: 'Commodities',
  fx: 'FX',
  macro: 'Macro',
};

/** assets/v1, ranked by how often the mined weeks talk about each one. */
export function Assets() {
  const [params, setParams] = useSearchParams();
  const kind = params.get('kind');
  const q = params.get('q') ?? '';
  const { data, error } = useGet<AssetsT>(api.assets(kind, q || null));
  const set = (k: string, v: string | null) => {
    const next = new URLSearchParams(params);
    if (v) next.set(k, v);
    else next.delete(k);
    setParams(next, { replace: true });
  };
  const universe = data?.universe.reduce((s, u) => s + u.n, 0) ?? 0;

  return (
    <div className="page">
      <PageHead eyebrow="assets/v1 · every mention resolves to one of these" title="Assets">
        <p className="lede">
          The asset map: indexes, GICS sectors, trader themes, any US-listed stock or fund, crypto, rates, credit,
          commodities, currencies and macro. Each row carries the proxy whose price will score its mentions.
          {data && <> The map holds {int(universe)} assets; {plural(data.rows.length, 'asset')} have been mentioned.</>}
        </p>
      </PageHead>
      <div className="filters" role="group" aria-label="Filter the assets">
        <div className="chips-row" role="group" aria-label="Layer">
          <button type="button" className="chip-btn" aria-pressed={!kind} onClick={() => set('kind', null)}>
            Every layer
          </button>
          {(data?.kinds ?? []).map((k) => (
            <button key={k.kind} type="button" className="chip-btn" aria-pressed={kind === k.kind} onClick={() => set('kind', kind === k.kind ? null : k.kind)}>
              {KIND_LABEL[k.kind] ?? k.kind} {int(k.assets)}
            </button>
          ))}
        </div>
        <label className="find">
          <span className="sr-only">Find an asset</span>
          <input type="text" value={q} placeholder="Find an asset…" onChange={(e) => set('q', e.target.value || null)} />
        </label>
      </div>
      {!data ? (
        <Loading error={error} what="the assets" />
      ) : (
        <div className="tablewrap">
          <table className="asset-table">
            <thead>
              <tr>
                <th>Asset</th>
                <th>Layer</th>
                <th>Proxy</th>
                <th className="n">Mentions</th>
                <th className="n">Weeks</th>
                <th className="n">
                  <span className="stance bullish">↑</span> Bullish
                </th>
                <th className="n">
                  <span className="stance bearish">↓</span> Bearish
                </th>
                <th className="n">Rotation</th>
                <th>Last</th>
              </tr>
            </thead>
            <tbody>
              {data.rows.map((a) => (
                <tr key={a.id}>
                  <td>
                    <Link to={`/assets/${encodeURIComponent(a.id)}`}>{a.name}</Link>{' '}
                    {a.sp500 && <span className="tag">S&amp;P 500</span>} {a.ndx && <span className="tag">NDX</span>}
                  </td>
                  <td className="layer">{KIND_LABEL[a.kind] ?? a.kind}</td>
                  <td className="mono">{a.proxy ?? 'none'}</td>
                  <td className="n">{int(a.mentions)}</td>
                  <td className="n">{int(a.weeks)}</td>
                  <td className={`n${a.bullish ? ' bull' : ''}`}>{int(a.bullish)}</td>
                  <td className={`n${a.bearish ? ' bear' : ''}`}>{int(a.bearish)}</td>
                  <td className="n">{int(a.rotation)}</td>
                  <td className="mono">{date(a.last_week)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {data.rows.length === 0 && <p className="empty">No mentioned asset matches.</p>}
        </div>
      )}
    </div>
  );
}
