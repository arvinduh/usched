/**
 * The Library pane: one search box for finding courses or asking the
 * advisor.
 *
 * With empty text it shows saved courses and degree-suggested next courses;
 * otherwise it shows parsed filter chips, an "Ask" row when the text reads as
 * a question, and catalog results with infinite scroll. Every list honors
 * the filter panel and sort. Plan edits and the
 * advisor hand-off are delegated to the caller.
 */

import React, { useEffect, useRef, useState } from 'react';
import { ListFilter, Search, Sparkles, X } from 'lucide-react';
import type { CatalogSearch } from '../hooks/useCatalogSearch';
import { NO_FILTER, activeFilterCount, courseMatches, sortCourses } from '../lib/filter';
import type { DayPart, SectionFilter, SortKey } from '../lib/filter';
import { looksLikeQuestion } from '../lib/query';
import type { Course, Section } from '../types';
import { CourseRow } from './CourseRow';
import type { CourseRowProps } from './CourseRow';
import { FilterPanel } from './FilterPanel';
import styles from './Library.module.css';

/**
 * Properties for the Library pane.
 */
export interface LibraryProps {
  readonly search: CatalogSearch;
  readonly inputRef: React.RefObject<HTMLInputElement | null>;
  readonly savedCourses: readonly Course[];
  /** Degree courses the student can take next. */
  readonly suggestions: readonly Course[];
  readonly activeSections: readonly Section[];
  readonly scheduledCourseIds: readonly string[];
  readonly completed: ReadonlySet<string>;
  readonly watched: ReadonlySet<string>;
  readonly onToggleSave: (course: Course) => void;
  readonly onToggleTaken: CourseRowProps['onToggleTaken'];
  readonly onToggleSection: (section: Section, course: Course) => void;
  readonly otherVariants: CourseRowProps['otherVariants'];
  readonly onAddToVariant: CourseRowProps['onAddToVariant'];
  readonly onAsk: (text: string) => void;
}

const SORT_LABELS: Record<SortKey, string> = {
  relevance: 'Relevance',
  rating: 'Highest rated',
  easiest: 'Easiest',
  code: 'Course code',
};

const DAY_PART_LABELS: Record<DayPart, string> = {
  morning: 'Mornings',
  afternoon: 'Afternoons',
  evening: 'Evenings',
};

interface FilterChip {
  readonly label: string;
  readonly clear: (f: SectionFilter) => SectionFilter;
}

function without<T>(set: ReadonlySet<T>, value: T): ReadonlySet<T> {
  return new Set([...set].filter((x) => x !== value));
}

/**
 * Lists the active section filters as removable chips.
 */
function filterChips(f: SectionFilter): readonly FilterChip[] {
  const chips: FilterChip[] = [];
  for (const d of f.excludedDays) {
    chips.push({
      label: `No ${d}`,
      clear: (g) => ({ ...g, excludedDays: without(g.excludedDays, d) }),
    });
  }
  for (const p of f.dayParts) {
    chips.push({
      label: DAY_PART_LABELS[p],
      clear: (g) => ({ ...g, dayParts: without(g.dayParts, p) }),
    });
  }
  if (f.openSeatsOnly) {
    chips.push({ label: 'Open seats', clear: (g) => ({ ...g, openSeatsOnly: false }) });
  }
  if (f.fitsWeekOnly) {
    chips.push({ label: 'Fits my week', clear: (g) => ({ ...g, fitsWeekOnly: false }) });
  }
  return chips;
}

/**
 * Renders the search box and whichever list the text calls for.
 */
