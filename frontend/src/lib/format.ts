/** Formatting. Times are shown on the New York clock: the pick rule is defined on it (s00). */

export const DASH = '—';

const day = (iso: string) => new Date(`${iso.slice(0, 10)}T12:00:00Z`);

/** 2026-10-23 → 23 Oct 2026 */
export function date(iso: string | null | undefined): string {
  if (!iso) return DASH;
  return day(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' });
}

/** 2026-10-23 → 23.10.2026, the template's date stamp */
export function stamp(iso: string | null | undefined): string {
  if (!iso) return DASH;
  const [y, m, d] = iso.slice(0, 10).split('-');
  return `${d}.${m}.${y}`;
}

/** An instant on the New York clock: Sat 24 Oct 2026, 9:30 pm ET */
export function et(iso: string | null | undefined): string {
  if (!iso) return DASH;
  const s = new Date(iso).toLocaleString('en-US', {
    timeZone: 'America/New_York',
    weekday: 'short',
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });
  return `${s} ET`;
}

/** seconds → 26:25 or 1:02:03 */
export function dur(s: number | null | undefined): string {
  if (s == null) return DASH;
  const t = Math.max(0, Math.round(s));
  const h = Math.floor(t / 3600);
  const m = Math.floor((t % 3600) / 60);
  const sec = String(t % 60).padStart(2, '0');
  return h ? `${h}:${String(m).padStart(2, '0')}:${sec}` : `${m}:${sec}`;
}

export function int(n: number | null | undefined): string {
  return n == null ? DASH : Math.round(n).toLocaleString('en-US');
}

/** 5,912,345 → 5.9M */
export function compact(n: number | null | undefined): string {
  if (n == null) return DASH;
  return new Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 1 }).format(n);
}

export function bytes(n: number): string {
  if (n < 1024) return `${n} B`;
  const units = ['KB', 'MB', 'GB'];
  let v = n / 1024;
  let i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i += 1;
  }
  return `${v.toFixed(v < 10 ? 1 : 0)} ${units[i]}`;
}

/** 2026-07-01 → Q3 2026 */
export function quarter(iso: string): string {
  const d = day(iso);
  return `Q${Math.floor(d.getUTCMonth() / 3) + 1} ${d.getUTCFullYear()}`;
}

/** A rate per wrap: one decimal, two below one (most assets come up less than weekly). */
export function perWrap(v: number): string {
  return v >= 1 || v === 0 ? v.toFixed(1) : v.toFixed(2);
}

/** A FRED level in its own units: 4.12, 18.6, 237, 6.6M. */
export function level(v: number): string {
  const a = Math.abs(v);
  if (a >= 10000) return compact(v);
  if (a >= 100) return v.toFixed(0);
  if (a >= 10) return v.toFixed(1);
  return v.toFixed(2);
}

export function year(iso: string): number {
  return Number(iso.slice(0, 4));
}

export function youtube(id: string, t?: number | null): string {
  const at = t != null && t > 0 ? `&t=${Math.floor(t)}s` : '';
  return `https://www.youtube.com/watch?v=${encodeURIComponent(id)}${at}`;
}

/** hqdefault is 4:3 with the 16:9 frame letterboxed; a 16:9 box with object-fit: cover crops
 *  exactly the bars. mqdefault is a small 16:9 frame; maxresdefault is 16:9 but missing for some uploads. */
export type ThumbSize = 'mq' | 'hq' | 'max';
const THUMB: Record<ThumbSize, string> = { mq: 'mqdefault', hq: 'hqdefault', max: 'maxresdefault' };
export function thumb(id: string, size: ThumbSize = 'hq'): string {
  return `https://i.ytimg.com/vi/${encodeURIComponent(id)}/${THUMB[size]}.jpg`;
}

export const TOPIC_LABEL: Record<string, string> = {
  'macro-flows': 'macro & flows',
  technicals: 'technicals',
  'intro-outro': 'intro / outro',
  promo: 'promo',
  untagged: 'no chapters',
};

export const plural = (n: number, one: string, many = `${one}s`) => `${int(n)} ${n === 1 ? one : many}`;
