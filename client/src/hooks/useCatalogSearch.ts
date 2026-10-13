/**
 * Debounced, paginated course catalog search driven by one text box.
 *
 * Owns the raw search text, its parsed filters, and the currently loaded
 * result pages. Results are transient view data; anything the plan must keep
 * is pinned by `usePlanCourses`, never read back from here.
 */

import { startTransition, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { searchCourses } from '../api/client';
import { parseQuery } from '../lib/query';
import type { ParsedQuery } from '../lib/query';
import type { Course } from '../types';

// About two screens of results: enough to scroll into while the next page
// loads, without rendering rows nobody sees.
const PAGE_SIZE = 40;
const DEBOUNCE_MS = 150;
const NO_COURSES: readonly Course[] = [];

/**
 * Search text, its interpretation, loaded results, and paging controls.
 */
export interface CatalogSearch {
  readonly text: string;
  readonly setText: (text: string) => void;
  readonly parsed: ParsedQuery;
  readonly courses: readonly Course[];
  /** True until the current text's first page arrives. */
  readonly isSearching: boolean;
  readonly hasMore: boolean;
  readonly loadMore: () => void;
}

/**
 * Re-queries `term`'s catalog 150 ms after the text settles and appends
 * further pages on demand. Results land in transitions, so rendering them
 * never blocks typing. Empty text loads nothing: the Library shows saved
 * and suggested courses instead.
 */
export function useCatalogSearch(term: number): CatalogSearch {
  const [text, setText] = useState('');
  const parsed = useMemo(() => parseQuery(text), [text]);
  const { keywords, ge, minRmp } = parsed;
  const isEmpty = !keywords && !ge && minRmp === 0;

  const [courses, setCourses] = useState<readonly Course[]>([]);
  // Which query `courses` answers, so stale results never read as final.
  const queryKey = `${term}|${keywords}|${ge}|${minRmp}`;
  const [resultKey, setResultKey] = useState('');
  // Server offset of the next page; can exceed `courses.length` when a page
  // repeats rows already shown.
  const [nextOffset, setNextOffset] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [isLoadingMore, setIsLoadingMore] = useState(false);

  const fetchPage = useCallback(
    (offset: number) =>
      searchCourses(term, {
        q: keywords || undefined,
        ge: ge || undefined,
        minRating: minRmp > 0 ? minRmp : undefined,
        limit: PAGE_SIZE,
        offset,
      }),
    [term, keywords, ge, minRmp],
  );
  // The query whose results are on screen; late pages of older queries are
  // dropped instead of appended.
  const activeFetch = useRef(fetchPage);
  useEffect(() => {
    activeFetch.current = fetchPage;
  }, [fetchPage]);

  useEffect(() => {
    if (isEmpty) {
      return;
    }
    let stale = false;
    const timer = setTimeout(() => {
      fetchPage(0)
        .then((items) => {
          if (stale) {
            return;
          }
          // Rendering a page of results yields to typing, so a keystroke
          // never waits behind rows from the previous query.
          startTransition(() => {
            setCourses(items);
            setResultKey(queryKey);
            setNextOffset(items.length);
            setHasMore(items.length >= PAGE_SIZE);
          });
        })
        .catch(console.error);
    }, DEBOUNCE_MS);
    return () => {
      stale = true;
      clearTimeout(timer);
    };
  }, [fetchPage, isEmpty, queryKey]);

  const loadMore = useCallback((): void => {
    if (isLoadingMore || !hasMore) {
      return;
    }
    setIsLoadingMore(true);
    fetchPage(nextOffset)
      .then((items) => {
        if (activeFetch.current !== fetchPage) {
          return;
        }
        startTransition(() => {
          setNextOffset((prev) => prev + items.length);
          setCourses((prev) => {
            const seen = new Set(prev.map((c) => c.code));
            return [...prev, ...items.filter((c) => !seen.has(c.code))];
          });
          setHasMore(items.length >= PAGE_SIZE);
        });
      })
      .catch(console.error)
      .finally(() => setIsLoadingMore(false));
  }, [isLoadingMore, hasMore, fetchPage, nextOffset]);

  // Empty text shows no results without waiting for the stale page to clear.
  return {
    text,
    setText,
    parsed,
    courses: isEmpty ? NO_COURSES : courses,
    isSearching: !isEmpty && resultKey !== queryKey,
    hasMore: !isEmpty && hasMore,
    loadMore,
  };
}
