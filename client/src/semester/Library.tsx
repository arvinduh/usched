/**
 * The Library pane: one search box for finding courses or asking the
 * advisor.
 *
 * With empty text it shows saved courses and degree-suggested next courses;
 * otherwise it shows parsed filter chips, an "Ask" row when the text reads as
 * a question, and catalog results with infinite scroll. Plan edits and the
 * advisor hand-off are delegated to the caller.
 */

import React, { useEffect, useRef, useState } from 'react';
import { Search, Sparkles, X } from 'lucide-react';
import type { CatalogSearch } from '../hooks/useCatalogSearch';
import { displayCode } from '../lib/degree';
import { looksLikeQuestion } from '../lib/query';
import { clashes, isTimed } from '../lib/schedule';
import type { Course, Section } from '../types';
import { CourseRow } from './CourseRow';
import type { CourseRowProps } from './CourseRow';
import styles from './Library.module.css';

/**
 * A degree course the student can take next.
 */
export interface Suggestion {
  readonly id: string;
  readonly title: string;
}

/**
 * Properties for the Library pane.
 */
export interface LibraryProps {
  readonly search: CatalogSearch;
  readonly inputRef: React.RefObject<HTMLInputElement | null>;
  readonly savedCourses: readonly Course[];
  readonly suggestions: readonly Suggestion[];
  readonly activeSections: readonly Section[];
  readonly scheduledCourseIds: readonly string[];
  readonly completed: ReadonlySet<string>;
  readonly watched: ReadonlySet<string>;
  readonly onToggleSave: (course: Course) => void;
  readonly onToggleSection: (section: Section, course: Course) => void;
  readonly otherVariants: CourseRowProps['otherVariants'];
  readonly onAddToVariant: CourseRowProps['onAddToVariant'];
  readonly onAsk: (text: string) => void;
}

/**
 * Reports whether some section of the course can join the week without a
 * time clash. Courses that only meet TBA always fit.
 */
function fitsWeek(course: Course, scheduled: readonly Section[]): boolean {
  const timed = course.sections.filter(isTimed);
  return timed.length === 0 || timed.some((s) => !clashes(s, scheduled));
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
    onToggleSection,
    otherVariants,
    onAddToVariant,
    onAsk,
  } = props;
  const [fitsOnly, setFitsOnly] = useState(false);
  const { text, setText, parsed, courses, isSearching, hasMore, loadMore } =
    search;
  const isQuestion = looksLikeQuestion(text);
  const activeIds = new Set(activeSections.map((s) => s.id));

  const results = fitsOnly
    ? courses.filter((c) => fitsWeek(c, activeSections))
    : courses;

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
        <button
          type="button"
          className={`${styles.chip} ${fitsOnly ? styles.chipOn : ''}`}
          aria-pressed={fitsOnly}
          onClick={() => setFitsOnly((v) => !v)}
        >
          Fits my week
        </button>
      </div>

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
                {fitsOnly && courses.length > 0
                  ? 'Nothing here fits your week.'
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
                {(fitsOnly
                  ? savedCourses.filter((c) => fitsWeek(c, activeSections))
                  : savedCourses
                ).map(row)}
              </section>
            )}
            {suggestions.length > 0 && (
              <section>
                <h3 className={styles.heading}>Next up</h3>
                {suggestions.map((s) => (
                  <button
                    key={s.id}
                    type="button"
                    data-nav="suggestion"
                    className={styles.suggestion}
                    onClick={() => setText(displayCode(s.id))}
                  >
                    <span className={styles.code}>{displayCode(s.id)}</span>
                    <span className={styles.suggestionTitle}>{s.title}</span>
                  </button>
                ))}
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
