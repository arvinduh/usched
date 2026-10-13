/**
 * Pure schedule arithmetic over sections and courses.
 *
 * Computes meeting overlaps, link-group compatibility, unit totals, missing
 * section components, and unmet prerequisites on the client so the week
 * reacts to hover previews without a server round trip. The rules mirror
 * the server's schedule engine. Rendering and state live elsewhere.
 */

import type { components } from '../api/schema';
import { courseKey } from '../degree/_degree';

/** Weekdays the week canvas shows. */
export const WEEKDAYS: readonly components['schemas']['Weekday'][] = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri'];

/** A meeting with a fixed weekly time, in minutes after midnight. */
export interface TimedMeeting {
  readonly days: readonly components['schemas']['Weekday'][];
  readonly start: number;
  readonly end: number;
}

/**
 * Two scheduled sections that meet at the same time on at least one day.
 */
export interface Overlap {
  readonly a: components['schemas']['Section'];
  readonly b: components['schemas']['Section'];
}

function timed(meeting: components['schemas']['Meeting']): TimedMeeting | null {
  const { days, start_minute: start, end_minute: end } = meeting;
  return days.length > 0 && start !== null && end !== null && end > start
    ? { days, start, end }
    : null;
}

/**
 * Lists a section's meetings that have a fixed time (not TBA).
 */
export function timedMeetings(section: components['schemas']['Section']): readonly TimedMeeting[] {
  let found = timedCache.get(section);
  if (found === undefined) {
    found = section.meetings.flatMap((m) => timed(m) ?? []);
    timedCache.set(section, found);
  }
  return found;
}

// Sections are immutable API records, and sorting, clash checks, and
// layout ask for their meetings constantly; each is computed once and
// dropped with its section.
const timedCache = new WeakMap<components['schemas']['Section'], readonly TimedMeeting[]>();

/**
 * Reports whether a section meets at a fixed weekly time.
 */
export function isTimed(section: components['schemas']['Section']): boolean {
  return timedMeetings(section).length > 0;
}

/**
 * The earliest start among a section's timed meetings, or null if TBA.
 */
export function startOf(section: components['schemas']['Section']): number | null {
  const starts = timedMeetings(section).map((m) => m.start);
  return starts.length > 0 ? Math.min(...starts) : null;
}

/**
 * Reports whether two sections share a day and their times intersect.
 */
export function overlaps(a: components['schemas']['Section'], b: components['schemas']['Section']): boolean {
  const bs = timedMeetings(b);
  return timedMeetings(a).some((x) =>
    bs.some(
      (y) =>
        x.start < y.end &&
        y.start < x.end &&
        x.days.some((d) => y.days.includes(d)),
    ),
  );
}

/**
 * Lists every overlapping pair among the given sections.
 */
export function findOverlaps(sections: readonly components['schemas']['Section'][]): readonly Overlap[] {
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
 * Reports whether two sections of a course can be taken together: their
 * link codes agree, or one has none (it pairs with any group).
 */
export function compatible(a: components['schemas']['Section'], b: components['schemas']['Section']): boolean {
  return (
    a.link_code === null || b.link_code === null || a.link_code === b.link_code
  );
}

/**
 * Reports whether adding `section` displaces `other`: they belong to the
 * same course and share a type or cannot be taken together.
 */
export function displaces(section: components['schemas']['Section'], other: components['schemas']['Section']): boolean {
  return (
    other.id !== section.id &&
    other.course_code === section.course_code &&
    (other.type === section.type || !compatible(other, section))
  );
}

/**
 * Reports whether adding `section` would collide with the schedule,
 * ignoring sections that adding it swaps out.
 */
export function clashes(
  section: components['schemas']['Section'],
  scheduled: readonly components['schemas']['Section'][],
): boolean {
  return scheduled.some((s) => !displaces(section, s) && overlaps(s, section));
}

/**
 * Sums units once per distinct course, counting a variable-unit course at
 * its minimum.
 */
export function totalUnits(
  sections: readonly components['schemas']['Section'][],
  coursesByCode: ReadonlyMap<string, components['schemas']['Course']>,
): number {
  let units = 0;
  for (const code of new Set(sections.map((s) => s.course_code))) {
    units += coursesByCode.get(code)?.units.min ?? 0;
  }
  return units;
}

/**
 * Lists the section types the chosen sections' link group still needs.
 *
 * The group is fixed by the first chosen section with a link code; until
 * one is chosen, every type the course offers counts.
 */
export function missingComponents(
  course: components['schemas']['Course'],
  chosen: readonly components['schemas']['Section'][],
): readonly string[] {
  const link = chosen.find((s) => s.link_code !== null)?.link_code ?? null;
  const required = new Set(
    course.sections
      .filter(
        (s) =>
          !s.is_cancelled &&
          (link === null || s.link_code === null || s.link_code === link),
      )
      .map((s) => s.type),
  );
  for (const s of chosen) {
    required.delete(s.type);
  }
  return [...required];
}

/**
 * Returns the prerequisite groups completed courses do not meet; the course
 * is takeable when this is empty. `completed` holds `courseKey` codes.
 */
export function unmetPrereqs(
  course: components['schemas']['Course'],
  completed: ReadonlySet<string>,
): readonly components['schemas']['RequisiteGroup'][] {
  return course.requisites.prerequisite.filter(
    (group) =>
      group.options.filter((option) =>
        option.every((ref) => completed.has(courseKey(ref.resolved ?? ref.code))),
      ).length < group.required_count,
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
const TYPE_RANK = new Map(TYPE_ORDER.map((type, i) => [type, i]));

/**
 * Sorts sections by type, then link code, then start time.
 */
export function bySectionOrder(a: components['schemas']['Section'], b: components['schemas']['Section']): number {
  const rank = (s: components['schemas']['Section']): number => TYPE_RANK.get(s.type) ?? TYPE_ORDER.length;
  const la = a.link_code ?? '';
  const lb = b.link_code ?? '';
  return (
    rank(a) - rank(b) ||
    (la < lb ? -1 : la > lb ? 1 : 0) ||
    (startOf(a) ?? Infinity) - (startOf(b) ?? Infinity)
  );
}

/**
 * Sections of one type within a course; a student takes exactly one.
 */
export interface SectionGroup {
  readonly type: string;
  readonly sections: readonly components['schemas']['Section'][];
}

/**
 * Groups a course's sections by type in display order (Lecture first).
 */
export function groupByType(
  sections: readonly components['schemas']['Section'][],
): readonly SectionGroup[] {
  const groups: { type: string; sections: components['schemas']['Section'][] }[] = [];
  for (const section of [...sections].sort(bySectionOrder)) {
    const last = groups[groups.length - 1];
    if (last?.type === section.type) {
      last.sections.push(section);
    } else {
      groups.push({ type: section.type, sections: [section] });
    }
  }
  return groups;
}
