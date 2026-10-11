/**
 * Parses the Library's single search box into catalog filters.
 *
 * Recognized tokens ("ge b", "4+") become structured filters and are removed
 * from the free-text query; whatever remains is sent as keywords. Also
 * decides when the text reads as a question for the advisor.
 */

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
