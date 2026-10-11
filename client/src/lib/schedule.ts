/**
 * Pure schedule arithmetic over sections and courses.
 *
 * Computes meeting overlaps, unit totals, missing section components, and
 * unmet prerequisites on the client so the week can react to hover previews
 * without a server round trip. Rendering and state live elsewhere.
 */

import type { Course, Section } from '../types';
import { courseKey } from './degree';

/** Weekday labels in the order `Section.days` uses. */
export const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri'] as const;

/**
 * Two scheduled sections that meet at the same time on at least one day.
 */
export interface Overlap {
  readonly a: Section;
  readonly b: Section;
}

/**
 * Reports whether a section has a fixed weekly meeting time (not TBA).
 */
export function isTimed(section: Section): boolean {
  return section.days.length > 0 && section.end_minute > section.start_minute;
}

/**
 * Reports whether two sections share a day and their times intersect.
 */
export function overlaps(a: Section, b: Section): boolean {
  return (
    isTimed(a) &&
    isTimed(b) &&
    a.start_minute < b.end_minute &&
    b.start_minute < a.end_minute &&
    a.days.some((d) => b.days.includes(d))
  );
}

/**
 * Lists every overlapping pair among the given sections.
 */
export function findOverlaps(sections: readonly Section[]): readonly Overlap[] {
  const result: Overlap[] = [];
  for (let i = 0; i < sections.length; i++) {
    for (let j = i + 1; j < sections.length; j++) {
      if (overlaps(sections[i], sections[j])) {
        result.push({ a: sections[i], b: sections[j] });
      }
    }
  }
  return result;
}

/**
 * Reports whether adding `section` would collide with the schedule. A
 * scheduled section of the same course and type is ignored because adding
 * swaps it out; a course's lecture against its own lab still collides.
 */
export function clashes(
  section: Section,
  scheduled: readonly Section[],
): boolean {
  return scheduled.some(
    (s) =>
      !(
        s.course_id === section.course_id &&
        s.section_type === section.section_type
      ) && overlaps(s, section),
  );
}

/**
 * Sums units once per distinct course among the sections.
 */
export function totalUnits(
  sections: readonly Section[],
  coursesById: ReadonlyMap<string, Course>,
): number {
  let units = 0;
  for (const id of new Set(sections.map((s) => s.course_id))) {
    units += coursesById.get(id)?.units ?? 0;
  }
  return units;
}

function components(sectionType: string): readonly string[] {
  return sectionType.split('/');
}

/**
 * Lists section components (Lecture, Lab, ...) the course offers but none of
 * the chosen sections cover. A combined "Lecture/Lab" covers both parts.
 */
export function missingComponents(
  course: Course,
  chosen: readonly Section[],
): readonly string[] {
  const covered = new Set(chosen.flatMap((s) => components(s.section_type)));
  const required = new Set(
    course.sections.flatMap((s) => components(s.section_type)),
  );
  return [...required].filter((c) => !covered.has(c));
}

/**
 * Returns the prerequisite OR-groups with no completed member. The course
 * is takeable when this is empty. `completed` holds `courseKey` IDs.
 */
export function unmetPrereqs(
  course: Course,
  completed: ReadonlySet<string>,
): readonly (readonly string[])[] {
  return course.prerequisites_json.filter(
    (group) => !group.some((id) => completed.has(courseKey(id))),
  );
}

/** Display order for section types within a course. */
const TYPE_ORDER = [
  'Lecture',
  'Lecture/Lab',
  'Lecture/Discussion',
  'Discussion',
  'Lab',
  'Quiz',
];

/**
 * Sorts sections by type, then start time.
 */
export function bySectionOrder(a: Section, b: Section): number {
  const rank = (s: Section): number => {
    const i = TYPE_ORDER.indexOf(s.section_type);
    return i === -1 ? TYPE_ORDER.length : i;
  };
  return rank(a) - rank(b) || a.start_minute - b.start_minute;
}
