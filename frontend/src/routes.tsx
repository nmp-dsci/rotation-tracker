import { Link, type RouteObject, useRouteError } from 'react-router-dom';
import { Shell } from './Shell';
import { AssetPage } from './pages/Asset';
import { Assets } from './pages/Assets';
import { ChartPage } from './pages/Chart';
import { Home } from './pages/Home';
import { Label } from './pages/Label';
import { Mentions } from './pages/Mentions';
import { Mining } from './pages/Mining';
import { Pipeline } from './pages/Pipeline';
import { Search } from './pages/Search';
import { WeekPage } from './pages/Week';
import { Weeks } from './pages/Weeks';

/**
 * Every viewer address. The path names the subject (a week's video id); the query string holds
 * the lens (year, kind, q, topics, order, quarter, view), so every view can be linked.
 */
export const routes: RouteObject[] = [
  {
    id: 'shell',
    element: <Shell />,
    errorElement: <Crash />,
    children: [
      { id: 'home', path: '/', element: <Home /> },
      { id: 'weeks', path: '/weeks', element: <Weeks /> },
      { id: 'week', path: '/weeks/:id', element: <WeekPage /> },
      { id: 'mentions', path: '/mentions', element: <Mentions /> },
      { id: 'assets', path: '/assets', element: <Assets /> },
      { id: 'asset', path: '/assets/:id', element: <AssetPage /> },
      { id: 'mining', path: '/mining', element: <Mining /> },
      { id: 'label', path: '/label', element: <Label /> },
      { id: 'search', path: '/search', element: <Search /> },
      { id: 'chart', path: '/chart', element: <ChartPage /> },
      { id: 'pipeline', path: '/pipeline', element: <Pipeline /> },
      { id: 'missing', path: '*', element: <NotFound /> },
    ],
  },
];

function NotFound() {
  return (
    <div className="page">
      <header className="page-head">
        <p className="kicker">404</p>
        <h1 className="display">No page here</h1>
      </header>
      <p>
        Try the <Link to="/weeks">weekly wraps</Link> or the <Link to="/">front page</Link>.
      </p>
    </div>
  );
}

function Crash() {
  const err = useRouteError() as Error | undefined;
  return (
    <main className="page">
      <div className="callout red" role="alert">
        <span className="badge bad">✕ error</span> The viewer hit an error:{' '}
        <span className="mono">{err?.message ?? String(err)}</span>
      </div>
      <p>
        <a href="/">Back to the front page</a>
      </p>
    </main>
  );
}
