import { useSearchParams } from 'react-router-dom';
import { Link } from 'react-router-dom';
import { type Mentions as MentionsT, PLAYS, type Play, api, useGet } from '../lib/api';
import { int, plural } from '../lib/format';
import { MentionRow, PLAY_LABEL, PLAY_NOTE } from '../lib/mentions';
import { Loading, PageHead } from '../lib/ui';

const STEP = 100;
const KEYS = ['play', 'stance', 'speaker', 'modality', 'year', 'q', 'asset', 'week'] as const;

/** Every mention the miner kept, newest week first. The query string is the lens, so any view links. */
export function Mentions() {
  const [params, setParams] = useSearchParams();
  const get = (k: string) => params.get(k);
  const limit = Number(get('limit') ?? STEP);
  const filters = Object.fromEntries(KEYS.map((k) => [k, get(k)]));
  const { data, error } = useGet<MentionsT>(api.mentions({ ...filters, limit }));

  const set = (k: string, v: string | null) => {
    const next = new URLSearchParams(params);
    if (v) next.set(k, v);
    else next.delete(k);
    next.delete('limit');
    setParams(next, { replace: true });
  };
  const chips = (key: string, label: string, values: [string, string][]) => (
    <div className="chips-row" role="group" aria-label={label}>
      <button type="button" className="chip-btn" aria-pressed={!get(key)} onClick={() => set(key, null)}>
        All
      </button>
      {values.map(([v, text]) => (
        <button key={v} type="button" className="chip-btn" aria-pressed={get(key) === v} onClick={() => set(key, get(key) === v ? null : v)}>
          {text}
        </button>
      ))}
    </div>
  );
  const f = data?.facets;
  const n = (facet: keyof NonNullable<typeof f>, k: string) => (f ? ` ${int(f[facet][k] ?? 0)}` : '');

  return (
    <div className="page">
      <PageHead eyebrow={`${data?.version ?? 'play/v1'} · every commentary on price, located in the transcript`} title="Mentions">
        <p className="lede">
          One row per claim about an asset: the play, which way it points, the words he used and the second he said them.
          {data && (
            <>
              {' '}
              {int(data.coverage.mined)} of {int(data.coverage.weeks)} weeks mined so far. <Link to="/mining">How these were mined and measured →</Link>
            </>
          )}
        </p>
      </PageHead>

      <div className="filters" role="group" aria-label="Filter the mentions">
        {chips('play', 'Play', PLAYS.map((p: Play) => [p, `${PLAY_LABEL[p]}${n('play', p)}`]))}
        {chips('stance', 'Stance', [
          ['bullish', `↑ Bullish${n('stance', 'bullish')}`],
          ['bearish', `↓ Bearish${n('stance', 'bearish')}`],
          ['neutral', `· Neutral${n('stance', 'neutral')}`],
        ])}
        {chips('speaker', 'Speaker', [
          ['him', `His view${n('speaker', 'him')}`],
          ['reported', `Reported${n('speaker', 'reported')}`],
        ])}
        {chips('modality', 'Modality', [
          ['observed', 'Observed'],
          ['expected', 'Expected'],
          ['recommended', 'Recommended'],
        ])}
        {chips('year', 'Year', Object.keys(f?.year ?? {}).map((y) => [y, `${y}${n('year', y)}`]))}
        <label className="find">
          <span className="sr-only">Search the quotes</span>
          <input type="text" value={get('q') ?? ''} placeholder="Words in the quote…" onChange={(e) => set('q', e.target.value || null)} />
        </label>
      </div>
      {get('play') && <p className="count">{PLAY_LABEL[get('play') as Play]}: {PLAY_NOTE[get('play') as Play]}.</p>}
      {(get('asset') || get('week')) && (
        <p className="count">
          {get('asset') && (
            <>
              Asset <code>{get('asset')}</code>{' '}
              <button type="button" className="linkish" onClick={() => set('asset', null)}>
                clear
              </button>
            </>
          )}
          {get('week') && (
            <>
              {' '}
              Week <code>{get('week')}</code>{' '}
              <button type="button" className="linkish" onClick={() => set('week', null)}>
                clear
              </button>
            </>
          )}
        </p>
      )}

      {!data ? (
        <Loading error={error} what="the mentions" />
      ) : (
        <>
          <p className="count" aria-live="polite">
            {plural(data.rows.length, 'mention')}
            {data.rows.length < data.total ? ` of ${int(data.total)}` : ''}
          </p>
          <ol className="hits">
            {data.rows.map((m) => (
              <MentionRow key={m.id} m={m} />
            ))}
          </ol>
          {data.rows.length === 0 && <p className="empty">No mention matches these filters.</p>}
          {data.rows.length < data.total && (
            <p>
              <button
                type="button"
                className="pill ghost"
                onClick={() => {
                  const next = new URLSearchParams(params);
                  next.set('limit', String(limit + STEP));
                  setParams(next, { replace: true });
                }}
              >
                Show {Math.min(STEP, data.total - data.rows.length)} more
              </button>
            </p>
          )}
        </>
      )}
    </div>
  );
}
