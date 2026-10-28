import { useEffect, useState } from 'react';
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom';
import { type Health, api, useGet } from './lib/api';
import { theme, toggleTheme } from './theme';

/** The pages, in the order of the work: the wraps, the calls mined from them, the assets they are about,
 *  what they say, how often, how it was built. */
const NAV: [string, string][] = [
  ['/weeks', 'Weeks'],
  ['/mentions', 'Mentions'],
  ['/assets', 'Assets'],
  ['/search', 'Search'],
  ['/chart', 'Chart'],
  ['/pipeline', 'Liner notes'],
];

/** Pages that open on a full-bleed image: the header starts transparent over them. */
const OVER_IMAGE = /^\/($|weeks\/[^/]+$)/;

export function Shell() {
  const { pathname } = useLocation();
  const { data: health, error } = useGet<Health>(api.health());
  const [scrolled, setScrolled] = useState(false);
  const [menu, setMenu] = useState(false);
  const [mode, setMode] = useState(theme());

  useEffect(() => {
    const on = () => setScrolled(window.scrollY > 24);
    on();
    window.addEventListener('scroll', on, { passive: true });
    return () => window.removeEventListener('scroll', on);
  }, []);
  useEffect(() => {
    setMenu(false);
    window.scrollTo(0, 0);
  }, [pathname]);
  useEffect(() => {
    if (!menu) return;
    const esc = (e: KeyboardEvent) => e.key === 'Escape' && setMenu(false);
    window.addEventListener('keydown', esc);
    return () => window.removeEventListener('keydown', esc);
  }, [menu]);

  const over = OVER_IMAGE.test(pathname) && !scrolled && !menu;
  const themeBtn = (
    <button
      type="button"
      className="pill ghost theme-btn"
      onClick={() => setMode(toggleTheme())}
      aria-label={`Switch to ${mode === 'dark' ? 'light' : 'dark'} theme`}
    >
      <span aria-hidden="true">◐</span> {mode === 'dark' ? 'Light' : 'Dark'}
    </button>
  );
  const channel = (
    <a className="pill channel" href="https://www.youtube.com/@fxevolutionvideo" target="_blank" rel="noreferrer">
      Channel ↗
    </a>
  );
  const links = NAV.map(([to, label]) => (
    <NavLink key={to} to={to} className={({ isActive }) => (isActive ? 'on' : '')}>
      {label}
    </NavLink>
  ));

  return (
    <>
      <a className="skip" href="#main">
        Skip to content
      </a>
      <header className={`topbar${over ? ' over' : ''}`}>
        <Link to="/" className="brand">
          Rotation Tracker
        </Link>
        <nav aria-label="Pages" className="bar-nav">
          {links}
        </nav>
        <div className="bar-end">
          <HealthDot health={health} error={error} />
          {themeBtn}
          {channel}
          <button
            type="button"
            className="pill ghost menu-btn"
            aria-expanded={menu}
            aria-controls="drawer"
            onClick={() => setMenu((m) => !m)}
          >
            {menu ? 'Close' : 'Menu'}
          </button>
        </div>
      </header>
      <div id="drawer" className={`drawer${menu ? ' open' : ''}`} hidden={!menu}>
        <nav aria-label="Pages (menu)">
          <NavLink to="/" end>
            Home
          </NavLink>
          {links}
        </nav>
        <div className="drawer-end">
          {themeBtn}
          {channel}
        </div>
      </div>
      <main id="main">
        <Outlet />
      </main>
      <footer className="foot">
        <p className="wordmark" aria-hidden="true">
          Rotation
          <br />
          Tracker
        </p>
        <div className="foot-row">
          <span>
            Weekly market wraps from FX Evolution – Trading Academy, 2023 onwards · transcripts via Supadata through
            transcript·lab · stored in Postgres <code>rotation.rt</code> and Chroma
          </span>
          <span className="mono">
            127.0.0.1 only · build {health?.code_sha ?? '…'}
          </span>
        </div>
      </footer>
    </>
  );
}

function HealthDot({ health, error }: { health: Health | null; error: string | null }) {
  if (error)
    return (
      <span className="health" title={error}>
        <span className="badge bad">✕ api down</span>
      </span>
    );
  if (!health) return <span className="health badge">api …</span>;
  const parts: [string, 'up' | 'down'][] = [
    ['postgres', health.postgres],
    ['chroma', health.chroma],
    ['mlflow', health.mlflow],
  ];
  const down = parts.filter(([, s]) => s === 'down');
  return (
    <span className="health" title={parts.map(([n, s]) => `${n} ${s}`).join(' · ')}>
      {down.length ? (
        <span className="badge warn">○ {down.map(([n]) => n).join(', ')} down</span>
      ) : (
        <span className="badge ok">● live</span>
      )}
    </span>
  );
}
