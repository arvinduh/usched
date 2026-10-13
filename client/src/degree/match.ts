/**
 * Finds programs from what a student types, abbreviations included.
 *
 * Reads the server's abbreviation list, so "ai for business" finds
 * Artificial Intelligence for Business and "cs games" finds Computer
 * Science (Games), just as course search expands them. Ranks and groups
 * programs only; the picker owns presentation.
 */

import abbreviations from '../../../server/seeds/abbreviations.json';
import type { ProgramSummary } from '../types';

const ALIASES: Readonly<Record<string, readonly string[] | undefined>> = abbreviations;

/** How far along a program leads: what the picker's chips filter by. */
export type Level = 'major' | 'minor' | 'master' | 'doctoral';

/** The chips' order and labels. */
export const LEVELS: readonly { readonly level: Level; readonly label: string }[] = [
  { level: 'major', label: 'Major' },
  { level: 'minor', label: 'Minor' },
  { level: 'master', label: "Master's" },
  { level: 'doctoral', label: 'Doctoral' },
];

/**
 * Groups a program by its degree type: BS is a major, MS a master's, PhD
 * or MD doctoral. Null for types that fit none, which only "All" shows.
 */
export function levelOf(p: ProgramSummary): Level | null {
  if (p.kind === 'minor') {
    return 'minor';
  }
  const type = p.degree_type ?? '';
  if (type.startsWith('B')) {
    return 'major';
  }
  // Before master's: MD is a doctorate, as are PhD, JD, EdD, and DPT.
  if (/^D|D$/.test(type)) {
    return 'doctoral';
  }
  return /^(M|LLM)/.test(type) ? 'master' : null;
}

/** A program with its title split once, for matching on every keystroke. */
export interface IndexedProgram {
  readonly program: ProgramSummary;
  readonly words: readonly string[];
}

function wordsOf(text: string): string[] {
  return text.toLowerCase().split(/[^a-z0-9]+/).filter(Boolean);
}

/**
 * Splits each title into words, alphabetically by title.
 */
export function indexPrograms(programs: readonly ProgramSummary[]): IndexedProgram[] {
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
): ProgramSummary[] {
  const spellings = wordsOf(query).map((word) => [
    [word],
    ...(ALIASES[word] ?? []).map(wordsOf),
  ]);
  const ranked: { program: ProgramSummary; rank: number }[] = [];
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