export function Library(props: LibraryProps): React.JSX.Element {
  const {
    search,
    inputRef,
    savedCourses,
    suggestions,
    activeSections,
    scheduledCourseIds,
    completed,
    watched,
    onToggleSave,
    onToggleTaken,
    onToggleSection,
    otherVariants,
    onAddToVariant,
    onAsk,
  } = props;
  const [filter, setFilter] = useState<SectionFilter>(NO_FILTER);
  const [sort, setSort] = useState<SortKey>('relevance');
  const [panelOpen, setPanelOpen] = useState(false);
  const { text, setText, parsed, courses, isSearching, hasMore, loadMore } =
    search;
  const isQuestion = looksLikeQuestion(text);
  const activeIds = new Set(activeSections.map((s) => s.id));
  const filterCount = activeFilterCount(filter) + parsed.tokens.length;

  const refine = (list: readonly Course[]): readonly Course[] =>
    sortCourses(
      list.filter((c) => courseMatches(c, filter, activeSections)),
      sort,
    );
  const results = refine(courses);

  const sentinel = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const node = sentinel.current;
    if (!node || !hasMore) {
      return;
    }
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((e) => e.isIntersecting)) {
        loadMore();
      }
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, [hasMore, loadMore]);

  const row = (course: Course): React.JSX.Element => (
    <CourseRow
      key={course.id}
      course={course}
      isSaved={watched.has(course.id)}
      completed={completed}
      activeSectionIds={activeIds}
      scheduledCourseIds={scheduledCourseIds}
      onToggleSave={onToggleSave}
      onToggleTaken={onToggleTaken}
      onToggleSection={onToggleSection}
      otherVariants={otherVariants}
      onAddToVariant={onAddToVariant}
    />
  );

  // Arrow keys walk every `data-nav` row in order; Right/Left expand and
  // collapse the course under focus. Enter is the buttons' native click.
  const list = useRef<HTMLDivElement>(null);
  const moveFocus = (from: Element | null, step: 1 | -1): void => {
    const items = [...(list.current?.querySelectorAll<HTMLElement>('[data-nav]') ?? [])];
    const index = from ? items.indexOf(from as HTMLElement) : -1;
    const next = index === -1 ? (step === 1 ? items[0] : undefined) : items[index + step];
    if (next) {
      next.focus();
      next.scrollIntoView({ block: 'nearest' });
    } else if (step === -1) {
      inputRef.current?.focus();
    }
  };
  const handleListKeyDown = (e: React.KeyboardEvent<HTMLDivElement>): void => {
    const target = e.target as HTMLElement;
    const course = target
      .closest('[data-course]')
      ?.querySelector<HTMLElement>('[data-nav="course"]');
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      moveFocus(target, e.key === 'ArrowDown' ? 1 : -1);
    } else if (e.key === 'ArrowRight' && course?.getAttribute('aria-expanded') === 'false') {
      e.preventDefault();
      course.click();
    } else if (e.key === 'ArrowLeft' && course?.getAttribute('aria-expanded') === 'true') {
      e.preventDefault();
      course.click();
      course.focus();
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>): void => {
    if (e.key === 'Enter' && text.trim() && (isQuestion || e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      onAsk(text.trim());
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      moveFocus(null, 1);
    } else if (e.key === 'Escape') {
      if (text) {
        setText('');
      } else {
        e.currentTarget.blur();
      }
    }
  };

  return (
    <div className={styles.library}>
      <div className={styles.searchBox}>
        <Search size={14} className={styles.searchIcon} />
        <input
          ref={inputRef}
          className={styles.input}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Search or ask"
          aria-label="Search courses or ask the advisor"
          spellCheck={false}
        />
        {!text && <kbd className={styles.kbd}>/</kbd>}
      </div>

      <div className={styles.chips}>
        {parsed.tokens.map((token) => (
          <button
            key={token.raw}
            type="button"
            className={`${styles.chip} ${styles.chipOn}`}
            onClick={() => setText(text.replace(token.raw, '').trim())}
          >
            {token.label}
            <X size={11} />
          </button>
        ))}
        {filterChips(filter).map((chip) => (
          <button
            key={chip.label}
            type="button"
            className={`${styles.chip} ${styles.chipOn}`}
            onClick={() => setFilter(chip.clear)}
          >
            {chip.label}
            <X size={11} />
          </button>
        ))}
        <button
          type="button"
          className={`${styles.chip} ${panelOpen ? styles.chipActive : ''}`}
          aria-expanded={panelOpen}
          onClick={() => setPanelOpen((v) => !v)}
        >
          <ListFilter size={12} />
          Filter
          {filterCount > 0 && <span className={styles.badge}>{filterCount}</span>}
        </button>
        <label className={styles.sort}>
          <span className={styles.srOnly}>Sort by</span>
          <select value={sort} onChange={(e) => setSort(e.target.value as SortKey)}>
            {Object.entries(SORT_LABELS).map(([key, label]) => (
              <option key={key} value={key}>
                {label}
              </option>
            ))}
          </select>
        </label>
      </div>

      {panelOpen && (
        <FilterPanel
          filter={filter}
          onFilter={setFilter}
          parsed={parsed}
          text={text}
          setText={setText}
        />
      )}

      <div className={styles.list} ref={list} onKeyDown={handleListKeyDown}>
        {text.trim() && isQuestion && (
          <button
            type="button"
            data-nav="ask"
            className={styles.ask}
            onClick={() => onAsk(text.trim())}
          >
            <Sparkles size={13} />
            <span className={styles.askText}>Ask “{text.trim()}”</span>
            <kbd className={styles.kbd}>⏎</kbd>
          </button>
        )}

        {text.trim() ? (
          <>
            {results.map(row)}
            {results.length === 0 && !hasMore && !isSearching && (
              <p className={styles.empty}>
                {courses.length > 0
                  ? 'Nothing matches these filters.'
                  : 'No matching courses.'}
              </p>
            )}
            <div ref={sentinel} className={styles.sentinel} />
          </>
        ) : (
          <>
            {savedCourses.length > 0 && (
              <section>
                <h3 className={styles.heading}>Saved</h3>
                {refine(savedCourses).map(row)}
              </section>
            )}
            {suggestions.length > 0 && (
              <section>
                <h3 className={styles.heading}>Next up</h3>
                {refine(suggestions).map(row)}
              </section>
            )}
            {savedCourses.length === 0 && suggestions.length === 0 && (
              <p className={styles.empty}>
                Search by code, title, or topic. Add “ge b” or “4+” to filter.
              </p>
            )}
          </>
        )}
      </div>
    </div>
  );
}
