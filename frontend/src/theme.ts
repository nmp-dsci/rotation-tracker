/** Dark first, as the template is; the house UI defines both themes, so this only picks one.
 *  The choice is a per-browser convenience: storage may be blocked, and the page works without it. */
export type Mode = 'dark' | 'light';
const KEY = 'rotation-tracker:theme';

function stored(): Mode | null {
  try {
    const v = window.localStorage.getItem(KEY);
    return v === 'light' || v === 'dark' ? v : null;
  } catch {
    return null;
  }
}

export function theme(): Mode {
  return document.documentElement.dataset.theme === 'light' ? 'light' : 'dark';
}

export function applyTheme(mode: Mode = stored() ?? 'dark'): void {
  document.documentElement.dataset.theme = mode;
}

export function toggleTheme(): Mode {
  const next: Mode = theme() === 'dark' ? 'light' : 'dark';
  applyTheme(next);
  try {
    window.localStorage.setItem(KEY, next);
  } catch {
    // storage blocked: the switch still holds for this page
  }
  return next;
}
