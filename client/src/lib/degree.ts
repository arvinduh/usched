/**
 * Pure helpers for reading degree programs and requirements.
 *
 * Parses program titles into name, emphasis, and degree type; classifies
 * requirement categories into all / choice / open-pool shapes; and extracts
 * course codes from pasted text. Course IDs are compared case-insensitively
 * because degree rules and the catalog disagree on suffix case
 * ("BUAD-310G" vs "BUAD-310g").
 */

import type { DegreeCategory } from '../types';

/** Units assumed for a required course the catalog does not list. */
const DEFAULT_UNITS = 4;

/**
 * Canonical form of a course ID for comparisons.
 */
export function courseKey(courseId: string): string {
  return courseId.trim().toUpperCase();
}

/**
 * Formats a course ID for display: "CSCI-104L" becomes "CSCI 104L".
 */
export function displayCode(courseId: string): string {
  return courseId.replace('-', ' ');
}

/**
 * A degree program title split into its parts.
 */
export interface DegreeTitle {
  readonly name: string;
  /** Concentration in parentheses before the type, e.g. "Asian American Studies". */
  readonly emphasis: string;
  /** Degree type such as "BS", or empty when the title carries none. */
  readonly type: string;
}

const TITLE_PATTERN = /^(.*?)(?:\s+\(([^()]+)\))?\s+\((B[A-Za-z]+)\)$/;

/**
 * Splits "American Studies and Ethnicity (Asian American Studies) (BA)" into
 * name, emphasis, and type. Titles without a trailing degree type keep their
 * full text as the name.
 */
export function parseDegreeTitle(title: string): DegreeTitle {
  const match = TITLE_PATTERN.exec(title.trim());
  if (!match) {
    return { name: title.trim(), emphasis: '', type: '' };
  }
  return { name: match[1], emphasis: match[2] ?? '', type: match[3] };
}

/**
 * How a requirement category asks to be satisfied.
 *
 * - `all`: take every listed course.
 * - `choice`: take some of the listed courses; `pick` is exact only when
 *   every option carries the same units, otherwise null.
 * - `pool`: take the listed courses plus `openUnits` of anything matching.
 */
export type CategoryShape =
  | { readonly kind: 'all' }
  | { readonly kind: 'choice'; readonly pick: number | null }
  | { readonly kind: 'pool'; readonly openUnits: number };

/**
 * Infers a category's shape by comparing required units against the units
 * of its listed courses. The rules data stores no explicit OR groups, so
 * this is the best available reading.
 */
export function categoryShape(
  category: DegreeCategory,
  unitsOf: (courseKey: string) => number | undefined,
): CategoryShape {
  const units = category.required_courses.map(
    (id) => unitsOf(courseKey(id)) ?? DEFAULT_UNITS,
  );
  const listed = units.reduce((a, b) => a + b, 0);
  if (category.required_units < listed && units.length > 1) {
    const uniform = units.every((u) => u === units[0]) && units[0] > 0;
    return {
      kind: 'choice',
      pick: uniform ? Math.ceil(category.required_units / units[0]) : null,
    };
  }
  if (category.required_units > listed) {
    return { kind: 'pool', openUnits: category.required_units - listed };
  }
  return { kind: 'all' };
}

const CODE_PATTERN = /\b([A-Za-z]{2,4})[\s-]?(\d{3}[A-Za-z]{0,2})\b/g;

/**
 * Extracts distinct course codes from free text such as a pasted transcript,
 * normalized to "DEPT-123X".
 */
export function extractCourseCodes(text: string): readonly string[] {
  const codes = new Set<string>();
  for (const match of text.matchAll(CODE_PATTERN)) {
    codes.add(courseKey(`${match[1]}-${match[2]}`));
  }
  return [...codes];
}
