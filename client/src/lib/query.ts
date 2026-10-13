/**
 * Parses the Library's single search box into catalog filters.
 *
 * Recognized tokens ("ge b", "4+") become structured filters and are removed
 * from the free-text query; whatever remains is sent as keywords. Also
 * reads which mode the bar is in from its first character (`readBar`).
 */

import { extractCourseCodes } from './degree';

/**
 * A recognized filter token, with the exact text that produced it so the
 * UI can remove it from the box.
 */
export interface QueryToken {
  readonly label: string;
  readonly raw: string;
}

/**
 * Structured interpretation of the search box text.
 */
export interface ParsedQuery {
  readonly keywords: string;
  readonly ge: string;
  readonly minRmp: number;
  readonly tokens: readonly QueryToken[];
}

const GE_PATTERN = /\bge[- ]?([a-h])\b/i;
const RATING_PATTERN = /(?:^|\s)([1-4](?:\.\d)?)\+(?=\s|$)/;

/**
 * Extracts a GE category ("ge b", "GE-B") and a minimum rating ("4+",
 * "3.5+"); the first occurrence of each wins.
 */
export function parseQuery(text: string): ParsedQuery {
  let rest = text;
  const tokens: QueryToken[] = [];
  let ge = '';
  let minRmp = 0;

  const geMatch = GE_PATTERN.exec(rest);
  if (geMatch) {
    ge = `GE-${geMatch[1].toUpperCase()}`;
    tokens.push({ label: ge, raw: geMatch[0] });
    rest = rest.replace(geMatch[0], ' ');
  }
  const ratingMatch = RATING_PATTERN.exec(rest);
  if (ratingMatch) {
    minRmp = Number(ratingMatch[1]);
    tokens.push({ label: `★ ${ratingMatch[1]}+`, raw: `${ratingMatch[1]}+` });
    rest = rest.replace(`${ratingMatch[1]}+`, ' ');
  }
  return {
    keywords: rest.replace(/\s+/g, ' ').trim(),
    ge,
    minRmp,
    tokens,
  };
}

/**
 * What the bar's text asks for, read from its first character: plain text
 * talks to the advisor, ">" finds courses, and "/" runs a command.
 */
export type Bar =
  | { readonly kind: 'chat'; readonly text: string }
  | { readonly kind: 'courses'; readonly query: string }
  /** A command still being named, such as "/" or "/to". */
  | { readonly kind: 'commands'; readonly name: string }
  /** "/took CSCI 103L, MATH 1": codes so far, and the one being typed. */
  | { readonly kind: 'took'; readonly codes: readonly string[]; readonly partial: string };

const TOOK = /^\/took\s/i;
/** What separates codes in a list: "CSCI 103L, MATH 125 and WRIT 150". */
const LIST_BREAK = /,|;|\band\b/i;

/**
 * Reads the bar's mode and its argument from its text.
 */
export function readBar(text: string): Bar {
  if (text.startsWith('>')) {
    return { kind: 'courses', query: text.slice(1).trim() };
  }
  if (TOOK.test(text)) {
    const args = text.replace(TOOK, '');
    const segments = args.split(LIST_BREAK);
    const partial = segments[segments.length - 1].trim();
    return { kind: 'took', codes: extractCourseCodes(args), partial };
  }
  if (text.startsWith('/')) {
    return { kind: 'commands', name: text.slice(1).trim().toLowerCase() };
  }
  return { kind: 'chat', text: text.trim() };
}

/**
 * The catalog query the bar implies: what follows ">", or the code being
 * typed after "/took". Empty means nothing to look up.
 */
export function searchTextOf(bar: Bar): string {
  return bar.kind === 'courses' ? bar.query : bar.kind === 'took' ? bar.partial : '';
}
