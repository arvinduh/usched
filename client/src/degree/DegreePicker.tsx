/**
 * The Degree space's title, which is also its program picker.
 *
 * At rest it reads as a heading: program name, emphasis, and a type chip
 * (BS, BA, Minor). Clicking turns it into `ProgramSearch`, a combobox that
 * matches degrees and minors as you type, which the first-run welcome also
 * uses. Selection is delegated to the caller.
 */

import React, { useMemo, useState } from 'react';
import { ChevronDown } from 'lucide-react';
import type { ProgramSummary } from '../types';
import styles from './Degree.module.css';

const MAX_RESULTS = 8;

/**
 * Properties for the degree picker.
 */
export interface DegreePickerProps {
  /** Degrees and minors; other program kinds are not offered here. */
  readonly programs: readonly ProgramSummary[];
  readonly selectedId: string;
  readonly onSelect: (programId: string) => void;
}

/** The chip text for a program: its degree type, or Minor. */
function typeOf(p: ProgramSummary): string {
  return p.degree_type ?? (p.kind === 'minor' ? 'Minor' : '');
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
 * Describes a program beyond its name: its emphasis, plus its school when
 * another program shares its title.
 */
function useProgramDetail(
  programs: readonly ProgramSummary[],
): (p: ProgramSummary) => string {
  const sharedTitles = useMemo(() => {
    const seen = new Set<string>();
    const shared = new Set<string>();
    for (const p of programs) {
      (seen.has(p.title) ? shared : seen).add(p.title);
    }
    return shared;
  }, [programs]);
  return (p) =>
    [p.emphasis, sharedTitles.has(p.title) ? p.school : '']
      .filter(Boolean)
      .join(' · ');
}

/**
 * Properties for the program combobox.
 */
export interface ProgramSearchProps {
  readonly programs: readonly ProgramSummary[];
  readonly onChoose: (programId: string) => void;
  /** Leaving the input (blur or Escape); omit to keep it open. */
  readonly onCancel?: () => void;
}

/**
 * Renders an input that matches degrees and minors as you type.
 */
export function ProgramSearch(props: ProgramSearchProps): React.JSX.Element {
  const { programs, onChoose, onCancel } = props;
  const [query, setQuery] = useState('');
  const [cursor, setCursor] = useState(0);
  const detailOf = useProgramDetail(programs);

  const matches = useMemo(() => {
    const words = query.toLowerCase().split(/\s+/).filter(Boolean);
    return programs
      .map((p) => ({ program: p, rank: score(p.title, words) }))
      .filter(
        (m): m is { program: ProgramSummary; rank: number } => m.rank !== null,
      )
      .sort(
        (a, b) =>
          a.rank - b.rank || a.program.title.localeCompare(b.program.title),
      )
      .slice(0, MAX_RESULTS)
      .map((m) => m.program);
  }, [programs, query]);

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
        onBlur={onCancel}
        onKeyDown={(e) => {
          if (e.key === 'ArrowDown') {
            e.preventDefault();
            setCursor((c) => Math.min(c + 1, matches.length - 1));
          } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            setCursor((c) => Math.max(c - 1, 0));
          } else if (e.key === 'Enter' && matches[cursor]) {
            onChoose(matches[cursor].id);
          } else if (e.key === 'Escape' && onCancel) {
            e.stopPropagation();
            onCancel();
          }
        }}
      />
      <ul id="degree-options" role="listbox" className={styles.options}>
        {matches.map((d, i) => {
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
                onChoose(d.id);
              }}
            >
              <span className={styles.optionText}>
                <span>{d.name}</span>
                {detail && <span className={styles.optionEmphasis}>{detail}</span>}
              </span>
              <TypeChip type={typeOf(d)} />
            </li>
          );
        })}
        {matches.length === 0 && <li className={styles.optionEmpty}>No programs match.</li>}
      </ul>
    </div>
  );
}

/**
 * Renders the title, or the open combobox while choosing.
 */
export function DegreePicker(props: DegreePickerProps): React.JSX.Element {
  const { programs, selectedId, onSelect } = props;
  const [open, setOpen] = useState(false);
  const detailOf = useProgramDetail(programs);
  const selected = programs.find((p) => p.id === selectedId);

  if (open) {
    return (
      <ProgramSearch
        programs={programs}
        onChoose={(id) => {
          onSelect(id);
          setOpen(false);
        }}
        onCancel={() => setOpen(false)}
      />
    );
  }
  return (
    <button
      type="button"
      className={styles.picker}
      onClick={() => setOpen(true)}
      aria-haspopup="listbox"
    >
      <span className={styles.degreeName}>
        {selected?.name ?? 'Choose a program'}
      </span>
      {selected && <TypeChip type={typeOf(selected)} />}
      <ChevronDown size={16} className={styles.pickerCaret} />
      {selected && detailOf(selected) && (
        <span className={styles.emphasis}>{detailOf(selected)}</span>
      )}
    </button>
  );
}
