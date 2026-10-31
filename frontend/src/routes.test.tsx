import { fireEvent, render, screen, within } from '@testing-library/react';
import { RouterProvider, createMemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { routes } from './routes';
import { market, respond } from './test/fixtures';

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
afterEach(() => {
  vi.unstubAllGlobals();
  market.prices = true;
});

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
    expect(screen.getByText(/none in Q3 2026/)).toBeTruthy();
  });

  it('chart: lists every asset, filters by layer and orders by all time', async () => {
    open('/chart?view=assets');
    expect((await screen.findByRole('link', { name: 'Gold' })).getAttribute('href')).toBe('/assets/commodity%3Agold');
    expect(screen.getByText('0.31')).toBeTruthy(); // a rate under one keeps two decimals
    const names = () => screen.getAllByRole('listitem').map((li) => li.querySelector('.c-name a')?.textContent);
    expect(names()).toEqual(['Gold', 'Nvidia', 'Bitcoin']);
    fireEvent.click(screen.getByRole('button', { name: 'All time first' }));
    expect(names()).toEqual(['Bitcoin', 'Gold', 'Nvidia']);
    fireEvent.click(screen.getByRole('button', { name: 'Stocks 1' }));
    expect(names()).toEqual(['Nvidia']);
  });

  it('chart: each sparkline splits a quarter into bullish and bearish, with a key', async () => {
    open('/chart');
    expect(await screen.findByText('▲ in bullish calls')).toBeTruthy();
    expect(screen.getByText('▼ in bearish calls')).toBeTruthy();
    expect(screen.getByTitle('Q3 2026: 10.0 mentions per wrap · ▲ 6.0 bullish · ▼ 2.0 bearish')).toBeTruthy();
  });

  it('liner notes: stores, credits and decisions', async () => {
    open('/pipeline');
    expect((await screen.findAllByText('rt.videos')).length).toBe(2); // the Catalog track and the tables
    expect(screen.getByText('98 / 100 left')).toBeTruthy();
    expect(screen.getByText('@example')).toBeTruthy();
  });

  it('mentions: the quote, its play, the asset chips and the timestamp link', async () => {
    open('/mentions');
    expect(await screen.findByText(/money leaves widgets for gadgets/)).toBeTruthy();
    expect(screen.getByRole('link', { name: /Widgets/ }).getAttribute('href')).toBe('/assets/theme%3Awidgets');
    expect(screen.getByText('? unknown')).toBeTruthy();
    expect(screen.getByRole('link', { name: '▶ 2:05' }).getAttribute('href')).toContain('t=125s');
  });

  it('assets: ranked with layer and proxy', async () => {
    open('/assets');
    expect(await screen.findByRole('link', { name: 'Widgets' })).toBeTruthy();
    expect(screen.getByText('WDGT')).toBeTruthy();
  });

  it('an asset: the strip marks a bearish week and an unmined one', async () => {
    open('/assets/theme%3Awidgets');
    expect(await screen.findByRole('heading', { level: 1, name: 'Widgets' })).toBeTruthy();
    expect(screen.getByLabelText(/23 Oct 2026: 1 bearish, 1 rotation call/)).toBeTruthy();
    expect(screen.getByLabelText(/16 Oct 2026: not mined yet/)).toBeTruthy();
  });

  it('an asset not in the map says so', async () => {
    open('/assets/theme%3Anope');
    expect(await screen.findByText(/is not an asset in assets\/v1/)).toBeTruthy();
  });

  it('miner: the targets show a missed measure', async () => {
    open('/mining');
    expect(await screen.findByRole('heading', { name: 'Targets' })).toBeTruthy();
    expect(screen.getByText('✕ 1 missed')).toBeTruthy();
    expect(screen.getByText('✕ missed')).toBeTruthy();
    expect(screen.getByText('Asset accuracy')).toBeTruthy();
    expect(screen.getByText('“gadgets”')).toBeTruthy();
  });

  it('miner: has its own tab in the top bar, lit on its page', async () => {
    open('/mining');
    const tab = within(await screen.findByRole('navigation', { name: 'Pages' })).getByRole('link', { name: 'Miner' });
    expect(tab.getAttribute('href')).toBe('/mining');
    expect(tab.className).toBe('on');
  });

  it('spot-check: read-only without --label', async () => {
    open('/label');
    expect(await screen.findByText(/This viewer cannot record/)).toBeTruthy();
    expect(screen.queryByRole('button', { name: /Right/ })).toBeNull();
  });
});

