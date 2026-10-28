import { Link } from 'react-router-dom';
import { type Chart, type Overview, type Week, api, useGet } from '../lib/api';
import { compact, int, quarter, stamp } from '../lib/format';
import { stages } from '../lib/stages';
import { Cover, Loading, Move, Release } from '../lib/ui';

export function Home() {
  const { data, error } = useGet<Overview>(api.overview());
  const chart = useGet<Chart>(api.chart());
  const weeks = useGet<Week[]>(api.weeks());
  if (!data) {
    return (
      <div className="page">
        <Loading error={error} what="the overview" />
      </div>
    );
  }
  const s = data.status;
  const latest = data.latest[0];
  const hours = data.totals.seconds / 3600;
  return (
    <>
      <section className="hero" aria-labelledby="hero-title">
        <div className="hero-media" aria-hidden="true">
          <div className="mosaic">
            {(weeks.data ?? data.latest).slice(0, 120).map((w) => (
              <Cover key={w.video_id} id={w.video_id} size="mq" eager />
            ))}
          </div>
        </div>
        <div className="hero-scrim" aria-hidden="true" />
        <div className="hero-in">
          <div>
            <p className="kicker">{data.channel.name} · weekly market wraps</p>
            <h1 id="hero-title" className="display hero-title">
              Money on
              <br />
              the move
            </h1>
          </div>
          <div className="hero-foot">
            <p className="hero-sub">{int(s.picks)} weekly wraps</p>
            <div className="hero-cta">
              <span className="stamp">
                {stamp(s.first_week)} — {stamp(s.last_week)}
              </span>
              {latest && (
                <Link className="pill ghost" to={`/weeks/${latest.video_id}`}>
                  Latest wrap
                </Link>
              )}
            </div>
          </div>
        </div>
      </section>

      <div className="page">
        <section className="figures" aria-label="The corpus in numbers">
          <Figure n={int(s.transcripts)} l={`transcripts, one per trading week since ${stamp(s.first_week)}`} />
          <Figure n={int(s.sections)} l={`chapter sections, ${int(data.topics['macro-flows'])} of them macro & flows`} />
          <Figure n={compact(data.totals.words)} l="words of market commentary" />
          <Figure n={int(hours)} l="hours of video" />
        </section>

        <section className="band">
          <div className="band-head">
            <h2 className="display-2">Latest</h2>
            <Link className="more" to="/weeks">
              All {int(s.picks)} weeks →
            </Link>
          </div>
          <div className="releases">
            {data.latest.map((w) => (
              <Release key={w.video_id} w={w} />
            ))}
          </div>
        </section>

        <section className="band">
          <div className="band-head">
            <h2 className="display-2">The chart</h2>
            <Link className="more" to="/chart">
              Full chart →
            </Link>
          </div>
          {chart.data ? (
            <>
              <p className="lede">
                Themes ranked by mentions per weekly wrap, {quarter(chart.data.quarter)}. Keyword counts over the macro &
                flows sections, not rotation calls.
              </p>
              <ol className="chart-rows compact">
                {chart.data.entries.slice(0, 5).map((e) => (
                  <li key={e.theme} className="chart-row">
                    <span className="c-rank">{e.rank}</span>
                    <span className="c-move">
                      <Move e={e} />
                    </span>
                    <span className="c-name">{e.theme}</span>
                    <span className="c-rate">
                      {e.rate.toFixed(1)}
                      <small>per wrap</small>
                    </span>
                  </li>
                ))}
              </ol>
            </>
          ) : (
            <Loading error={chart.error} what="the chart" />
          )}
        </section>

        <section className="band">
          <div className="band-head">
            <h2 className="display-2">Built so far</h2>
            <Link className="more" to="/pipeline">
              Liner notes →
            </Link>
          </div>
          <ol className="tracks">
            {stages(s).map((st) => (
              <li key={st.n} className={`track stage ${st.state}`}>
                <span className="t-n">{String(st.n).padStart(2, '0')}</span>
                <span className="t-title">
                  <b>{st.name}</b>
                  <span className="t-sub">{st.did}</span>
                </span>
                <span className="t-end">
                  {st.state === 'built' ? (
                    <span className="badge ok">✓ built</span>
                  ) : st.state === 'next' ? (
                    <span className="badge info">→ next</span>
                  ) : (
                    <span className="badge">○ planned</span>
                  )}
                </span>
              </li>
            ))}
          </ol>
        </section>
      </div>
    </>
  );
}

function Figure({ n, l }: { n: string; l: string }) {
  return (
    <div className="figure">
      <span className="f-n">{n}</span>
      <span className="f-l">{l}</span>
    </div>
  );
}
