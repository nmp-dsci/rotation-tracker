import { type Pipeline as P, api, useGet } from '../lib/api';
import { DASH, bytes, date, dur, et, int, plural } from '../lib/format';
import { stages } from '../lib/stages';
import { Bars, Loading, PageHead, Ticks } from '../lib/ui';

const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

/** The template's credits page: who and what made each part, and what it cost. */
export function Pipeline() {
  const { data, error } = useGet<P>(api.pipeline());
  return (
    <div className="page">
      <PageHead eyebrow="M1 · data pipeline · ai_specs/s00_data_pipeline.md" title="Liner notes">
        <p className="lede">
          What has been built so far, where each part lives, and what it cost. Every number on this page is read live
          from Postgres, Chroma, MLflow and Supadata.
        </p>
      </PageHead>
      {!data ? <Loading error={error} what="the pipeline" /> : <Notes d={data} />}
    </div>
  );
}

function Notes({ d }: { d: P }) {
  const s = d.status;
  const spent = d.batches.reduce((n, b) => n + b.indexed, 0);
  const left = d.credits?.reduce((n, c) => n + c.left, 0);
  const evening = d.hours_et.slice(19).reduce((a, b) => a + b, 0) + d.hours_et.slice(0, 3).reduce((a, b) => a + b, 0);
  const dated = d.hours_et.reduce((a, b) => a + b, 0);
  return (
    <>
      <section className="band" aria-labelledby="tracks-h">
        <h2 id="tracks-h" className="display-3">
          Tracks
        </h2>
        <ol className="tracks">
          {stages(s).map((st) => (
            <li key={st.n} className={`track stage ${st.state}`}>
              <span className="t-n">{String(st.n).padStart(2, '0')}</span>
              <span className="t-title">
                <b>{st.name}</b>
                <span className="t-sub">{st.did}</span>
                {st.store && <span className="t-store mono">{st.store}</span>}
              </span>
              <span className="t-end">
                {st.cmd && <code>{st.cmd}</code>}
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

      <section className="band" aria-labelledby="cost-h">
        <h2 id="cost-h" className="display-3">
          Credits
        </h2>
        <div className="figures">
          <div className="figure">
            <span className="f-n">{int(spent)}</span>
            <span className="f-l">Supadata credits spent: one per transcript, nothing re-fetched</span>
          </div>
          <div className="figure">
            <span className="f-n">{left == null ? DASH : int(left)}</span>
            <span className="f-l">credits left across {d.credits ? plural(d.credits.length, 'key') : 'the keys'}</span>
          </div>
          <div className="figure">
            <span className="f-n">0</span>
            <span className="f-l">model calls: summaries come from the video description</span>
          </div>
        </div>
        {d.credits ? (
          <ul className="meters">
            {d.credits.map((c) => (
              <li key={c.key}>
                <span className="m-label">
                  Key {c.key} · {c.plan}
                </span>
                <span className="meter" role="img" aria-label={`${c.left} of ${c.max} credits left`}>
                  <span style={{ width: `${(c.left / Math.max(1, c.max)) * 100}%` }} />
                </span>
                <span className="m-n">
                  {int(c.left)} / {int(c.max)} left
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="callout warn">
            <span className="badge warn">○ unknown</span> Supadata did not answer: {d.credits_error}
          </p>
        )}
      </section>

      <section className="band cols" aria-labelledby="stores-h">
        <div>
          <h2 id="stores-h" className="display-3">
            Postgres
          </h2>
          <p className="small">
            Database <code>rotation</code>, schema <code>rt</code>, read here as <code>rotation_ro</code>.
          </p>
          <div className="tablewrap">
            <table>
              <thead>
                <tr>
                  <th>Table</th>
                  <th className="num">Rows</th>
                  <th className="num">Size</th>
                </tr>
              </thead>
              <tbody>
                {d.tables.map((t) => (
                  <tr key={t.name}>
                    <td className="k">{t.name}</td>
                    <td className="n num">{int(t.rows)}</td>
                    <td className="n num">{bytes(t.bytes)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
        <div>
          <h2 className="display-3">Chroma</h2>
          <p className="small">
            transcript·lab's store, opened read-only: <code className="wrap-any">{d.chroma.path}</code>
          </p>
          {d.chroma.error ? (
            <p className="callout red">
              <span className="badge bad">✕ unreadable</span> {d.chroma.error}
            </p>
          ) : (
            <div className="tablewrap">
              <table>
                <thead>
                  <tr>
                    <th>Collection</th>
                    <th className="num">This project</th>
                    <th className="num">Whole store</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td className="k">raw_transcripts</td>
                    <td className="n num">{int(d.chroma.raw_ours)}</td>
                    <td className="n num">{int(d.chroma.raw_total)}</td>
                  </tr>
                  <tr>
                    <td className="k">transcript_chunks</td>
                    <td className="n num">{int(d.chroma.chunks_ours)}</td>
                    <td className="n num">{int(d.chroma.chunks_total)}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          )}
        </div>
      </section>

      <section className="band cols" aria-labelledby="runs-h">
        <div>
          <h2 id="runs-h" className="display-3">
            Ingest batches
          </h2>
          <div className="tablewrap">
            <table>
              <thead>
                <tr>
                  <th>Batch</th>
                  <th className="num">Indexed</th>
                  <th className="num">Took</th>
                </tr>
              </thead>
              <tbody>
                {d.batches.map((b) => (
                  <tr key={b.batch_id}>
                    <td className="k">{b.batch_id}</td>
                    <td className="n num">
                      {b.indexed} / {b.n}
                    </td>
                    <td className="n num">
                      {b.finished ? dur((new Date(b.finished).getTime() - new Date(b.started).getTime()) / 1000) : DASH}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
        <div>
          <h2 className="display-3">MLflow</h2>
          <p className="small">
            Experiment <code>{d.experiment}</code> on the central server.{' '}
            {d.mlflow_url ? (
              <a href={d.mlflow_url} target="_blank" rel="noreferrer">
                Open it ↗
              </a>
            ) : (
              <span className="badge warn">○ MLflow down</span>
            )}
          </p>
          <div className="tablewrap">
            <table>
              <thead>
                <tr>
                  <th>Run</th>
                  <th>Kind</th>
                  <th className="num">Credits</th>
                </tr>
              </thead>
              <tbody>
                {d.runs.map((r) => (
                  <tr key={r.run_id}>
                    <td>
                      <a href={r.url} target="_blank" rel="noreferrer">
                        {r.name ?? r.run_id}
                      </a>
                      <span className="tag"> · {et(r.started)}</span>
                    </td>
                    <td className="k">{r.kind ?? DASH}</td>
                    <td className="n num">{r.metrics.credits_spent != null ? int(r.metrics.credits_spent) : DASH}</td>
                  </tr>
                ))}
                {d.runs.length === 0 && (
                  <tr>
                    <td colSpan={3} className="faint">
                      No runs read (MLflow down or empty).
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      <section className="band" aria-labelledby="when-h">
        <h2 id="when-h" className="display-3">
          Why the weekend video
        </h2>
        <p className="lede">
          The creator posts from Australia: {Math.round((evening / Math.max(1, dated)) * 100)}% of {int(dated)} dated
          uploads land between 19:00 and 03:00 New York time, recapping the session that just closed. So the one
          upload between Friday's close and Monday's open is the week's wrap.
        </p>
        <div className="cols">
          <Bars
            caption="Uploads by hour of day, New York time (Videos tab, dated)"
            every={3}
            bars={d.hours_et.map((n, h) => ({
              key: String(h),
              label: `${String(h).padStart(2, '0')}h`,
              value: n,
              tip: `${String(h).padStart(2, '0')}:00–${String(h).padStart(2, '0')}:59 ET: ${plural(n, 'upload')}`,
            }))}
          />
          <Bars
            caption="The picked video's weekday, New York time"
            bars={d.pick_weekdays.map((n, i) => ({
              key: DAYS[i],
              label: DAYS[i],
              value: n,
              dim: i < 4,
              tip: `${DAYS[i]}: ${plural(n, 'pick')}`,
            }))}
          />
        </div>
        <div className="figures">
          {d.years.map((y) => (
            <div key={y.year} className="figure">
              <span className="f-n">{Math.round((y.weekend / y.weeks) * 100)}%</span>
              <span className="f-l">
                weekend wraps in {y.year} ({y.weekend} of {y.weeks} weeks)
              </span>
            </div>
          ))}
        </div>
      </section>

      <section className="band" aria-labelledby="dec-h">
        <h2 id="dec-h" className="display-3">
          Decisions
        </h2>
        <p className="small">
          From the plan of record, <code>ai_specs/s00_data_pipeline.md</code>. Scope: {date(s.first_week)} to{' '}
          {date(s.last_week)}.
        </p>
        <dl className="kv big">
          {d.decisions.map((r) => (
            <div key={r.question} className="kvrow">
              <dt>{r.question}</dt>
              <dd>
                <Ticks text={r.decision} />
              </dd>
            </div>
          ))}
        </dl>
      </section>
    </>
  );
}
