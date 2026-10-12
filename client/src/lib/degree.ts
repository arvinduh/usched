/**
 * Pure helpers for course codes in degree and plan contexts.
 *
 * Course codes are compared case-insensitively because the catalogue and
 * the schedule of classes disagree on suffix case ("BUAD-310G" vs
 * "BUAD-310g"); this module owns that canonical form and code extraction
 * from pasted text.
 */

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
