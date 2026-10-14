/**
 * Single Source of Truth (SSOT) registry for frontend configuration and constants.
 */

/** The application display name. */
export const APP_NAME = 'usched';

/** The root base URL for API requests. */
export const API_BASE_URL = '/api';

/** Local storage keys, including backwards-compatible fallback keys. */
export interface StorageKeys {
  readonly PLAN: string;
  readonly THEME: string;
  readonly LEGACY_PLAN: string;
  readonly LEGACY_THEME: string;
}

export const STORAGE_KEYS: StorageKeys = {
  PLAN: 'usched:v2:plan',
  THEME: 'usched:v2:theme',
  LEGACY_PLAN: 'usched:v2',
  LEGACY_THEME: 'usched:theme',
};

/** Default starting hour for the schedule calendar view (9 AM). */
export const DEFAULT_START_HOUR = 9;

/** Default ending hour for the schedule calendar view (5 PM). */
export const DEFAULT_END_HOUR = 17;

/** Standard weekdays shown in the schedule calendar view. */
export const DAYS_OF_WEEK = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri'] as const;

/** Extended days of the week including Saturday when weekend classes exist. */
export const EXTENDED_DAYS_OF_WEEK = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'] as const;

/**
 * Most units a term takes at flat tuition; each unit past it costs extra.
 * Mirrors the server's OVERLOAD_UNIT_THRESHOLD.
 */
export const OVERLOAD_UNITS = 18;

/** Milliseconds to keep the reset button armed for confirmation. */
export const ARM_WINDOW_MS = 3000;

/** Default page size for catalog search results. */
export const PAGE_SIZE = 40;

/** Milliseconds to debounce input changes before searching the catalog. */
export const DEBOUNCE_MS = 60;

/**
 * Builds the external link to a course on USC's Schedule of Classes for a given term.
 */
export function uscCourseUrl(code: string, term: number): string {
  const smashed = code.replace(/[^A-Za-z0-9]/g, '').toUpperCase();
  return `https://classes.usc.edu/term/${term}/catalogue/course/${smashed}`;
}
