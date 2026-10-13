/**
 * Parses the Library's single search box into catalog filters.
 *
 * Recognized tokens ("ge b", "4+") become structured filters and are removed
 * from the free-text query; whatever remains is sent as keywords. Also
 * decides when the text reads as a question for the advisor, and when it
 * records courses taken ("took CSCI 103L, MATH 125").
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
 * Reports whether text reads as a question for the advisor rather than a
 * catalog lookup: a question mark, or three or more words.
 */
export function looksLikeQuestion(text: string): boolean {
  const trimmed = text.trim();
  return trimmed.includes('?') || trimmed.split(/\s+/).length >= 3;
}

const TOOK = /^\s*(?:i\s+)?(?:took|taken|have taken|completed|finished|passed)\b/i;
const CODE = /\b[A-Za-z]{2,5}[\s-]?\d{3}[A-Za-z]{0,4}\b/g;
/** What may join codes in a list: "CSCI 103L, MATH 125 and WRIT 150." */
const JOINERS = /\b(?:and|also|plus|too)\b|[\s,;.&+]/gi;

/**
 * The course codes a "took ..." line names, as identities, or null when
 * the text is not one. Only codes and list joiners may follow "took";
 * anything more ("I took CSCI 103L, what next?") is a question for the
 * advisor. The catalog still decides which codes are courses.
 */
export function takenCodes(text: string): readonly string[] | null {
  if (!TOOK.test(text)) {
    return null;
  }
  const rest = text.replace(TOOK, '');
  if (rest.replace(CODE, '').replace(JOINERS, '') !== '') {
    return null;
  }
  const codes = extractCourseCodes(rest);
  return codes.length > 0 ? codes : null;
}
