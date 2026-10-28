import { useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { type Chunk, type Section, type WeekDetail, api, useGet } from '../lib/api';
import { DASH, compact, date, dur, et, int, plural, youtube } from '../lib/format';
import { Cover, KindBadge, Loading, TopicBadge } from '../lib/ui';

type View = 'tracks' | 'chunks' | 'stored';
const VIEWS: [View, string][] = [
  ['tracks', 'Tracklist'],
  ['chunks', 'Chroma chunks'],
  ['stored', 'Where it lives'],
];

export function WeekPage() {
  const { id = '' } = useParams();
  const { data, error, status } = useGet<WeekDetail>(api.week(id));
  const [params, setParams] = useSearchParams();
  const view = (params.get('view') as View | null) ?? 'tracks';

  if (!data || data.video_id !== id) {
    return (
      <div className="page">
        {status === 404 ? (
          <div className="empty">
            <p>
              <b>{id}</b> is not one of the weekly picks. <Link to="/weeks">See every week</Link>.
            </p>
          </div>
        ) : (
          <Loading error={error} what="this week" />
        )}
      </div>
    );
  }
  const w = data;
  const words = w.sections.reduce((n, s) => n + s.paragraphs.reduce((m, p) => m + p.text.split(' ').length, 0), 0);
  return (
    <>
      <section className="hero album" aria-labelledby="album-title">
        <div className="hero-media" aria-hidden="true">
          <Cover id={w.video_id} size="max" eager />
        </div>
        <div className="hero-scrim" aria-hidden="true" />
        <div className="hero-in album-in">
          <div className="album-art">
            <Cover id={w.video_id} size="max" alt={`Thumbnail: ${w.title}`} eager />
          </div>
          <div className="album-text">
            <p className="kicker">
              Week ending Fri {date(w.week_friday)} · <KindBadge reason={w.reason} />
            </p>
            <h1 id="album-title" className="album-title">
              {w.title}
            </h1>
            <p className="album-meta">
              <span>{et(w.published_at)}</span>
              <span>{dur(w.duration_s)}</span>
              <span>{compact(w.view_count)} views</span>
              <span>{compact(words)} words</span>
              <span>{plural(w.sections.length, 'section')}</span>
            </p>
            <div className="album-cta">
              <a className="pill" href={youtube(w.video_id)} target="_blank" rel="noreferrer">
                ▶ Watch on YouTube
              </a>
              {w.next && (
                <Link className="pill ghost" to={`/weeks/${w.next}`}>
                  ← Newer week
                </Link>
              )}
              {w.prev && (
                <Link className="pill ghost" to={`/weeks/${w.prev}`}>
                  Older week →
                </Link>
              )}
            </div>
          </div>
        </div>
      </section>

      <div className="page">
        <div className="tabs" role="tablist" aria-label="View">
          {VIEWS.map(([v, label]) => (
            <button
              key={v}
              type="button"
              role="tab"
              aria-selected={view === v}
              className="tab"
              onClick={() => {
                const next = new URLSearchParams(params);
                if (v === 'tracks') next.delete('view');
                else next.set('view', v);
                setParams(next, { replace: true });
              }}
            >
              {label}
            </button>
          ))}
        </div>
        {view === 'tracks' && <Tracklist key={w.video_id} w={w} />}
        {view === 'chunks' && <Chunks id={w.video_id} />}
        {view === 'stored' && <Stored w={w} />}
      </div>
    </>
  );
}

function Tracklist({ w }: { w: WeekDetail }) {
  const first = w.sections.find((s) => s.topic === 'macro-flows' || s.topic === 'untagged');
  const [open, setOpen] = useState<Set<number>>(new Set(first ? [first.idx] : []));
  const toggle = (i: number) =>
    setOpen((o) => {
      const n = new Set(o);
      if (n.has(i)) n.delete(i);
      else n.add(i);
      return n;
    });
  const all = open.size === w.sections.length;
  return (
    <section aria-labelledby="tl">
      <div className="band-head slim">
        <h2 id="tl" className="display-3">
          Tracklist
        </h2>
        <button type="button" className="pill ghost" onClick={() => setOpen(all ? new Set() : new Set(w.sections.map((s) => s.idx)))}>
          {all ? 'Close all' : 'Open all'}
        </button>
      </div>
      <p className="lede">
        The transcript cut at the video's chapters and tagged by <code>topic/v1</code>. Rotation work reads the{' '}
        <b>● macro & flows</b> and <b>● no chapters</b> sections. Open a track to read it; each timestamp plays the
        video from there.
      </p>
      <ol className="tracks">
        {w.sections.map((s) => (
          <Track key={s.idx} s={s} id={w.video_id} open={open.has(s.idx)} onToggle={() => toggle(s.idx)} />
        ))}
      </ol>
    </section>
  );
}

function Track({ s, id, open, onToggle }: { s: Section; id: string; open: boolean; onToggle: () => void }) {
  const len = s.end_s != null ? s.end_s - s.start_s : null;
  return (
    <li className={`track${open ? ' open' : ''}`}>
      <button type="button" className="track-row" aria-expanded={open} onClick={onToggle}>
        <span className="t-n">
          <span className="t-num">{String(s.idx + 1).padStart(2, '0')}</span>
          <span className="t-play" aria-hidden="true">
            {open ? '▼' : '▶'}
          </span>
        </span>
        <span className="t-title">
          <b>{s.title || 'Whole video (no chapters)'}</b>
          <span className="t-sub">
            {dur(s.start_s)} · {int(s.n_chars)} characters
          </span>
        </span>
        <span className="t-end">
          <TopicBadge topic={s.topic} />
          <span className="t-len">{len != null ? dur(len) : DASH}</span>
        </span>
      </button>
      {open && (
        <div className="reader">
          {s.paragraphs.map((p) => (
            <p key={p.t}>
              <a className="at" href={youtube(id, p.t)} target="_blank" rel="noreferrer" title="Play from here on YouTube">
                {dur(p.t)}
              </a>{' '}
              {p.text}
            </p>
          ))}
          {s.paragraphs.length === 0 && <p className="faint">No transcript text falls inside this chapter.</p>}
        </div>
      )}
    </li>
  );
}

function Chunks({ id }: { id: string }) {
  const { data, error } = useGet<Chunk[]>(api.chunks(id));
  return (
    <section aria-labelledby="ch">
      <h2 id="ch" className="display-3">
        Chroma chunks
      </h2>
      <p className="lede">
        The same transcript as transcript·lab stored it for retrieval: collection <code>transcript_chunks</code>, read
        here without writing.
      </p>
      {!data ? (
        <Loading error={error} what="the chunks" />
      ) : (
        <ol className="chunks">
          {data.map((c) => (
            <li key={c.idx} className="chunk">
              <span className="chunk-at">
                <span className="mono">#{c.idx}</span>
                <a className="at" href={youtube(id, c.start_s)} target="_blank" rel="noreferrer">
                  {dur(c.start_s)}–{dur(c.end_s)}
                </a>
              </span>
              <p>{c.text}</p>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

function Stored({ w }: { w: WeekDetail }) {
  return (
    <section aria-labelledby="st" className="cols">
      <div>
        <h2 id="st" className="display-3">
          Where it lives
        </h2>
        <dl className="kv big">
          <dt>Postgres</dt>
          <dd>
            <code>rt.transcripts</code> · {int(w.n_segments)} timed segments · synced {et(w.stored.synced_at)}
          </dd>
          <dt>sha256</dt>
          <dd className="mono">{w.stored.sha256 ?? DASH}</dd>
          <dt>Sections</dt>
          <dd>
            <code>rt.transcript_chapters</code> · {plural(w.sections.length, 'section')} ·{' '}
            {w.sections[0]?.topic_rule_version ?? DASH}
          </dd>
          <dt>Chapters</dt>
          <dd>
            <code>rt.chapters</code> · {plural(w.n_chapters, 'chapter')} from yt-dlp
          </dd>
          <dt>Chroma</dt>
          <dd>
            <code>{w.stored.chroma_raw_id}</code> · {w.stored.chroma_chunks == null ? DASH : plural(w.stored.chroma_chunks, 'chunk')}
          </dd>
          <dt>Pick</dt>
          <dd>
            <code>rt.weekly_picks</code> · week ending {date(w.week_friday)} · {w.reason}
          </dd>
          <dt>MLflow</dt>
          <dd>
            {w.mlflow_url ? (
              <a href={w.mlflow_url} target="_blank" rel="noreferrer">
                rotation-tracker/ingest ↗
              </a>
            ) : (
              'MLflow is down: no link'
            )}
          </dd>
        </dl>
      </div>
      <div>
        <h3 className="label">Ingest log</h3>
        <div className="tablewrap">
          <table>
            <thead>
              <tr>
                <th>Batch</th>
                <th>Took</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {w.ingest.map((r) => (
                <tr key={r.batch_id + r.started_at}>
                  <td className="k">{r.batch_id}</td>
                  <td className="n">
                    {r.finished_at ? dur((new Date(r.finished_at).getTime() - new Date(r.started_at).getTime()) / 1000) : DASH}
                  </td>
                  <td>
                    {r.status === 'indexed' ? (
                      <span className="badge ok">✓ indexed</span>
                    ) : (
                      <span className="badge bad">✕ {r.status}</span>
                    )}
                    {r.returncode ? <span className="tag"> rc {r.returncode}</span> : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}