describe('prices (s03): a strip under each chart row, and what prices an asset', () => {
  it('chart: each row has its price on the same x scale, linked to the pinned asset', async () => {
    open('/chart');
    const lab = await screen.findByRole('link', { name: 'WDGT' });
    expect(lab.getAttribute('href')).toBe('/assets/theme%3Awidgets'); // the theme's pinned asset
    expect(screen.getByText('100 → 118')).toBeTruthy(); // performance: rebased to 100
    expect(screen.getByTitle('Q3 2026: WDGT 118 · last close in the quarter, rebased, 100 = Q2 2026')).toBeTruthy();
    expect(screen.getByText('-0.50 → 0.25')).toBeTruthy(); // a FRED level, in its own units
    expect(screen.getByTitle('Q2 2026: SPREAD -0.50 · last close in the quarter, a level')).toBeTruthy();
    expect(screen.getByText('no prices yet')).toBeTruthy(); // a series with no data
    expect(screen.getByText('price, its own scale')).toBeTruthy();
    expect(screen.queryByText(/i no prices/)).toBeNull();
    const strip = screen.getByRole('img', { name: /^WDGT, rebased/ });
    expect(strip.querySelectorAll('polyline.px')).toHaveLength(1);
  });

  it('chart: a gap in a series breaks its line, and an unpriced asset says so', async () => {
    open('/chart?view=assets');
    expect(await screen.findByRole('link', { name: 'Gold' })).toBeTruthy();
    expect(screen.getByText('not priced').getAttribute('title')).toBe('A synthetic reason it is unpriced.');
    const nvda = screen.getByRole('img', { name: /^NVDA, rebased/ });
    expect(nvda.getAttribute('aria-label')).toContain('Q2 2026 none; Q3 2026 100');
  });

  it('chart: without market data, a notice, and every row still names its series', async () => {
    market.prices = false;
    open('/chart');
    expect(await screen.findByText(/market_staging.series_values is not there/)).toBeTruthy();
    expect(screen.getByText('i no prices')).toBeTruthy();
    expect(screen.getAllByText('no prices yet')).toHaveLength(3);
    expect(screen.getByRole('link', { name: 'WDGT' })).toBeTruthy();
    expect(screen.queryByRole('img', { name: /rebased/ })).toBeNull();
  });

  it('an asset: priced by its primary since its first year, with companions, and its components', async () => {
    open('/assets/theme%3Awidgets');
    expect(await screen.findByRole('heading', { level: 1, name: 'Widgets' })).toBeTruthy();
    expect(screen.getByText('WDGT since 2001')).toBeTruthy();
    expect(screen.getByText('WIDGETIDX since 1990')).toBeTruthy();
    expect(screen.getByText(/priced by WDGT/)).toBeTruthy(); // the eyebrow
    expect(screen.getByRole('heading', { level: 2, name: 'Components' })).toBeTruthy();
    const chips = within(screen.getByRole('list', { name: 'Components' }));
    const said = chips.getByRole('link', { name: 'WDGT 7' });
    expect(said.className).toContain('said');
    expect(chips.getByRole('link', { name: 'GDGT' }).getAttribute('href')).toBe('/assets/stock%3AGDGT');
    expect(screen.getByText(/issuer holdings: phase 2/)).toBeTruthy();
    expect(screen.queryByText(/No prices loaded yet/)).toBeNull();
  });

  it('an asset without market data keeps its series and says the prices are not loaded', async () => {
    market.prices = false;
    open('/assets/theme%3Awidgets');
    expect(await screen.findByText(/No prices loaded yet/)).toBeTruthy();
    expect(screen.getByText('WDGT', { selector: '.priced-by b' })).toBeTruthy(); // no first date: no "since"
  });

  it('an asset priced by nothing on purpose shows the reason', async () => {
    open('/assets/macro%3Awidget-policy');
    expect(await screen.findByText('not priced')).toBeTruthy();
    expect(screen.getByText(/policy is context, not a price/)).toBeTruthy();
    expect(screen.getByText(/No component list/)).toBeTruthy();
  });

  it('assets: the list shows what prices each row', async () => {
    open('/assets');
    expect(await screen.findByRole('columnheader', { name: 'Priced by' })).toBeTruthy();
    expect(screen.getByTitle('yahoo:WDGT').textContent).toBe('WDGT');
  });
});
