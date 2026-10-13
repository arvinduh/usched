/**
 * The Library's compact filter panel.
 *
 * Section filters (days, time of day, seats, fit) are plain state owned by
 * the Library. GE and rating stay text tokens in the search box, so this
 * panel edits the text for those and the box remains the single source of
 * truth for what the server is asked.
 */

import React from 'react';
import type { DayPart, SectionFilter } from './_search/_filter';
import type { ParsedQuery } from './_search/_query';
import { WEEKDAYS } from './_schedule';
import styles from './assistant/Assistant.module.css';

const DAY_PARTS: readonly { readonly key: DayPart; readonly label: string }[] = [
  { key: 'morning', label: 'Morning' },
  { key: 'afternoon', label: 'Afternoon' },
  { key: 'evening', label: 'Evening' },
];
const GE_LETTERS = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H'] as const;
const RATINGS = ['3.5', '4', '4.5'] as const;

/**
 * Properties for the filter panel.
 */
export interface FilterPanelProps {
  readonly filter: SectionFilter;
  /** Applies an update to the latest filter, so rapid clicks compose. */
  readonly onFilter: (update: (current: SectionFilter) => SectionFilter) => void;
  readonly parsed: ParsedQuery;
  /** Replaces the search text; used to add or remove GE and rating tokens. */
  readonly text: string;
  readonly setText: (text: string) => void;
}

function toggled<T>(set: ReadonlySet<T>, value: T): ReadonlySet<T> {
  const next = new Set(set);
  if (!next.delete(value)) {
    next.add(value);
  }
  return next;
}

/**
 * Renders the filter rows.
 */
export function FilterPanel(props: FilterPanelProps): React.JSX.Element {
  const { filter, onFilter, parsed, text, setText } = props;

  // Swaps the token of one kind ("ge b", "4+") for `token`, or removes it
  // when `token` is null.
  const setToken = (kind: 'ge' | 'rating', token: string | null): void => {
    const existing = parsed.tokens.find((t) =>
      kind === 'ge' ? t.label.startsWith('GE-') : t.label.startsWith('★'),
    );
    const base = existing ? text.replace(existing.raw, ' ') : text;
    setText(`${base.replace(/\s+/g, ' ').trim()}${token ? ` ${token}` : ''}`.trim());
  };

  return (
    <div className={styles.panel}>
      <div className={styles.panelRow}>
        <span className={styles.panelLabel}>Days</span>
        {WEEKDAYS.map((day) => {
          const off = filter.excludedDays.has(day);
          return (
            <button
              key={day}
              type="button"
              className={`${styles.dayToggle} ${off ? styles.dayOff : ''}`}
              aria-pressed={!off}
              aria-label={`${off ? 'Allow' : 'Exclude'} ${day}`}
              onClick={() =>
                onFilter((f) => ({ ...f, excludedDays: toggled(f.excludedDays, day) }))
              }
            >
              {day.slice(0, 2)}
            </button>
          );
        })}
      </div>

      <div className={styles.panelRow}>
        <span className={styles.panelLabel}>Time</span>
        {DAY_PARTS.map(({ key, label }) => (
          <button
            key={key}
            type="button"
            className={`${styles.chip} ${filter.dayParts.has(key) ? styles.chipOn : ''}`}
            aria-pressed={filter.dayParts.has(key)}
            onClick={() => onFilter((f) => ({ ...f, dayParts: toggled(f.dayParts, key) }))}
          >
            {label}
          </button>
        ))}
      </div>

      <div className={styles.panelRow}>
        <span className={styles.panelLabel}>GE</span>
        {GE_LETTERS.map((letter) => {
          const on = parsed.ge === `GE-${letter}`;
          return (
            <button
              key={letter}
              type="button"
              className={`${styles.geToggle} ${on ? styles.chipOn : ''}`}
              aria-pressed={on}
              onClick={() => setToken('ge', on ? null : `ge ${letter.toLowerCase()}`)}
            >
              {letter}
            </button>
          );
        })}
      </div>

      <div className={styles.panelRow}>
        <span className={styles.panelLabel}>Rating</span>
        {RATINGS.map((r) => {
          const on = parsed.minRmp === Number(r);
          return (
            <button
              key={r}
              type="button"
              className={`${styles.chip} ${on ? styles.chipOn : ''}`}
              aria-pressed={on}
              onClick={() => setToken('rating', on ? null : `${r}+`)}
            >
              ★ {r}+
            </button>
          );
        })}
      </div>

      <div className={styles.panelRow}>
        <span className={styles.panelLabel} />
        <button
          type="button"
          className={`${styles.chip} ${filter.openSeatsOnly ? styles.chipOn : ''}`}
          aria-pressed={filter.openSeatsOnly}
          onClick={() => onFilter((f) => ({ ...f, openSeatsOnly: !f.openSeatsOnly }))}
        >
          Open seats
        </button>
        <button
          type="button"
          className={`${styles.chip} ${filter.fitsWeekOnly ? styles.chipOn : ''}`}
          aria-pressed={filter.fitsWeekOnly}
          onClick={() => onFilter((f) => ({ ...f, fitsWeekOnly: !f.fitsWeekOnly }))}
        >
          Fits my week
        </button>
      </div>
    </div>
  );
}
