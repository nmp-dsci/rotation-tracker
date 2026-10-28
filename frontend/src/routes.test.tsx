import { render, screen } from '@testing-library/react';
import { RouterProvider, createMemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { routes } from './routes';
import { respond } from './test/fixtures';

beforeEach(() => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) => {
      const body = respond(String(input));
      return body === undefined
        ? new Response(JSON.stringify({ detail: 'not found' }), { status: 404 })
        : new Response(JSON.stringify(body), { status: 200, headers: { 'content-type': 'application/json' } });
    }),
  );
  window.scrollTo = vi.fn() as unknown as typeof window.scrollTo;
});
afterEach(() => vi.unstubAllGlobals());

function open(path: string) {
  render(<RouterProvider router={createMemoryRouter(routes, { initialEntries: [path] })} />);
}

describe('every page renders from the API', () => {
  it('front page: hero, figures, latest wraps, chart teaser, stages', async () => {
    open('/');
    expect(await screen.findByRole('heading', { level: 1, name: /money on/i })).toBeTruthy();
    expect(await screen.findAllByText('A synthetic weekend wrap')).toHaveLength(1);
    expect(await screen.findByText('Semiconductors')).toBeTruthy();
    expect(screen.getByText('Listener')).toBeTruthy();
  });

  it('weeks: grouped by year with kind badges', async () => {
    open('/weeks');
    expect(await screen.findByRole('heading', { level: 2, name: /2026/ })).toBeTruthy();
    expect(screen.getAllByText('Fallback').length).toBeGreaterThan(0);
    expect(screen.getByText('2 weeks of 2')).toBeTruthy();
  });

  it('a week: tracklist opens on the first macro section, with timestamps', async () => {
    open('/weeks/AAAAAAAAAAA');
    expect(await screen.findByRole('heading', { level: 1, name: 'A synthetic weekend wrap' })).toBeTruthy();
    expect(screen.getByText('A synthetic paragraph about flows.')).toBeTruthy();
    expect(screen.queryByText('A synthetic paragraph about levels.')).toBeNull();
  });

  it('a week that is not a pick says so', async () => {
    open('/weeks/CCCCCCCCCCC');
    expect(await screen.findByText(/is not one of the weekly picks/)).toBeTruthy();
  });

  it('search marks the matched words without trusting HTML', async () => {
    open('/search?q=rotation');
    const mark = await screen.findByText('rotation', { selector: 'mark' });
    expect(mark.tagName).toBe('MARK');
  });

  it('chart: ranks, moves and the not-a-signal note', async () => {
    open('/chart');
    expect(await screen.findByText('Utilities')).toBeTruthy();
    expect(screen.getByText('New')).toBeTruthy();
    expect(screen.getByText(/not a signal/)).toBeTruthy();
    expect(screen.getByText('China')).toBeTruthy();
  });

  it('liner notes: stores, credits and decisions', async () => {
    open('/pipeline');
    expect((await screen.findAllByText('rt.videos')).length).toBe(2); // the Catalog track and the tables
    expect(screen.getByText('98 / 100 left')).toBeTruthy();
    expect(screen.getByText('@example')).toBeTruthy();
  });
});
