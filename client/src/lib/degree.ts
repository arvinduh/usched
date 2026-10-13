/**
 * Pure helpers for course codes in degree and plan contexts.
 *
 * Sources spell one course differently: attribute letters move or vanish
 * (MATH-118gx, MATH-118xg, "MATH 118"), but department, number, and
 * sequence letter never change. This module owns that identity, mirroring
 * the server's codes.identity, and code extraction from pasted text.
 */

const PARTS = /^\s*([A-Za-z]{2,5})[\s-]*(\d{3})([A-Za-z]*)\s*$/;
/** Letters that describe a course rather than identify it (L lab, g GE...). */
const ATTRIBUTES = new Set(['l', 'g', 'x', 'm', 'w', 'p']);

/**
 * A course code's identity for comparisons: CHEM-105aLg becomes CHEM-105A
 * and MATH-118gx becomes MATH-118. Text that is not a code is upper-cased.
 */
export function courseKey(courseId: string): string {
  const match = PARTS.exec(courseId);
  if (!match) {
    return courseId.trim().toUpperCase();
  }
  const first = match[3].slice(0, 1).toLowerCase();
  const sequence = first && !ATTRIBUTES.has(first) ? first.toUpperCase() : '';
  return `${match[1].toUpperCase()}-${match[2]}${sequence}`;
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
