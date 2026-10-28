import { type FormEvent, useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { READ_TOPICS, type SearchResult, TOPICS, type Topic, api, useGet } from '../lib/api';
import { TOPIC_LABEL, date, dur, int, plural, quarter, youtube } from '../lib/format';
import { Bars, Loading, PageHead, Snippet, TopicBadge } from '../lib/ui';

const SUGGEST = ['rotation', 'rotating out', 'small caps', 'software', 'defensive', 'money flowing', 'capitulation'];

export function Search() {
  const [params, setParams] = useSearchParams();
  const q = params.get('q') ?? 'rotation';
  const topics = (params.get('topics')?.split(',').filter((t): t is Topic => (TOPICS as string[]).includes(t)) ?? READ_TOPICS) as Topic[];
  const order = params.get('order') === 'rank' ? 'rank' : 'recent';
  const [draft, setDraft] = useState(q);
  useEffect(() => setDraft(q), [q]);
  const { data, error } = useGet<SearchResult>(api.search(q, topics, order));

  const update = (patch: Record<string, string | null>) => {
    const next = new URLSearchParams(params);
    for (const [k, v] of Object.entries(patch)) {
      if (v) next.set(k, v);
      else next.delete(k);
    }
    setParams(next, { replace: true });
  };
  const submit = (e: FormEvent) => {
    e.preventDefault();
    update({ q: draft.trim() || null });
  };
  const flip = (t: Topic) => {
    const on = topics.includes(t) ? topics.filter((x) => x !== t) : [...topics, t];
    update({ topics: on.length ? on.join(',') : null });
  };

  return (
    <div className="page">
      <PageHead eyebrow="Postgres full-text search · rt.transcript_chapters" title="Search">
        <form className="big-search" onSubmit={submit} role="search">
          <label htmlFor="q" className="sr-only">
            Search the transcripts
          </label>
          <input id="q" type="text" value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="rotation" autoComplete="off" />
          <button type="submit" className="pill">
            Search
          </button>
        </form>
        <p className="suggest">
          Try{' '}
          {SUGGEST.map((s) => (
            <button key={s} type="button" className="linkish" onClick={() => update({ q: s })}>
              {s}
            </button>
          ))}
        </p>
      </PageHead>

      <div className="filters">
        <div className="chips-row" role="group" aria-label="Sections to search">
          {TOPICS.map((t) => (
            <button key={t} type="button" className="chip-btn" aria-pressed={topics.includes(t)} onClick={() => flip(t)}>
              {TOPIC_LABEL[t]}
            </button>
          ))}
        </div>
        <div className="chips-row" role="group" aria-label="Order">
          <button type="button" className="chip-btn" aria-pressed={order === 'recent'} onClick={() => update({ order: null })}>
            Newest first
          </button>
          <button type="button" className="chip-btn" aria-pressed={order === 'rank'} onClick={() => update({ order: 'rank' })}>
            Best match
          </button>
        </div>
      </div>

      {!data ? (
        <Loading error={error} what="the results" />
      ) : !data.total ? (
        <p className="empty">Type a word or a phrase. Quotes match a phrase, a leading minus excludes a word.</p>
      ) : (
        <>
          <section className="cols search-top" aria-label="Summary">
            <div className="figure">
              <span className="f-n">{int(data.total.weeks)}</span>
              <span className="f-l">
                of {int(data.total.of)} weeks mention “{data.q}”, in {plural(data.total.sections, 'section')}
              </span>
            </div>
            <Bars
              caption={`Weeks per quarter that mention “${data.q}” (of the weeks in that quarter)`}
              every={4}
              height={120}
              bars={data.quarters.map((qc) => ({
                key: qc.quarter,
                label: quarter(qc.quarter),
                value: qc.weeks,
                tip: `${quarter(qc.quarter)}: ${qc.weeks} of ${qc.of} weeks, ${plural(qc.sections, 'section')}`,
              }))}
            />
          </section>
          <p className="count">
            Showing {plural(data.hits.length, 'section')}
            {data.hits.length < data.total.sections ? ` of ${int(data.total.sections)}` : ''}
          </p>
          <ol className="hits">
            {data.hits.map((h) => (
              <li key={`${h.video_id}-${h.idx}`} className="hit">
                <span className="hit-date">{date(h.week_friday)}</span>
                <div className="hit-body">
                  <Link className="hit-title" to={`/weeks/${h.video_id}`}>
                    {h.title}
                  </Link>
                  <span className="hit-sec">
                    {h.section || 'Whole video'} <TopicBadge topic={h.topic} />
                  </span>
                  <p className="snip">
                    <Snippet text={h.snippet} />
                  </p>
                </div>
                <a className="at hit-at" href={youtube(h.video_id, h.start_s)} target="_blank" rel="noreferrer" title="Play the section on YouTube">
                  ▶ {dur(h.start_s)}
                </a>
              </li>
            ))}
          </ol>
        </>
      )}
    </div>
  );
}
