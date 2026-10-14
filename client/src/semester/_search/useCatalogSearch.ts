/**
 * Debounced, paginated course catalog search driven by the bar.
 *
 * Owns the bar's raw text, the mode it reads as, the filters of the
 * catalog query that mode implies, and the currently loaded result pages.
 * Results are transient view data; anything the plan must keep
 * is pinned by `usePlanCourses`, never read back from here.
 */

import { startTransition, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { Dispatch, SetStateAction } from 'react';
import { searchCourses } from '../../api/client';
import { DEBOUNCE_MS, PAGE_SIZE } from '../../config';
import { parseQuery, readBar, searchTextOf } from './_query';
import type { Bar, ParsedQuery } from './_query';
import type { components } from '../../api/schema';

const NO_COURSES: readonly components['schemas']['Course'][] = [];

/**
 * Search text, its interpretation, loaded results, and paging controls.
 */
export interface CatalogSearch {
  readonly text: string;
  /** Takes the new text, or an edit of the current one. */
  readonly setText: Dispatch<SetStateAction<string>>;
  readonly bar: Bar;
  readonly parsed: ParsedQuery;
  readonly courses: readonly components['schemas']['Course'][];
  /** True until the current text's first page arrives. */
  readonly isSearching: boolean;
  readonly hasMore: boolean;
  readonly loadMore: () => void;
}

function _isAbortError(err: unknown): boolean {
  return (
    (err instanceof DOMException && err.name === 'AbortError') ||
    (typeof err === 'object' && err !== null && (err as { name?: string }).name === 'AbortError')
  );
}

/**
 * Re-queries `term`'s catalog 60 ms after the text settles and appends
 * further pages on demand. Results land in transitions, so rendering them
 * never blocks typing. Only ">" text and a code after "/took" query the
 * catalog; chat and empty text load nothing.
 */
export function useCatalogSearch(term: number): CatalogSearch {
  const [text, setText] = useState('');
  const bar = useMemo(() => readBar(text), [text]);
  const parsed = useMemo(() => parseQuery(searchTextOf(bar)), [bar]);
  const { keywords, ge, minRmp } = parsed;
  const isEmpty = !keywords && !ge && minRmp === 0;

  const [courses, setCourses] = useState<readonly components['schemas']['Course'][]>([]);
  // Which query `courses` answers, so stale results never read as final.
  const queryKey = `${term}|${keywords}|${ge}|${minRmp}`;
  const [resultKey, setResultKey] = useState('');
  // Server offset of the next page; can exceed `courses.length` when a page
  // repeats rows already shown.
  const [nextOffset, setNextOffset] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [isLoadingMore, setIsLoadingMore] = useState(false);

  const fetchPage = useCallback(
    (offset: number, signal?: AbortSignal) =>
      searchCourses(
        term,
        {
          q: keywords || undefined,
          ge: ge || undefined,
          minRating: minRmp > 0 ? minRmp : undefined,
          limit: PAGE_SIZE,
          offset,
        },
        signal,
      ),
    [term, keywords, ge, minRmp],
  );
  // The query whose results are on screen; late pages of older queries are
  // dropped instead of appended.
  const activeFetch = useRef(fetchPage);
  useEffect(() => {
    activeFetch.current = fetchPage;
  }, [fetchPage]);

  const loadMoreAbort = useRef<AbortController | null>(null);

  useEffect(() => {
    loadMoreAbort.current?.abort();
    if (isEmpty) {
      return;
    }
    const controller = new AbortController();
    const timer = setTimeout(() => {
      fetchPage(0, controller.signal)
        .then((items) => {
          if (controller.signal.aborted) {
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
        .catch((err: unknown) => {
          if (_isAbortError(err)) {
            return;
          }
          console.error(err);
        });
    }, DEBOUNCE_MS);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [fetchPage, isEmpty, queryKey]);

  useEffect(() => {
    return () => {
      loadMoreAbort.current?.abort();
    };
  }, []);

  const loadMore = useCallback((): void => {
    if (isLoadingMore || !hasMore) {
      return;
    }
    loadMoreAbort.current?.abort();
    const controller = new AbortController();
    loadMoreAbort.current = controller;
    setIsLoadingMore(true);
    fetchPage(nextOffset, controller.signal)
      .then((items) => {
        if (controller.signal.aborted || activeFetch.current !== fetchPage) {
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
      .catch((err: unknown) => {
        if (_isAbortError(err)) {
          return;
        }
        console.error(err);
      })
      .finally(() => {
        setIsLoadingMore(false);
      });
  }, [isLoadingMore, hasMore, fetchPage, nextOffset]);

  // Empty text shows no results without waiting for the stale page to clear.
  return {
    text,
    setText,
    bar,
    parsed,
    courses: isEmpty ? NO_COURSES : courses,
    isSearching: !isEmpty && resultKey !== queryKey,
    hasMore: !isEmpty && hasMore,
    loadMore,
  };
}
