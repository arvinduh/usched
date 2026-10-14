/**
 * Persisted student plan store backed by browser localStorage.
 *
 * Owns every piece of user-authored state and nothing fetched from the
 * server. Schedules and shortlists belong to a term, since they name that
 * term's sections and offerings; completed courses, AP credits, and the
 * program span terms. Components read slices through `useStore` or
 * `useTermPlan` and write through `update`; each write persists
 * synchronously and reaches other open tabs via the `storage` event.
 * Advisor chat is deliberately absent: it is ephemeral.
 */

import { STORAGE_KEYS } from '../config';
import { createExternalStore, useSelector } from './_externalStore';
import type { components } from '../api/schema';

/**
 * One schedule variant of a term: the sections the student picked.
 */
export interface ScheduleConfiguration {
  readonly id: string;
  readonly name: string;
  readonly section_ids: readonly string[];
}

/**
 * One term's plan: schedule variants and shortlisted courses.
 */
export interface TermPlan {
  readonly configurations: readonly ScheduleConfiguration[];
  readonly activeConfigId: string;
  readonly watchedCourseIds: readonly string[];
}

/**
 * User-authored planning state that survives reloads.
 */
export interface PlanState {
  /** The term being planned, or null until the client picks the default. */
  readonly term: number | null;
  /** Plans by term code; a term without one reads as `EMPTY_TERM_PLAN`. */
  readonly terms: Readonly<Record<number, TermPlan>>;
  readonly completedCourseIds: readonly string[];
  readonly apCredits: readonly components['schemas']['ApCredit'][];
  /** GE seats counted by hand (credit the catalog cannot place), by code. */
  readonly geCounted: Readonly<Record<string, number>>;
  /** Chosen program, or empty until the student picks one. */
  readonly programId: string;
  /** True once the first-run welcome was answered or skipped. */
  readonly welcomed: boolean;
}

/** The plan of a term the student has not touched yet. */
export const EMPTY_TERM_PLAN: TermPlan = {
  configurations: [{ id: 'config-1', name: 'A', section_ids: [] }],
  activeConfigId: 'config-1',
  watchedCourseIds: [],
};

const DEFAULT_STATE: PlanState = {
  term: null,
  terms: {},
  completedCourseIds: [],
  apCredits: [],
  geCounted: {},
  programId: '',
  welcomed: false,
};

function _isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function _isStringArray(arr: unknown): arr is readonly string[] {
  return Array.isArray(arr) && arr.every((item) => typeof item === 'string');
}

function _isValidConfiguration(c: unknown): c is ScheduleConfiguration {
  if (!_isRecord(c)) {
    return false;
  }
  return (
    typeof c['id'] === 'string' &&
    typeof c['name'] === 'string' &&
    _isStringArray(c['section_ids'])
  );
}

function _isValidTermPlan(tp: unknown): tp is TermPlan {
  if (!_isRecord(tp)) {
    return false;
  }
  return (
    typeof tp['activeConfigId'] === 'string' &&
    _isStringArray(tp['watchedCourseIds']) &&
    Array.isArray(tp['configurations']) &&
    tp['configurations'].every(_isValidConfiguration)
  );
}

function _isApCredit(c: unknown): c is components['schemas']['ApCredit'] {
  return (
    _isRecord(c) &&
    typeof c['exam_id'] === 'string' &&
    typeof c['score'] === 'number'
  );
}

function _isValidPlanState(candidate: unknown): candidate is PlanState {
  if (!_isRecord(candidate)) {
    return false;
  }

  if (candidate['term'] !== null && typeof candidate['term'] !== 'number') {
    return false;
  }

  if (!_isRecord(candidate['terms'])) {
    return false;
  }
  for (const [key, val] of Object.entries(candidate['terms'])) {
    if (Number.isNaN(Number(key)) || !_isValidTermPlan(val)) {
      return false;
    }
  }

  if (!_isStringArray(candidate['completedCourseIds'])) {
    return false;
  }

  if (
    !Array.isArray(candidate['apCredits']) ||
    !candidate['apCredits'].every(_isApCredit)
  ) {
    return false;
  }

  if (!_isRecord(candidate['geCounted'])) {
    return false;
  }
  for (const [k, v] of Object.entries(candidate['geCounted'])) {
    if (typeof k !== 'string' || typeof v !== 'number') {
      return false;
    }
  }

  if (typeof candidate['programId'] !== 'string') {
    return false;
  }

  if (typeof candidate['welcomed'] !== 'boolean') {
    return false;
  }

  return true;
}

/**
 * Loads persisted state, falling back to defaults when storage is
 * unavailable, empty, or corrupt.
 */
function readStorage(): PlanState {
  try {
    const raw =
      localStorage.getItem(STORAGE_KEYS.PLAN) ??
      localStorage.getItem(STORAGE_KEYS.LEGACY_PLAN);
    if (raw === null) {
      return DEFAULT_STATE;
    }
    const parsed: unknown = JSON.parse(raw);
    if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
      return DEFAULT_STATE;
    }
    const candidate = { ...DEFAULT_STATE, ...parsed };
    if (!_isValidPlanState(candidate)) {
      return DEFAULT_STATE;
    }
    return candidate;
  } catch {
    return DEFAULT_STATE;
  }
}

const plan = createExternalStore(readStorage());

// Another tab wrote (key set) or cleared storage (key null): adopt its state.
window.addEventListener('storage', (event) => {
  if (
    event.key === STORAGE_KEYS.PLAN ||
    event.key === STORAGE_KEYS.LEGACY_PLAN ||
    event.key === null
  ) {
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
 * The plan of the term being planned.
 */
export function termPlanOf(s: PlanState): TermPlan {
  return (s.term !== null && s.terms[s.term]) || EMPTY_TERM_PLAN;
}

/**
 * Selects a slice of the current term's plan; the same stability rule as
 * `useStore` applies.
 */
export function useTermPlan<T>(selector: (p: TermPlan) => T): T {
  return useSelector(plan, (s) => selector(termPlanOf(s)));
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
    localStorage.setItem(STORAGE_KEYS.PLAN, JSON.stringify(next));
  } catch (err) {
    console.error('Failed to persist plan state', err);
  }
  plan.set(next);
}

/**
 * Applies a recipe to the current term's plan; a no-op before a term is
 * chosen or when the recipe returns its input.
 */
export function updateTerm(recipe: (prev: TermPlan) => TermPlan): void {
  update((s) => {
    if (s.term === null) {
      return s;
    }
    const prev = termPlanOf(s);
    const next = recipe(prev);
    return next === prev ? s : { ...s, terms: { ...s.terms, [s.term]: next } };
  });
}

/**
 * Erases all persisted plan data and restores defaults, keeping the term.
 */
export function reset(): void {
  try {
    localStorage.removeItem(STORAGE_KEYS.PLAN);
    localStorage.removeItem(STORAGE_KEYS.LEGACY_PLAN);
  } catch (err) {
    console.error('Failed to clear plan state', err);
  }
  plan.set({ ...DEFAULT_STATE, term: plan.get().term });
}
