/**
 * Persisted student plan store backed by browser localStorage.
 *
 * Owns every piece of user-authored state (schedule configurations, watched
 * and completed courses, AP credits, chosen degree) and nothing fetched from
 * the server. Components read slices through `useStore` and write through
 * `update`; each write persists synchronously and reaches other open tabs via
 * the `storage` event. Advisor chat is deliberately absent: it is ephemeral.
 */

import { createExternalStore, useSelector } from '../lib/externalStore';
import type { ScheduleConfiguration, UserApCredit } from '../types';

/**
 * User-authored planning state that survives reloads.
 */
export interface PlanState {
  readonly configurations: readonly ScheduleConfiguration[];
  readonly activeConfigId: string;
  readonly watchedCourseIds: readonly string[];
  readonly completedCourseIds: readonly string[];
  readonly apCredits: readonly UserApCredit[];
  /** Chosen degree program, or empty to fall back to the catalog default. */
  readonly degreeId: string;
}

/** Bump the suffix when `PlanState` changes shape; old data is discarded. */
const STORAGE_KEY = 'usched:v1';

const DEFAULT_STATE: PlanState = {
  configurations: [{ id: 'config-1', name: 'A', section_ids: [] }],
  activeConfigId: 'config-1',
  watchedCourseIds: [],
  completedCourseIds: [],
  apCredits: [],
  degreeId: '',
};

/**
 * Loads persisted state, falling back to defaults when storage is
 * unavailable, empty, corrupt, or holds no schedule configuration.
 */
function readStorage(): PlanState {
  let parsed: Partial<PlanState>;
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw === null) {
      return DEFAULT_STATE;
    }
    parsed = JSON.parse(raw) as Partial<PlanState>;
  } catch {
    return DEFAULT_STATE;
  }
  const merged = { ...DEFAULT_STATE, ...parsed };
  if (
    !Array.isArray(merged.configurations) ||
    merged.configurations.length === 0
  ) {
    return DEFAULT_STATE;
  }
  return merged;
}

const plan = createExternalStore(readStorage());

// Another tab wrote (key set) or cleared storage (key null): adopt its state.
window.addEventListener('storage', (event) => {
  if (event.key === STORAGE_KEY || event.key === null) {
    plan.set(readStorage());
  }
});

/**
 * Selects a slice of plan state and re-renders when it changes.
 *
 * The selector must return a reference already held in state (a field), not
 * a freshly built object, or React will re-render indefinitely.
 */
export function useStore<T>(selector: (s: PlanState) => T): T {
  return useSelector(plan, selector);
}

/**
 * Reads the current plan outside React, for event handlers.
 */
export function getPlan(): PlanState {
  return plan.get();
}

/**
 * Replaces plan state with the recipe's result and persists it.
 *
 * Returning `prev` unchanged is a no-op. A failed write (quota exceeded,
 * storage disabled) keeps the in-memory state so the session still works.
 */
export function update(recipe: (prev: PlanState) => PlanState): void {
  const next = recipe(plan.get());
  if (next === plan.get()) {
    return;
  }
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  } catch (err) {
    console.error('Failed to persist plan state', err);
  }
  plan.set(next);
}

/**
 * Erases all persisted plan data and restores defaults.
 */
export function reset(): void {
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch (err) {
    console.error('Failed to clear plan state', err);
  }
  plan.set(DEFAULT_STATE);
}
