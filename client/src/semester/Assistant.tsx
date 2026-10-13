/**
 * The column beside the week: everything that is not the week itself.
 *
 * One input sits at the bottom; what fills the column follows what the
 * student is doing, never a tab or mode they pick. At rest it is the feed:
 * saved courses, their degree, then the conversation (or prompts to start
 * one). Typing lays live course matches over the feed, and an open course
 * lays its card over both. Covered layers stay mounted and keep their
 * scroll, so closing a card or clearing the text returns exactly where the
 * student was. The degree and the card arrive as rendered slots; plan
 * edits, chat sending, and navigation belong to the caller.
 */

import React, { useEffect, useRef, useState } from 'react';
import { ArrowUp, CircleCheck, ListFilter, X } from 'lucide-react';
import type { CatalogSearch } from '../hooks/useCatalogSearch';
import { displayCode } from '../lib/degree';
import { NO_FILTER, activeFilterCount, courseMatches, sortCourses } from '../lib/filter';
import type { DayPart, SectionFilter, SortKey } from '../lib/filter';
import { takenCodes } from '../lib/query';
import type { Chip, ChatMessage, Course, Section } from '../types';
import { Composer } from './Composer';
import { CourseLine } from './Course';
import type { CoursePlan } from './Course';
import { FilterPanel } from './FilterPanel';
import { Thread } from './Thread';
import styles from './Assistant.module.css';

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

/** Shows a layer, or hides it in place so it keeps its scroll position. */
function layer(isShown: boolean): React.CSSProperties | undefined {
  return isShown ? undefined : { visibility: 'hidden' };
}

/**
 * Properties for the column.
 */
export interface AssistantProps {
  readonly search: CatalogSearch;
  readonly inputRef: React.RefObject<HTMLInputElement | null>;
  readonly messages: readonly ChatMessage[];
  readonly busy: boolean;
  readonly onAsk: (text: string) => void;
  /** Records courses as taken, given as identities. */
  readonly onTaken: (codes: readonly string[]) => void;
  readonly onChip: (chip: Chip) => void;
  readonly onProject: (chips: readonly Chip[]) => void;
  readonly onNewChat: () => void;
  /** Closes the topmost layer: the card, else the search text. */
  readonly onEscape: () => void;
  readonly onOpenCourse: (course: Course) => void;
  /** Opens a course named by code, as advisor replies name them. */
  readonly onOpenCode: (code: string) => void;
  /** The degree audit, shown in the feed. */
  readonly degree: React.ReactNode;
  /** The open course's card, or null. */
  readonly card: React.ReactNode;
  readonly savedCourses: readonly Course[];
  readonly activeSections: readonly Section[];
  readonly plan: CoursePlan;
}

/**
 * Renders the feed, the results and card layers over it, and the input.
 */
export function Assistant(props: AssistantProps): React.JSX.Element {
  const { search, messages, card } = props;
  const [filter, setFilter] = useState<SectionFilter>(NO_FILTER);
  const [sort, setSort] = useState<SortKey>('relevance');
  const [panelOpen, setPanelOpen] = useState(false);
  const { text, setText, parsed, courses, isSearching, hasMore, loadMore } = search;
  const typing = text.trim() !== '';
  const taken = takenCodes(text);
  const filterCount = activeFilterCount(filter) + parsed.tokens.length;
  const results = sortCourses(
    courses.filter((c) => courseMatches(c, filter, props.activeSections)),
    sort,
  );
  const line = (course: Course): React.JSX.Element => (
    <CourseLine
      key={course.code}
      course={course}
      plan={props.plan}
      onOpen={props.onOpenCourse}
    />
  );

  const resultsLayer = useRef<HTMLDivElement>(null);
  const sentinel = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const node = sentinel.current;
    if (!typing || !node || !hasMore) {
      return;
    }
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((e) => e.isIntersecting)) {
        loadMore();
      }
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, [typing, hasMore, loadMore]);

  // Arrow keys walk the results; Right opens the course under focus.
  const onResultsKey = (e: React.KeyboardEvent<HTMLDivElement>): void => {
    const target = e.target as HTMLElement;
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      const items = [
        ...(resultsLayer.current?.querySelectorAll<HTMLElement>('[data-nav]') ?? []),
      ];
      const next = items[items.indexOf(target) + (e.key === 'ArrowDown' ? 1 : -1)];
      e.preventDefault();
      (next ?? (e.key === 'ArrowDown' ? props.inputRef.current : undefined))?.focus();
      next?.scrollIntoView({ block: 'nearest' });
    } else if (e.key === 'ArrowRight' && target.dataset.nav === 'course') {
      e.preventDefault();
      target.click();
    }
  };

  return (
    <div className={styles.assistant}>
      <div className={styles.layers}>
        <div className={styles.layer} style={layer(!typing && !card)}>
          {props.savedCourses.length > 0 && (
            <section className={styles.saved}>
              <h3 className={styles.heading}>Saved</h3>
              {props.savedCourses.map(line)}
            </section>
          )}
          {props.degree}
          {messages.length > 0 ? (
            <Thread
              messages={messages}
              onChip={props.onChip}
              onProject={props.onProject}
              onOpenCourse={props.onOpenCode}
              onNewChat={props.onNewChat}
            />
          ) : (
            <div className={styles.starters}>
              {STARTERS.map((s) => (
                <button key={s} type="button" className={styles.starter} onClick={() => props.onAsk(s)}>
                  {s}
                </button>
              ))}
            </div>
          )}
        </div>

        {typing && (
          <div
            className={styles.layer}
            style={layer(!card)}
            ref={resultsLayer}
            onKeyDown={onResultsKey}
          >
            {!taken && (
              <div className={styles.resultsHead}>
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
              </div>
            )}
            {taken ? (
              <button
                type="button"
                data-nav="taken"
                className={styles.ask}
                onClick={() => props.onTaken(taken)}
              >
                <CircleCheck size={12} />
                Mark {taken.map(displayCode).join(', ')} taken
              </button>
            ) : (
              <button
                type="button"
                data-nav="ask"
                className={styles.ask}
                onClick={() => props.onAsk(text.trim())}
              >
                <ArrowUp size={12} />
                Ask “{text.trim()}”
              </button>
            )}
            {!taken && results.map(line)}
            {!taken && results.length === 0 && !hasMore && !isSearching && (
              <p className={styles.empty}>
                {courses.length > 0 ? 'Nothing matches these filters.' : 'No matching courses.'}
              </p>
            )}
            <div ref={sentinel} className={styles.sentinel} />
          </div>
        )}

        {card && <div className={styles.layer}>{card}</div>}
      </div>

      <Composer
        text={text}
        setText={setText}
        top={results[0] ?? null}
        busy={props.busy}
        inputRef={props.inputRef}
        onOpen={props.onOpenCourse}
        onAsk={props.onAsk}
        onTaken={props.onTaken}
        onEscape={props.onEscape}
        onArrowUp={() =>
          resultsLayer.current?.querySelector<HTMLElement>('[data-nav]')?.focus()
        }
      />
    </div>
  );
}
