/**
 * The Degree space's title, which is also its program picker.
 *
 * At rest it reads as a heading: program name, emphasis, and a degree-type
 * chip. Clicking turns it into a combobox that fuzzy-matches all programs as
 * you type. Selection is delegated to the caller.
 */

import React, { useMemo, useState } from 'react';
import { ChevronDown } from 'lucide-react';
import { parseDegreeTitle } from '../lib/degree';
import type { DegreeProgram } from '../types';
import styles from './Degree.module.css';

const MAX_RESULTS = 8;

/**
 * Properties for the degree picker.
 */
export interface DegreePickerProps {
  readonly degrees: readonly DegreeProgram[];
  readonly selectedId: string;
  readonly onSelect: (degreeId: string) => void;
}

/**
 * Renders a degree-type chip ("BS", "BA") in that type's quiet color.
 */
export function TypeChip({ type }: { readonly type: string }): React.JSX.Element | null {
  if (!type) {
    return null;
  }
  return (
    <span className={styles.typeChip} data-type={type}>
      {type}
    </span>
  );
}

/**
 * Scores a title against the query: every query word must prefix some title
 * word. Lower is better; null means no match.
 */
function score(title: string, words: readonly string[]): number | null {
  const titleWords = title.toLowerCase().split(/[\s(),/-]+/).filter(Boolean);
  let total = 0;
  for (const word of words) {
    const at = titleWords.findIndex((t) => t.startsWith(word));
    if (at === -1) {
      return null;
    }
    total += at;
  }
  return total;
}

/**
 * Renders the title, or the open combobox while choosing.
 */
export function DegreePicker(props: DegreePickerProps): React.JSX.Element {
  const { degrees, selectedId, onSelect } = props;
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [cursor, setCursor] = useState(0);

  const selected = degrees.find((d) => d.id === selectedId);
  const title = parseDegreeTitle(selected?.title ?? '');

  // Programs sharing a title are told apart by school.
  const sharedTitles = useMemo(() => {
    const seen = new Set<string>();
    const shared = new Set<string>();
    for (const d of degrees) {
      (seen.has(d.title) ? shared : seen).add(d.title);
    }
    return shared;
  }, [degrees]);

  const matches = useMemo(() => {
    const words = query.toLowerCase().split(/\s+/).filter(Boolean);
    return degrees
      .map((d) => ({ degree: d, rank: score(d.title, words) }))
      .filter((m): m is { degree: DegreeProgram; rank: number } => m.rank !== null)
      .sort((a, b) => a.rank - b.rank || a.degree.title.localeCompare(b.degree.title))
      .slice(0, MAX_RESULTS)
      .map((m) => m.degree);
  }, [degrees, query]);

  const detailOf = (degree: DegreeProgram): string => {
    const t = parseDegreeTitle(degree.title);
    return [t.emphasis, sharedTitles.has(degree.title) ? degree.school : '']
      .filter(Boolean)
      .join(' · ');
  };

  const choose = (degree: DegreeProgram): void => {
    onSelect(degree.id);
    setOpen(false);
  };

  if (!open) {
    return (
      <button
        type="button"
        className={styles.picker}
        onClick={() => {
          setQuery('');
          setCursor(0);
          setOpen(true);
        }}
        aria-haspopup="listbox"
      >
        <span className={styles.degreeName}>{title.name || 'Choose a program'}</span>
        <TypeChip type={title.type} />
        <ChevronDown size={16} className={styles.pickerCaret} />
        {selected && detailOf(selected) && (
          <span className={styles.emphasis}>{detailOf(selected)}</span>
        )}
      </button>
    );
  }

  return (
    <div className={styles.combo}>
      <input
        autoFocus
        className={styles.comboInput}
        value={query}
        placeholder="Type a program, like computer science"
        role="combobox"
        aria-expanded
        aria-controls="degree-options"
        aria-activedescendant={matches[cursor] ? `degree-${matches[cursor].id}` : undefined}
        onChange={(e) => {
          setQuery(e.target.value);
          setCursor(0);
        }}
        onBlur={() => setOpen(false)}
        onKeyDown={(e) => {
          if (e.key === 'ArrowDown') {
            e.preventDefault();
            setCursor((c) => Math.min(c + 1, matches.length - 1));
          } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            setCursor((c) => Math.max(c - 1, 0));
          } else if (e.key === 'Enter' && matches[cursor]) {
            choose(matches[cursor]);
          } else if (e.key === 'Escape') {
            e.stopPropagation();
            setOpen(false);
          }
        }}
      />
      <ul id="degree-options" role="listbox" className={styles.options}>
        {matches.map((d, i) => {
          const t = parseDegreeTitle(d.title);
          const detail = detailOf(d);
          return (
            <li
              key={d.id}
              id={`degree-${d.id}`}
              role="option"
              aria-selected={i === cursor}
              className={`${styles.option} ${i === cursor ? styles.optionOn : ''}`}
              onMouseEnter={() => setCursor(i)}
              // Choose on mousedown so the input's blur doesn't close first.
              onMouseDown={(e) => {
                e.preventDefault();
                choose(d);
              }}
            >
              <span className={styles.optionText}>
                <span>{t.name}</span>
                {detail && <span className={styles.optionEmphasis}>{detail}</span>}
              </span>
              <TypeChip type={t.type} />
            </li>
          );
        })}
        {matches.length === 0 && <li className={styles.optionEmpty}>No programs match.</li>}
      </ul>
    </div>
  );
}
