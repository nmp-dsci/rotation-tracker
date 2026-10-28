import { describe, expect, it } from 'vitest';
import { DASH, date, dur, et, quarter, stamp, thumb, youtube } from './format';

describe('format', () => {
  it('dates ignore the local time zone', () => {
    expect(date('2026-10-23')).toBe('23 Oct 2026');
    expect(stamp('2026-01-06')).toBe('06.01.2026');
    expect(quarter('2026-07-01')).toBe('Q3 2026');
    expect(date(null)).toBe(DASH);
  });

  it('instants are shown on the New York clock', () => {
    // 01:30 UTC Saturday is 21:30 Friday in New York (EDT).
    expect(et('2026-10-24T01:30:00Z')).toMatch(/^Fri, Oct 23, 2026, 9:30\s?PM ET$/);
  });

  it('durations', () => {
    expect(dur(1585)).toBe('26:25');
    expect(dur(3723)).toBe('1:02:03');
    expect(dur(null)).toBe(DASH);
  });

  it('links', () => {
    expect(youtube('AAAAAAAAAAA', 12.7)).toBe('https://www.youtube.com/watch?v=AAAAAAAAAAA&t=12s');
    expect(youtube('AAAAAAAAAAA', 0)).toBe('https://www.youtube.com/watch?v=AAAAAAAAAAA');
    expect(thumb('AAAAAAAAAAA', 'mq')).toBe('https://i.ytimg.com/vi/AAAAAAAAAAA/mqdefault.jpg');
  });
});
