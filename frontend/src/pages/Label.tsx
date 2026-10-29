import { useState } from 'react';
import { Link } from 'react-router-dom';
import { type Labels, type OwnerLabel, PLAYS, type Play, type SpotCheck, api, post, useGet } from '../lib/api';
import { date, dur, youtube } from '../lib/format';
import { AssetChip, DIRECTION_LABEL, PLAY_LABEL, PlayBadge, StanceGlyph } from '../lib/mentions';
import { Loading, PageHead } from '../lib/ui';

const DIRECTIONS: Record<Play, string[]> = {
  rotation: ['in', 'out', 'out_in'],
  flow: ['buying', 'selling'],
  valuation: ['under', 'over', 'fair'],
  technical: ['bullish', 'bearish', 'neutral'],
  regime: ['risk_on', 'risk_off', 'bull', 'bear', 'neutral'],
  relative: ['a_over_b'],
  call: ['long', 'short', 'avoid', 'watch'],
  other: ['bullish', 'bearish', 'neutral'],
};
const VERDICT: Record<OwnerLabel['verdict'], string> = { correct: '✓ right', wrong: '✕ not a mention', fix: '✎ fixed' };
const VERDICT_BADGE: Record<OwnerLabel['verdict'], string> = { correct: 'ok', wrong: 'bad', fix: 'warn' };

/** The owner's fifty spot-checks of the gold set. Writes only under `rt serve --label`. */
export function Label() {
  const [rev, setRev] = useState(0);
  const { data, error } = useGet<Labels>(`${api.labels()}${rev ? `?r=${rev}` : ''}`);
  if (!data) return <div className="page"><Loading error={error} what="the spot-checks" /></div>;
  const done = data.items.filter((i) => i.owner).length;

  return (
    <div className="page">
      <PageHead eyebrow={`gold/v1 · ${done} of ${data.items.length} checked`} title="Spot-check">
        <p className="lede">
          Fifty mentions from the gold set, rotation first. For each: is it a claim about this asset, with the right play and
          direction? Your verdict overrides the careful pass and the second read when <Link to="/mining">the eval</Link> runs
          again.
        </p>
        {!data.label_mode && (
          <div className="callout warn" role="note">
            <span className="badge warn">read-only</span> This viewer cannot record. Restart it with{' '}
            <code>uv run rt serve --label</code> to save your checks to <code>rt.labels</code>.
          </div>
        )}
      </PageHead>
      <ol className="checks">
        {data.items.map((it) => (
          <Check key={it.id} it={it} writable={data.label_mode} onSaved={() => setRev((r) => r + 1)} />
        ))}
      </ol>
      {data.items.length === 0 && <p className="empty">No spot-checks drawn yet: <code>rt gold sample</code>.</p>}
    </div>
  );
}

function Check({ it, writable, onSaved }: { it: SpotCheck; writable: boolean; onSaved: () => void }) {
  const [fixing, setFixing] = useState(false);
  const [play, setPlay] = useState<Play>(it.play);
  const [direction, setDirection] = useState(it.direction);
  const [assetId, setAssetId] = useState('');
  const [note, setNote] = useState('');
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const save = async (verdict: OwnerLabel['verdict']) => {
    setBusy(true);
    setErr(null);
    try {
      const fixes: Record<string, string> = {};
      if (verdict === 'fix') {
        if (play !== it.play) fixes.play = play;
        if (direction !== it.direction || play !== it.play) fixes.direction = direction;
        if (assetId.trim()) fixes.asset_id = assetId.trim();
      }
      await post(api.labels(), { mention_id: it.id, verdict, fixes, note: note || null });
      setFixing(false);
      onSaved();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <li className={`check card${it.owner ? ' done' : ''}`}>
      <div className="check-head">
        <span className="t-n">#{it.ord + 1}</span>
        <span>
          {date(it.week_friday)} · <Link to={`/weeks/${it.video_id}`}>{it.section_title || 'the week'}</Link>
        </span>
        <a className="at" href={youtube(it.video_id, it.t_seconds)} target="_blank" rel="noreferrer">
          ▶ {dur(it.t_seconds)}
        </a>
        {it.owner && <span className={`badge ${VERDICT_BADGE[it.owner.verdict]}`}>{VERDICT[it.owner.verdict]}</span>}
      </div>
      <p className="context">
        <span className="faint">…{it.before}</span>
        <mark>{it.quote}</mark>
        <span className="faint">{it.after}…</span>
      </p>
      <div className="m-head">
        <PlayBadge play={it.play} direction={it.direction} />
        <StanceGlyph stance={it.stance} />
        <span className="m-meta">
          {it.speaker === 'reported' ? `reported${it.reported_source ? `: ${it.reported_source}` : ''}` : 'his view'} · {it.modality} ·
          confidence {it.confidence.toFixed(2)}
        </span>
      </div>
      <div className="m-assets">
        {it.assets.map((a, i) => (
          <AssetChip key={i} a={a} />
        ))}
      </div>
      {it.second_read && it.second_read.verdict !== 'correct' && (
        <p className="count">
          Second read: {VERDICT[it.second_read.verdict]}
          {it.second_read.fixes?.play ? ` → ${PLAY_LABEL[it.second_read.fixes.play as Play]} ${DIRECTION_LABEL[it.second_read.fixes.direction] ?? ''}` : ''}.{' '}
          {it.second_read.note}
        </p>
      )}
      {it.owner?.note && <p className="count">Your note: {it.owner.note}</p>}
      {writable && (
        <div className="check-act">
          <button type="button" className="pill" disabled={busy} onClick={() => save('correct')}>
            ✓ Right
          </button>
          <button type="button" className="pill ghost" disabled={busy} onClick={() => save('wrong')}>
            ✕ Not a mention
          </button>
          <button type="button" className="pill ghost" disabled={busy} aria-expanded={fixing} onClick={() => setFixing((f) => !f)}>
            ✎ Fix…
          </button>
        </div>
      )}
      {writable && fixing && (
        <div className="fix-form">
          <label>
            Play{' '}
            <select
              value={play}
              onChange={(e) => {
                const p = e.target.value as Play;
                setPlay(p);
                setDirection(DIRECTIONS[p][0]);
              }}
            >
              {PLAYS.map((p) => (
                <option key={p} value={p}>
                  {PLAY_LABEL[p]}
                </option>
              ))}
            </select>
          </label>
          <label>
            Direction{' '}
            <select value={direction} onChange={(e) => setDirection(e.target.value)}>
              {DIRECTIONS[play].map((d) => (
                <option key={d} value={d}>
                  {DIRECTION_LABEL[d] ?? d}
                </option>
              ))}
            </select>
          </label>
          <label>
            Asset id <input type="text" value={assetId} placeholder="e.g. theme:semis" onChange={(e) => setAssetId(e.target.value)} />
          </label>
          <label className="wide">
            Note <input type="text" value={note} onChange={(e) => setNote(e.target.value)} />
          </label>
          <button type="button" className="pill" disabled={busy} onClick={() => save('fix')}>
            Save the fix
          </button>
        </div>
      )}
      {err && (
        <p className="callout red" role="alert">
          {err}
        </p>
      )}
    </li>
  );
}
