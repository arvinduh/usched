/**
 * Client-side refinement of loaded search results: section filters and sort.
 *
 * The server handles text, GE, and rating; this module narrows what is
 * already loaded by meeting days, time of day, seats, and fit with the week,
 * then orders it. Pure functions only; the Library owns the filter state.
 */

import type { components } from "../../api/schema";
import { clashes, startOf, timedMeetings } from "../_schedule";

/** Time-of-day buckets by start time. */
export type DayPart = "morning" | "afternoon" | "evening";

/** Ways to order results. */
export type SortKey = "relevance" | "rating" | "easiest" | "code";

/**
 * Section-level filters the user has set.
 */
export interface SectionFilter {
  /** Weekdays a section must not meet on, e.g. "Fri". */
  readonly excludedDays: ReadonlySet<components["schemas"]["Weekday"]>;
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

function dayPartOf(start: number): DayPart {
  if (start < NOON) {
    return "morning";
  }
  return start < FIVE_PM ? "afternoon" : "evening";
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
  section: components["schemas"]["Section"],
  f: SectionFilter,
  week: readonly components["schemas"]["Section"][],
): boolean {
  if (
    f.openSeatsOnly &&
    section.capacity > 0 &&
    section.registered >= section.capacity
  ) {
    return false;
  }
  const start = startOf(section);
  if (start === null) {
    return true;
  }
  if (
    timedMeetings(section).some((m) =>
      m.days.some((d) => f.excludedDays.has(d)),
    )
  ) {
    return false;
  }
  if (f.dayParts.size > 0 && !f.dayParts.has(dayPartOf(start))) {
    return false;
  }
  return !f.fitsWeekOnly || !clashes(section, week);
}

/**
 * Keeps a course when every section type it requires still has at least one
 * passing section, so a match is always actually schedulable.
 */
export function courseMatches(
  course: components["schemas"]["Course"],
  f: SectionFilter,
  week: readonly components["schemas"]["Section"][],
): boolean {
  if (activeFilterCount(f) === 0 || course.sections.length === 0) {
    return true;
  }
  const types = new Set(course.sections.map((s) => s.type));
  return [...types].every((type) =>
    course.sections.some((s) => s.type === type && sectionPasses(s, f, week)),
  );
}

function best(
  course: components["schemas"]["Course"],
  pick: (r: components["schemas"]["Rating"]) => number | null,
): number | null {
  let result: number | null = null;
  for (const s of course.sections) {
    for (const i of s.instructors) {
      const v = i.rmp ? pick(i.rmp) : null;
      if (v !== null && (result === null || v > result)) {
        result = v;
      }
    }
  }
  return result;
}

/**
 * Orders courses. Relevance keeps the server's order; rating and easiest use
 * the best instructor across sections and put unrated courses last.
 */
export function sortCourses(
  courses: readonly components["schemas"]["Course"][],
  key: SortKey,
): readonly components["schemas"]["Course"][] {
  switch (key) {
    case "relevance":
      return courses;
    case "code":
      return [...courses].sort((a, b) =>
        a.code.localeCompare(b.code, undefined, { numeric: true }),
      );
    case "rating": {
      const score = (c: components["schemas"]["Course"]) =>
        best(c, (r) => r.rating) ?? -1;
      return [...courses].sort((a, b) => score(b) - score(a));
    }
    case "easiest": {
      // Easiest = lowest difficulty, so negate to reuse "best is highest".
      const score = (c: components["schemas"]["Course"]) =>
        best(c, (r) => (r.difficulty === null ? null : -r.difficulty)) ?? -99;
      return [...courses].sort((a, b) => score(b) - score(a));
    }
  }
}
