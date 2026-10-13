/**
 * The viewer's color theme preference: follow the system, or force light or
 * dark.
 *
 * Applied as a `data-theme` attribute on the root element, which index.css
 * turns into `color-scheme`. Stored apart from the plan because it is a
 * display preference, so "Reset all data" leaves it alone. Importing this
 * module applies the saved choice, so main.tsx imports it before rendering
 * to avoid a flash of the wrong theme.
 */

import { STORAGE_KEYS } from '../config';
import { createExternalStore, useSelector } from './_externalStore';

/** A theme choice. */
export type Theme = 'system' | 'light' | 'dark';

function readTheme(): Theme {
  try {
    const saved =
      localStorage.getItem(STORAGE_KEYS.THEME) ??
      localStorage.getItem(STORAGE_KEYS.LEGACY_THEME);
    return saved === 'light' || saved === 'dark' ? saved : 'system';
  } catch {
    return 'system';
  }
}

function apply(theme: Theme): void {
  if (theme === 'system') {
    delete document.documentElement.dataset.theme;
  } else {
    document.documentElement.dataset.theme = theme;
  }
}

const theme = createExternalStore<Theme>(readTheme());
apply(theme.get());

/**
 * Selects the current theme choice.
 */
export function useTheme(): Theme {
  return useSelector(theme, (t) => t);
}

/**
 * Applies and remembers a theme choice.
 */
export function setTheme(next: Theme): void {
  apply(next);
  try {
    if (next === 'system') {
      localStorage.removeItem(STORAGE_KEYS.THEME);
      localStorage.removeItem(STORAGE_KEYS.LEGACY_THEME);
    } else {
      localStorage.setItem(STORAGE_KEYS.THEME, next);
    }
  } catch (err) {
    console.error('Failed to save theme', err);
  }
  theme.set(next);
}
