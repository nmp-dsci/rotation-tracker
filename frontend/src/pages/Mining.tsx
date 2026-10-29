import { Link } from 'react-router-dom';
import { type Mining as MiningT, PLAYS, type PlayScore, api, useGet } from '../lib/api';
import { date, et, int } from '../lib/format';
import { PLAY_LABEL, pct, usd } from '../lib/mentions';
import { Loading, PageHead } from '../lib/ui';

const GATE_LABEL: Record<string, string> = {
  rotation_precision: 'Rotation precision',
  rotation_recall: 'Rotation recall',
  asset_accuracy: 'Asset accuracy',
  unknown_rate: 'Unknown assets',
  dropped_rate: 'Dropped quotes',
};

const p2 = (v: number | null | undefined) => (v == null ? '—' : v.toFixed(2));
/** "< 0.03" → "< 3%", so a rate's bar reads in the unit of its value. */
const bar = (b: string) => b.replace(/([\d.]+)$/, (n) => `${+(Number(n) * 100).toFixed(1)}%`);

function Score({ s }: { s: PlayScore | undefined }) {
  return (
    <>
      <td className="n">{p2(s?.precision)}</td>
      <td className="n">{p2(s?.recall)}</td>
    </>
  );
}

/** How the mentions were made and how far to trust them: the targets, the eval, the runs, the cost. */
export function Mining() {
  const { data, error } = useGet<MiningT>(api.mining());
  if (!data) return <div className="page"><Loading error={error} what="the miner" /></div>;
  const ev = data.eval;
  const m = ev?.metrics;
  const spent = data.spend.reduce((s, r) => s + (r.usd ?? 0), 0);
  const cov = data.coverage;
  const link = (id: string | null) => (id ? data.mlflow.runs[id] : undefined);
  // The targets `rt mine eval` reports (stored under `gate`; nothing waits on them).
  const missed = m ? Object.values(m.gate).filter((g) => !g.pass).length : 0;

  return (
    <div className="page">
      <PageHead eyebrow={`s02 · ${data.version} · prompt ${data.prompt_sha.slice(0, 7)} · claude-opus-5-5 at effort high`} title="The miner">
        <p className="lede">
          One Claude call per week reads the macro and flows sections and returns every commentary on price as structured
          mentions. Code then keeps a mention only if its quote is found verbatim in the transcript, and resolves each asset
          through the alias table. A regex baseline (play/v0) runs the same gates for comparison. Every page reads the
          newest run per week made with this prompt.
        </p>
      </PageHead>

      <section className="figures" aria-label="Coverage">
        <div className="figure">
          <span className="f-n">{int(cov.mined)}</span>
          <span className="f-l">
            of {int(cov.weeks)} weeks mined{cov.first_week ? `, ${date(cov.first_week)} to ${date(cov.last_week)}` : ''}
          </span>
        </div>
        <div className="figure">
          <span className="f-n">{int(cov.mentions)}</span>
          <span className="f-l">
            mentions kept · <Link to="/mentions">read them</Link>
          </span>
        </div>
        <div className="figure">
          <span className="f-n">{pct(cov.assets ? cov.unknown / cov.assets : null, 1)}</span>
          <span className="f-l">of {int(cov.assets)} asset references unresolved</span>
        </div>
        <div className="figure">
          <span className="f-n">{usd(spent)}</span>
          <span className="f-l">spent on mining runs so far (extraction and gold passes; the second reads are extra, under a dollar)</span>
        </div>
      </section>

      <section className="band" aria-labelledby="targets-h">
        <div className="band-head slim">
          <h2 id="targets-h" className="display-3">
            Targets
          </h2>
          {ev && (
            <span className={`badge ${ev.gate_pass ? 'ok' : 'bad'}`}>{ev.gate_pass ? '✓ all met' : `✕ ${missed} missed`}</span>
          )}
        </div>
        {!m ? (
          <p className="empty">No eval yet: run <code>rt mine eval</code>.</p>
        ) : (
          <>
            <p className="count">
              Run <code>{ev.run_id}</code> scored against gold <code>{ev.gold_run_id}</code> on {m.weeks} weeks, {et(ev.at)}
              {link(ev.mlflow_run_id) && (
                <>
                  {' '}
                  · <a href={link(ev.mlflow_run_id)}>MLflow ↗</a>
                </>
              )}
            </p>
            <div className="tablewrap">
              <table>
                <thead>
                  <tr>
                    <th>Measure</th>
                    <th className="n">Value</th>
                    <th>Target</th>
                    <th>Result</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.keys(GATE_LABEL)
                    .filter((k) => m.gate[k])
                    .map((k) => [k, m.gate[k]] as const)
                    .map(([k, g]) => (
                    <tr key={k}>
                      <td>{GATE_LABEL[k] ?? k}</td>
                      <td className="n">{k.endsWith('rate') ? pct(g.value, 1) : p2(g.value)}</td>
                      <td className="mono">{k.endsWith('rate') ? bar(g.bar) : g.bar}</td>
                      <td>
                        <span className={`badge ${g.pass ? 'ok' : 'bad'}`}>{g.pass ? '✓ met' : '✕ missed'}</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </section>

      {m && (
        <section className="band" aria-labelledby="eval-h">
          <div className="band-head slim">
            <h2 id="eval-h" className="display-3">
              Play by play
            </h2>
            <span className="count">
              {int(m.matched)} matched of {int(m.pred)} predicted and {int(m.gold)} gold
            </span>
          </div>
          <div className="tablewrap">
            <table>
              <thead>
                <tr>
                  <th>Play</th>
                  <th className="n">Gold</th>
                  <th className="n">v1 P</th>
                  <th className="n">v1 R</th>
                  <th className="n">v1 F1</th>
                  <th className="n">v0 P</th>
                  <th className="n">v0 R</th>
                </tr>
              </thead>
              <tbody>
                {PLAYS.map((p) => (
                  <tr key={p}>
                    <td>{PLAY_LABEL[p]}</td>
                    <td className="n">{int(m.per_play[p]?.gold)}</td>
                    <Score s={m.per_play[p]} />
                    <td className="n">{p2(m.per_play[p]?.f1)}</td>
                    <Score s={m.baseline?.per_play[p]} />
                  </tr>
                ))}
                <tr className="total">
                  <td>All plays</td>
                  <td className="n">{int(m.gold)}</td>
                  <td className="n">{p2(m.precision)}</td>
                  <td className="n">{p2(m.recall)}</td>
                  <td className="n">{p2(m.f1)}</td>
                  <td className="n">{p2(m.baseline?.precision)}</td>
                  <td className="n">{p2(m.baseline?.recall)}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <dl className="kv big">
            <dt>Direction right, on matched mentions</dt>
            <dd>{pct(m.direction_accuracy)}</dd>
            <dt>Same assets, on matched mentions</dt>
            <dd>
              {pct(m.asset_accuracy)} exactly, {pct(m.asset_overlap)} at least one in common
            </dd>
            {m.agreement && (
              <>
                <dt>Two runs of play/v1 on the same {m.agreement.weeks} weeks</dt>
                <dd>
                  F1 {p2(m.agreement.f1)} overall, {p2(m.agreement.rotation_f1)} on rotation
                </dd>
              </>
            )}
            <dt>Gold corrections applied</dt>
            <dd>
              {Object.entries(m.labels)
                .map(([k, n]) => `${k} ${n}`)
                .join(' · ') || 'none yet'}
            </dd>
          </dl>
          <p className="count">
            A prediction matches a gold mention when both quotes sit in the same section, overlap by at least 30% of the
            shorter, and name the same play. Gold is a separate careful pass at effort xhigh, with every rotation mention read
            again by an independent call; your spot-checks override both.
          </p>
        </section>
      )}

      {data.history.length > 1 && (
        <section className="band" aria-labelledby="hist-h">
          <div className="band-head slim">
            <h2 id="hist-h" className="display-3">
              Prompt by prompt
            </h2>
            <span className="count">each prompt in the order it was tried; the page reads prompt {data.prompt_sha.slice(0, 7)}</span>
          </div>
          <div className="tablewrap">
            <table>
              <thead>
                <tr>
                  <th>Prompt</th>
                  <th>Gold run</th>
                  <th className="n">Rotation pred · gold</th>
                  <th className="n">Rotation P</th>
                  <th className="n">Rotation R</th>
                  <th className="n">Run-to-run rotation F1</th>
                  <th className="n">All plays F1</th>
                  <th>Targets</th>
                </tr>
              </thead>
              <tbody>
                {data.history.map((h) => (
                  <tr key={h.run_id} className={h.prompt_sha === data.prompt_sha ? 'total' : ''}>
                    <td className="mono">
                      {h.prompt_sha.slice(0, 7)}
                      {h.prompt_sha === data.prompt_sha ? ' (current)' : ''}
                    </td>
                    <td className="mono">{h.gold_run_id.slice(-4)}</td>
                    <td className="n">
                      {h.rotation_pred} · {h.rotation_gold}
                    </td>
                    <td className="n">{p2(h.rotation_precision)}</td>
                    <td className="n">{p2(h.rotation_recall)}</td>
                    <td className="n">{p2(h.rotation_run_to_run)}</td>
                    <td className="n">{p2(h.f1)}</td>
                    <td>
                      <span className={`badge ${h.gate_pass ? 'ok' : 'bad'}`}>{h.gate_pass ? '✓ all met' : '✕ some missed'}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      <section className="band" aria-labelledby="gold-h">
        <div className="band-head slim">
          <h2 id="gold-h" className="display-3">
            The gold set
          </h2>
          <Link className="more" to="/label">
            Spot-check {data.gold.spot.done} of {data.gold.spot.total} →
          </Link>
        </div>
        <p>
          Twelve weeks, three a year, drawn with a fixed seed:{' '}
          {data.gold.weeks.map((w, i) => (
            <span key={w.video_id}>
              {i ? ', ' : ''}
              <Link to={`/mentions?week=${w.video_id}`}>{date(w.week_friday)}</Link>
            </span>
          ))}
          .
        </p>
        <p className="count">
          Labels:{' '}
          {data.gold.labels.map((l) => `${l.source} ${l.verdict} ${l.n}`).join(' · ') || 'none'}
          {data.label_mode ? ' · this viewer records spot-checks' : ' · read-only viewer (start with rt serve --label to record)'}
        </p>
      </section>

      <section className="band" aria-labelledby="spend-h">
        <div className="band-head slim">
          <h2 id="spend-h" className="display-3">
            Runs and cost
          </h2>
          {data.mlflow.experiment && (
            <a className="more" href={data.mlflow.experiment}>
              rotation-tracker/mining in MLflow ↗
            </a>
          )}
        </div>
        <div className="tablewrap">
          <table>
            <thead>
              <tr>
                <th>Run</th>
                <th>Version</th>
                <th>Purpose</th>
                <th>Effort · mode</th>
                <th>Status</th>
                <th className="n">Weeks</th>
                <th className="n">Kept</th>
                <th className="n">Dropped</th>
                <th className="n">Out tokens</th>
                <th className="n">Cost</th>
              </tr>
            </thead>
            <tbody>
              {data.runs.map((r) => (
                <tr key={r.run_id}>
                  <td className="mono">{link(r.mlflow_run_id) ? <a href={link(r.mlflow_run_id)}>{r.run_id}</a> : r.run_id}</td>
                  <td className="mono">
                    {r.extractor_version}
                    {r.prompt_sha ? ` · ${r.prompt_sha.slice(0, 7)}` : ''}
                  </td>
                  <td>{r.purpose}</td>
                  <td>{r.engine === 'llm' ? `${r.effort} · ${r.mode}` : 'regex · local'}</td>
                  <td title={r.detail ?? ''}>
                    <span className={`badge ${r.status === 'done' ? 'ok' : r.status === 'failed' ? 'bad' : 'warn'}`}>{r.status}</span>
                  </td>
                  <td className="n">{int(r.weeks)}</td>
                  <td className="n">{int(r.mentions)}</td>
                  <td className="n">{int(r.dropped)}</td>
                  <td className="n">{int(r.output_tokens)}</td>
                  <td className="n">{usd(r.usd)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="band cols" aria-label="Queues">
        <div>
          <h2 className="display-3">Unknown assets</h2>
          {data.unknown.length === 0 ? (
            <p className="empty">Every asset reference resolved.</p>
          ) : (
            <div className="tablewrap">
              <table>
                <thead>
                  <tr>
                    <th>Said as</th>
                    <th>Kind · ticker guess</th>
                    <th className="n">Times</th>
                  </tr>
                </thead>
                <tbody>
                  {data.unknown.map((u) => (
                    <tr key={`${u.spoken}-${u.ticker_guess}`}>
                      <td>“{u.spoken}”</td>
                      <td className="mono">
                        {u.kind_guess ?? '—'} · {u.ticker_guess ?? '—'}
                      </td>
                      <td className="n">{u.n}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
        <div>
          <h2 className="display-3">Dropped by the gate</h2>
          {data.drops.length === 0 ? (
            <p className="empty">No quote failed the provenance gate.</p>
          ) : (
            <ul className="drops">
              {data.drops.map((d) => (
                <li key={`${d.video_id}-${d.quote.slice(0, 20)}`}>
                  <span className="badge warn">{d.reason}</span> {date(d.week_friday)} · {d.play}: “{d.quote}”
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>
    </div>
  );
}
