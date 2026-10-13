/**
 * The Assistant pane: an advisor-first column with course search built in.
 *
 * The body shows the conversation (or, before one starts, starter prompts
 * with saved and suggested courses), or the full search results with
 * filters and sort when the user asks to see them. The composer is pinned
 * at the bottom. Plan edits, chat sending, and navigation belong to the
 * caller; this pane owns only its filter and sort state.
 */

import React, { useEffect, useRef, useState } from 'react';
import { ArrowLeft, ListFilter, X } from 'lucide-react';
import type { CatalogSearch } from '../hooks/useCatalogSearch';
import { NO_FILTER, activeFilterCount, courseMatches, sortCourses } from '../lib/filter';
import type { DayPart, SectionFilter, SortKey } from '../lib/filter';
import type { Chip, ChatMessage, Course, Section } from '../types';
import { Composer } from './Composer';
import { CourseRow } from './CourseRow';
import type { CourseRowProps } from './CourseRow';
import { FilterPanel } from './FilterPanel';
import { Thread } from './Thread';
import styles from './Assistant.module.css';

/** What the pane body shows. */
export type AssistantView = 'chat' | 'results';

const STARTERS = [
  'What should I take next semester?',
  'Find an easy GE that fits my week',
  'Am I on track to graduate?',
] as const;

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
 * Properties for the Assistant pane.
 */
export interface AssistantProps {
  readonly view: AssistantView;
  readonly onView: (view: AssistantView) => void;
  readonly search: CatalogSearch;
  readonly inputRef: React.RefObject<HTMLInputElement | null>;
  readonly messages: readonly ChatMessage[];
  readonly busy: boolean;
  readonly onAsk: (text: string) => void;
  readonly onChip: (chip: Chip) => void;
  readonly onProject: (chips: readonly Chip[]) => void;
  readonly onNewChat: () => void;
  /** Opens a course: expands it and shows it in the results. */
  readonly onOpenCourse: (course: Course) => void;
  /** Opens a course the advisor named, by ID. */
  readonly onOpenCourseId: (courseId: string) => void;
  readonly savedCourses: readonly Course[];
  readonly suggestions: readonly Course[];
  readonly activeSections: readonly Section[];
  readonly scheduledCourseIds: readonly string[];
  readonly completed: ReadonlySet<string>;
  readonly watched: ReadonlySet<string>;
  readonly onToggleSave: CourseRowProps['onToggleSave'];
  readonly onToggleTaken: CourseRowProps['onToggleTaken'];
  readonly onToggleSection: CourseRowProps['onToggleSection'];
  readonly otherVariants: CourseRowProps['otherVariants'];
  readonly onAddToVariant: CourseRowProps['onAddToVariant'];
}

/**
 * Renders the pane body for the current view, then the composer.
 */
export function Assistant(props: AssistantProps): React.JSX.Element {
  const { view, onView, search, messages } = props;
  const [filter, setFilter] = useState<SectionFilter>(NO_FILTER);
  const [sort, setSort] = useState<SortKey>('relevance');
  const [panelOpen, setPanelOpen] = useState(false);
  const { text, setText, parsed, courses, isSearching, hasMore, loadMore } = search;
  const activeIds = new Set(props.activeSections.map((s) => s.id));
  const filterCount = activeFilterCount(filter) + parsed.tokens.length;
  const results = sortCourses(
    courses.filter((c) => courseMatches(c, filter, props.activeSections)),
    sort,
  );

  const row = (course: Course): React.JSX.Element => (
    <CourseRow
      key={course.code}
      course={course}
      isSaved={props.watched.has(course.code)}
      completed={props.completed}
      activeSectionIds={activeIds}
      scheduledCourseIds={props.scheduledCourseIds}
      onToggleSave={props.onToggleSave}
      onToggleTaken={props.onToggleTaken}
      onToggleSection={props.onToggleSection}
      otherVariants={props.otherVariants}
      onAddToVariant={props.onAddToVariant}
    />
  );

  const sentinel = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const node = sentinel.current;
    if (view !== 'results' || !node || !hasMore) {
      return;
    }
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((e) => e.isIntersecting)) {
        loadMore();
      }
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, [view, hasMore, loadMore]);

  // Arrow keys walk every `data-nav` row; Right/Left expand and collapse.
  const body = useRef<HTMLDivElement>(null);
  const onBodyKey = (e: React.KeyboardEvent<HTMLDivElement>): void => {
    const target = e.target as HTMLElement;
    const course = target
      .closest('[data-course]')
      ?.querySelector<HTMLElement>('[data-nav="course"]');
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      const items = [...(body.current?.querySelectorAll<HTMLElement>('[data-nav]') ?? [])];
      const next = items[items.indexOf(target) + (e.key === 'ArrowDown' ? 1 : -1)];
      if (next) {
        e.preventDefault();
        next.focus();
        next.scrollIntoView({ block: 'nearest' });
      }
    } else if (e.key === 'ArrowRight' && course?.getAttribute('aria-expanded') === 'false') {
      e.preventDefault();
      course.click();
    } else if (e.key === 'ArrowLeft' && course?.getAttribute('aria-expanded') === 'true') {
      e.preventDefault();
      course.click();
      course.focus();
    }
  };

  return (
    <div className={styles.assistant}>
      {view === 'results' && (
        <div className={styles.resultsHead}>
          <div className={styles.chips}>
            <button type="button" className={styles.back} onClick={() => onView('chat')}>
              <ArrowLeft size={13} />
            </button>
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
        </div>
      )}

      <div className={styles.body} ref={body} onKeyDown={onBodyKey}>
        {view === 'results' ? (
          <>
            {results.map(row)}
            {results.length === 0 && !hasMore && !isSearching && (
              <p className={styles.empty}>
                {!text.trim()
                  ? 'Type a course, topic, or code below.'
                  : courses.length > 0
                    ? 'Nothing matches these filters.'
                    : 'No matching courses.'}
              </p>
            )}
            <div ref={sentinel} className={styles.sentinel} />
          </>
        ) : messages.length > 0 ? (
          <Thread
            messages={messages}
            onChip={props.onChip}
            onProject={props.onProject}
            onOpenCourse={props.onOpenCourseId}
            onNewChat={props.onNewChat}
          />
        ) : (
          <>
            <div className={styles.starters}>
              {STARTERS.map((s) => (
                <button key={s} type="button" className={styles.starter} onClick={() => props.onAsk(s)}>
                  {s}
                </button>
              ))}
            </div>
            {props.savedCourses.length > 0 && (
              <section>
                <h3 className={styles.heading}>Saved</h3>
                {props.savedCourses.map(row)}
              </section>
            )}
            {props.suggestions.length > 0 && (
              <section>
                <h3 className={styles.heading}>Next up</h3>
                {props.suggestions.map(row)}
              </section>
            )}
          </>
        )}
      </div>

      <Composer
        text={text}
        setText={setText}
        matches={courses}
        hasMoreMatches={hasMore}
        busy={props.busy}
        inputRef={props.inputRef}
        onOpen={props.onOpenCourse}
        onSeeAll={() => onView('results')}
        onAsk={props.onAsk}
        showTray={view !== 'results'}
      />
    </div>
  );
}
