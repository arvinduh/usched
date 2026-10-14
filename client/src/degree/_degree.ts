/**
 * Pure helpers for course codes and degree program matching.
 *
 * Combines course code identity/formatting helpers with degree program
 * indexation and search ranking.
 */

import abbreviations from "../../../server/seeds/abbreviations.json";
import type { components } from "../api/schema";

const PARTS = /^\s*([A-Za-z]{2,5})[\s-]*(\d{3})([A-Za-z]*)\s*$/;
/** Letters that describe a course rather than identify it (L lab, g GE...). */
const ATTRIBUTES = new Set(["l", "g", "x", "m", "w", "p"]);

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
  const sequence = first && !ATTRIBUTES.has(first) ? first.toUpperCase() : "";
  return `${match[1].toUpperCase()}-${match[2]}${sequence}`;
}

/**
 * Formats a course ID for display: "CSCI-104L" becomes "CSCI 104L".
 */
export function displayCode(courseId: string): string {
  return courseId.replace("-", " ");
}

// Up to five prefix and four suffix letters: BISC 101Lxg, AMST 101gmw.
const CODE_PATTERN = /\b([A-Za-z]{2,5})[\s-]?(\d{3}[A-Za-z]{0,4})\b/g;

/**
 * Extracts distinct course-code candidates from free text, as identities
 * (courseKey). Look-alikes such as "the 100 level" survive; the catalog
 * decides which are courses.
 */
export function extractCourseCodes(text: string): readonly string[] {
  const codes = new Set<string>();
  for (const match of text.matchAll(CODE_PATTERN)) {
    codes.add(courseKey(`${match[1]}-${match[2]}`));
  }
  return [...codes];
}

const ALIASES: Readonly<Record<string, readonly string[] | undefined>> =
  abbreviations;

/** How far along a program leads: what the picker's chips filter by. */
export type Level = "major" | "minor" | "master" | "doctoral";

/** The chips' order and labels. */
export const LEVELS: readonly {
  readonly level: Level;
  readonly label: string;
}[] = [
  { level: "major", label: "Major" },
  { level: "minor", label: "Minor" },
  { level: "master", label: "Master's" },
  { level: "doctoral", label: "Doctoral" },
];

/**
 * Groups a program by its degree type: BS is a major, MS a master's, PhD
 * or MD doctoral. Null for types that fit none, which only "All" shows.
 */
export function levelOf(
  p: components["schemas"]["ProgramSummary"],
): Level | null {
  if (p.kind === "minor") {
    return "minor";
  }
  const type = p.degree_type ?? "";
  if (type.startsWith("B")) {
    return "major";
  }
  // Before master's: MD is a doctorate, as are PhD, JD, EdD, and DPT.
  if (/^D|D$/.test(type)) {
    return "doctoral";
  }
  return /^(M|LLM)/.test(type) ? "master" : null;
}

/** A program with its title split once, for matching on every keystroke. */
export interface IndexedProgram {
  readonly program: components["schemas"]["ProgramSummary"];
  readonly words: readonly string[];
}

function wordsOf(text: string): string[] {
  return text
    .toLowerCase()
    .split(/[^a-z0-9]+/)
    .filter(Boolean);
}

/**
 * Splits each title into words, alphabetically by title.
 */
export function indexPrograms(
  programs: readonly components["schemas"]["ProgramSummary"][],
): IndexedProgram[] {
  return programs
    .map((program) => ({ program, words: wordsOf(program.title) }))
    .sort((a, b) => a.program.title.localeCompare(b.program.title));
}

/** Where `phrase` starts in `words`, each word a prefix in turn; -1 if nowhere. */
function phraseAt(words: readonly string[], phrase: readonly string[]): number {
  for (let i = 0; i + phrase.length <= words.length; i += 1) {
    if (phrase.every((p, k) => words[i + k].startsWith(p))) {
      return i;
    }
  }
  return -1;
}

/**
 * Programs whose titles hold every query word or one of its expansions,
 * best first: matches nearer the start of the title rank higher, ties stay
 * alphabetical. An empty query keeps every program.
 */
export function rankPrograms(
  index: readonly IndexedProgram[],
  query: string,
): components["schemas"]["ProgramSummary"][] {
  const spellings = wordsOf(query).map((word) => [
    [word],
    ...(ALIASES[word] ?? []).map(wordsOf),
  ]);
  const ranked: {
    program: components["schemas"]["ProgramSummary"];
    rank: number;
  }[] = [];
  for (const { program, words } of index) {
    let rank = 0;
    for (const alternatives of spellings) {
      let at = Infinity;
      for (const phrase of alternatives) {
        const i = phraseAt(words, phrase);
        if (i >= 0 && i < at) {
          at = i;
        }
      }
      if (at === Infinity) {
        rank = -1;
        break;
      }
      rank += at;
    }
    if (rank >= 0) {
      ranked.push({ program, rank });
    }
  }
  // Stable sort: equal ranks keep the index's alphabetical order.
  return ranked.sort((a, b) => a.rank - b.rank).map((r) => r.program);
}
