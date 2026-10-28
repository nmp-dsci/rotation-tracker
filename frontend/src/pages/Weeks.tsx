import { useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import { type Week, api, useGet } from '../lib/api';
import { int, plural, year } from '../lib/format';
import { Loading, PageHead, Release } from '../lib/ui';

type Kind = 'all' | 'weekend' | 'fallback';

export function Weeks() {
  const { data, error } = useGet<Week[]>(api.weeks());
  const [params, setParams] = useSearchParams();
  const y = params.get('year');
  const kind = (params.get('kind') as Kind | null) ?? 'all';
  const q = params.get('q') ?? '';

  const set = (k: string, v: string | null) => {
    const next = new URLSearchParams(params);
    if (v) next.set(k, v);
    else next.delete(k);
    setParams(next, { replace: true });
  };

  const years = useMemo(() => [...new Set((data ?? []).map((w) => year(w.week_friday)))], [data]);
  const shown = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return (data ?? []).filter(
      (w) =>
        (!y || year(w.week_friday) === Number(y)) &&
        (kind === 'all' || w.reason === kind) &&
        (!needle || w.title.toLowerCase().includes(needle)),
    );
  }, [data, y, kind, q]);
  const byYear = useMemo(() => {
    const m = new Map<number, Week[]>();
    for (const w of shown) m.set(year(w.week_friday), [...(m.get(year(w.week_friday)) ?? []), w]);
    return [...m.entries()];
  }, [shown]);

  return (
    <div className="page">
      <PageHead eyebrow="pick/v1 · the last upload before Monday's New York open" title="Weekly wraps">
        <p className="lede">
          One video per trading week, picked from the Videos tab. A <b>weekend wrap</b> was uploaded between Friday's
          close and Monday's open; a <b>fallback</b> is the week's last recap when there was none.
        </p>
      </PageHead>

      <div className="filters" role="group" aria-label="Filter the weeks">
        <div className="chips-row" role="group" aria-label="Year">
          <button type="button" className="chip-btn" aria-pressed={!y} onClick={() => set('year', null)}>
            All years
          </button>
          {years.map((yr) => (
            <button key={yr} type="button" className="chip-btn" aria-pressed={y === String(yr)} onClick={() => set('year', String(yr))}>
              {yr}
            </button>
          ))}
        </div>
        <div className="chips-row" role="group" aria-label="Kind">
          {(['all', 'weekend', 'fallback'] as Kind[]).map((k) => (
            <button key={k} type="button" className="chip-btn" aria-pressed={kind === k} onClick={() => set('kind', k === 'all' ? null : k)}>
              {k === 'all' ? 'Every pick' : k === 'weekend' ? 'Weekend wraps' : 'Fallbacks'}
            </button>
          ))}
        </div>
        <label className="find">
          <span className="sr-only">Filter by title</span>
          <input type="text" value={q} placeholder="Filter titles…" onChange={(e) => set('q', e.target.value || null)} />
        </label>
      </div>

      {!data ? (
        <Loading error={error} what="the weeks" />
      ) : (
        <>
          <p className="count" aria-live="polite">
            {plural(shown.length, 'week')} of {int(data.length)}
          </p>
          {byYear.map(([yr, ws]) => (
            <section key={yr} className="year-block" aria-labelledby={`y${yr}`}>
              <h2 id={`y${yr}`} className="year">
                {yr}
                <span className="year-n">{plural(ws.length, 'week')}</span>
              </h2>
              <div className="releases">
                {ws.map((w) => (
                  <Release key={w.video_id} w={w} showYear={false} />
                ))}
              </div>
            </section>
          ))}
          {shown.length === 0 && <p className="empty">No week matches these filters.</p>}
        </>
      )}
    </div>
  );
}
