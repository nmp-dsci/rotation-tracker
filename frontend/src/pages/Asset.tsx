import { useMemo } from 'react';
import { Link, useParams } from 'react-router-dom';
import { type AssetDetail, type StripCell, api, useGet } from '../lib/api';
import { date, int, plural, year } from '../lib/format';
import { MentionRow, PLAY_LABEL } from '../lib/mentions';
import { Loading, PageHead } from '../lib/ui';
import { KIND_LABEL } from './Assets';

/** A week's cell: ↑ net bullish, ↓ net bearish, ± both, · mined and silent, blank not mined yet. */
function cell(c: StripCell): { glyph: string; cls: string; tip: string } {
  const when = date(c.week_friday);
  if (!c.mined) return { glyph: '', cls: 'unmined', tip: `${when}: not mined yet` };
  const n = c.up + c.down + c.flat;
  if (!n) return { glyph: '·', cls: 'quiet', tip: `${when}: no mention` };
  const parts = [c.up && `${c.up} bullish`, c.down && `${c.down} bearish`, c.flat && `${c.flat} neutral`].filter(Boolean).join(', ');
  const rot = c.rotation ? `, ${plural(c.rotation, 'rotation call')}` : '';
  const tip = `${when}: ${parts}${rot}`;
  if (c.up > c.down) return { glyph: '↑', cls: 'up', tip };
  if (c.down > c.up) return { glyph: '↓', cls: 'down', tip };
  return { glyph: '±', cls: 'mixed', tip };
}

export function AssetPage() {
  const { id = '' } = useParams();
  const { data, error, status } = useGet<AssetDetail>(api.asset(id));
  const years = useMemo(() => {
    const m = new Map<number, StripCell[]>();
    for (const c of data?.strip ?? []) m.set(year(c.week_friday), [...(m.get(year(c.week_friday)) ?? []), c]);
    return [...m.entries()];
  }, [data]);

  if (status === 404)
    return (
      <div className="page">
        <PageHead eyebrow="assets/v1" title="Not in the map" />
        <p>
          <code>{id}</code> is not an asset in assets/v1. <Link to="/assets">Browse the assets</Link>.
        </p>
      </div>
    );
  if (!data) return <div className="page"><Loading error={error} what="the asset" /></div>;
  const a = data.asset;
  const up = data.strip.reduce((s, c) => s + c.up, 0);
  const down = data.strip.reduce((s, c) => s + c.down, 0);
  const weeks = data.strip.filter((c) => c.up + c.down + c.flat > 0).length;
  const mined = data.strip.filter((c) => c.mined).length;

  return (
    <div className="page asset-page">
      <PageHead eyebrow={`${KIND_LABEL[a.kind] ?? a.kind} · ${a.id} · proxy ${a.proxy ?? 'none'}`} title={a.name}>
        <p className="lede">
          {a.gics_sector && (
            <>
              GICS {a.gics_sector}
              {a.gics_sub_industry ? ` · ${a.gics_sub_industry}` : ''}.{' '}
            </>
          )}
          {a.sp500 && <>In the S&amp;P 500{a.sp500_added ? ` since ${date(a.sp500_added)}` : ''}. </>}
          {a.ndx && <>In the Nasdaq-100. </>}
          {data.aliases.length > 0 && (
            <>
              Said as{' '}
              {data.aliases.slice(0, 14).map((al, i) => (
                <span key={al}>
                  {i ? ', ' : ''}“{al}”
                </span>
              ))}
              {data.aliases.length > 14 ? ` and ${data.aliases.length - 14} more` : ''}.
            </>
          )}
        </p>
      </PageHead>

      <section className="figures" aria-label="Totals">
        <div className="figure">
          <span className="f-n">{int(data.total)}</span>
          <span className="f-l">mentions</span>
        </div>
        <div className="figure">
          <span className="f-n">{int(weeks)}</span>
          <span className="f-l">of {int(mined)} mined weeks mention it</span>
        </div>
        <div className="figure">
          <span className="f-n bull">↑ {int(up)}</span>
          <span className="f-l">bullish (rotation in counts here)</span>
        </div>
        <div className="figure">
          <span className="f-n bear">↓ {int(down)}</span>
          <span className="f-l">bearish (rotation out counts here)</span>
        </div>
      </section>

      <section className="band" aria-labelledby="strip-h">
        <div className="band-head slim">
          <h2 id="strip-h" className="display-3">
            Week by week
          </h2>
        </div>
        <p className="strip-legend">
          <span>
            <span className="sc up">↑</span> net bullish
          </span>
          <span>
            <span className="sc down">↓</span> net bearish
          </span>
          <span>
            <span className="sc mixed">±</span> both
          </span>
          <span>
            <span className="sc quiet">·</span> mined, not mentioned
          </span>
          <span>
            <span className="sc unmined" /> not mined yet
          </span>
        </p>
        {years.map(([yr, cells]) => (
          <div key={yr} className="strip-row">
            <span className="strip-y">{yr}</span>
            <div className="strip" role="list" aria-label={`${yr}, week by week`}>
              {cells.map((c) => {
                const k = cell(c);
                return k.cls === 'up' || k.cls === 'down' || k.cls === 'mixed' ? (
                  <Link key={c.video_id} role="listitem" to={`/mentions?asset=${encodeURIComponent(a.id)}&week=${c.video_id}`} className={`sc ${k.cls}`} title={k.tip} aria-label={k.tip}>
                    {k.glyph}
                  </Link>
                ) : (
                  <span key={c.video_id} role="listitem" className={`sc ${k.cls}`} title={k.tip} aria-label={k.tip}>
                    {k.glyph}
                  </span>
                );
              })}
            </div>
          </div>
        ))}
        <details className="as-table">
          <summary>Table view</summary>
          <div className="tablewrap">
            <table>
              <thead>
                <tr>
                  <th>Week</th>
                  <th className="n">
                    <span className="stance bullish">↑</span>
                    <span className="sr-only"> bullish</span>
                  </th>
                  <th className="n">
                    <span className="stance bearish">↓</span>
                    <span className="sr-only"> bearish</span>
                  </th>
                  <th className="n">·</th>
                  <th className="n">Rotation</th>
                </tr>
              </thead>
              <tbody>
                {data.strip
                  .filter((c) => c.up + c.down + c.flat > 0)
                  .map((c) => (
                    <tr key={c.video_id}>
                      <td className="k">{date(c.week_friday)}</td>
                      <td className={`n${c.up ? ' bull' : ''}`}>{c.up}</td>
                      <td className={`n${c.down ? ' bear' : ''}`}>{c.down}</td>
                      <td className="n">{c.flat}</td>
                      <td className="n">{c.rotation}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </details>
      </section>

      <section className="band" aria-labelledby="m-h">
        <div className="band-head slim">
          <h2 id="m-h" className="display-3">
            What he said
          </h2>
          <span className="count">
            {Object.entries(data.by_play)
              .map(([p, n]) => `${PLAY_LABEL[p as keyof typeof PLAY_LABEL] ?? p} ${n}`)
              .join(' · ')}
          </span>
        </div>
        <ol className="hits">
          {data.mentions.map((m) => (
            <MentionRow key={m.id} m={m} />
          ))}
        </ol>
        {data.mentions.length === 0 && <p className="empty">No mention of this asset in the mined weeks yet.</p>}
      </section>
    </div>
  );
}
