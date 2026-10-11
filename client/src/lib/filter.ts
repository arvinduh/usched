/**
 * Client-side refinement of loaded search results: section filters and sort.
 *
 * The server handles text, GE, and rating; this module narrows what is
 * already loaded by meeting days, time of day, seats, and fit with the week,
 * then orders it. Pure functions only; the Library owns the filter state.
 */

import type { Course, Section } from '../types';
import { clashes, isTimed } from './schedule';

/** Time-of-day buckets by start time. */
export type DayPart = 'morning' | 'afternoon' | 'evening';

/** Ways to order results. */
export type SortKey = 'relevance' | 'rating' | 'easiest' | 'code';

/**
 * Section-level filters the user has set.
 */
export interface SectionFilter {
  /** Weekdays a section must not meet on, e.g. "Fri". */
  readonly excludedDays: ReadonlySet<string>;
  /** Allowed start buckets; empty means any time. */
  readonly dayParts: ReadonlySet<DayPart>;
  readonly openSeatsOnly: boolean;
  readonly fitsWeekOnly: boolean;
}

/** No filtering at all. */
export const NO_FILTER: SectionFilter = {
  excludedDays: new Set(),
  dayParts: new Set(),
  openSeatsOnly: false,
  fitsWeekOnly: false,
};

const NOON = 12 * 60;
const FIVE_PM = 17 * 60;

function dayPartOf(section: Section): DayPart {
  if (section.start_minute < NOON) {
    return 'morning';
  }
  return section.start_minute < FIVE_PM ? 'afternoon' : 'evening';
}

/**
 * Counts active filters, for the Filter button's badge.
 */
export function activeFilterCount(f: SectionFilter): number {
  return (
    f.excludedDays.size +
    f.dayParts.size +
    Number(f.openSeatsOnly) +
    Number(f.fitsWeekOnly)
  );
}

/**
 * Reports whether one section satisfies the filter. TBA sections pass the
 * day and time filters since they have no meeting time to exclude.
 */
export function sectionPasses(
  section: Section,
  f: SectionFilter,
  week: readonly Section[],
): boolean {
  if (f.openSeatsOnly && section.capacity > 0 && section.enrolled >= section.capacity) {
    return false;
  }
  if (!isTimed(section)) {
    return true;
  }
  if (section.days.some((d) => f.excludedDays.has(d))) {
    return false;
  }
  if (f.dayParts.size > 0 && !f.dayParts.has(dayPartOf(section))) {
    return false;
  }
  return !f.fitsWeekOnly || !clashes(section, week);
}

/**
 * Keeps a course when every section type it requires still has at least one
 * passing section, so a match is always actually schedulable.
 */
export function courseMatches(
  course: Course,
  f: SectionFilter,
  week: readonly Section[],
): boolean {
  if (activeFilterCount(f) === 0 || course.sections.length === 0) {
    return true;
  }
  const types = new Set(course.sections.map((s) => s.section_type));
  return [...types].every((type) =>
    course.sections.some(
      (s) => s.section_type === type && sectionPasses(s, f, week),
    ),
  );
}

function best(course: Course, pick: (s: Section) => number | null | undefined): number | null {
  let result: number | null = null;
  for (const s of course.sections) {
    const v = pick(s);
    if (v !== null && v !== undefined && (result === null || v > result)) {
      result = v;
    }
  }
  return result;
}

/**
 * Orders courses. Relevance keeps the server's order; rating and easiest use
 * the best instructor across sections and put unrated courses last.
 */
export function sortCourses(
  courses: readonly Course[],
  key: SortKey,
): readonly Course[] {
  switch (key) {
    case 'relevance':
      return courses;
    case 'code':
      return [...courses].sort((a, b) => a.id.localeCompare(b.id, undefined, { numeric: true }));
    case 'rating': {
      const score = (c: Course) => best(c, (s) => s.instructor?.rmp_rating) ?? -1;
      return [...courses].sort((a, b) => score(b) - score(a));
    }
    case 'easiest': {
      // Easiest = lowest difficulty, so negate to reuse "best is highest".
      const score = (c: Course) =>
        best(c, (s) => {
          const d = s.instructor?.rmp_difficulty;
          return d === null || d === undefined ? null : -d;
        }) ?? -99;
      return [...courses].sort((a, b) => score(b) - score(a));
    }
  }
}
