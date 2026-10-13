/**
 * The Degree space's title, which is also its program picker.
 *
 * At rest it reads as a heading: program name, emphasis, and a type chip
 * (BS, BA, Minor). Clicking turns it into `ProgramSearch`, a combobox that
 * matches degrees and minors as you type, abbreviations included, which the
 * first-run welcome also uses. Selection is delegated to the caller.
 */

import React, { useDeferredValue, useMemo, useRef, useState } from 'react';
import { ChevronDown } from 'lucide-react';
import type { ProgramSummary } from '../types';
import { indexPrograms, rankPrograms } from './match';
import styles from './Degree.module.css';

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
  const list = useRef<HTMLUListElement>(null);
  const detailOf = useProgramDetail(programs);

  const index = useMemo(() => indexPrograms(programs), [programs]);
  // Typing stays immediate; re-ranking every program follows a beat behind.
  const deferredQuery = useDeferredValue(query);
  const matches = useMemo(() => rankPrograms(index, deferredQuery), [index, deferredQuery]);

  const moveTo = (i: number): void => {
    setCursor(i);
    list.current?.children[i]?.scrollIntoView({ block: 'nearest' });
  };

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
          list.current?.scrollTo({ top: 0 });
        }}
        onBlur={onCancel}
        onKeyDown={(e) => {
          if (e.key === 'ArrowDown') {
            e.preventDefault();
            moveTo(Math.min(cursor + 1, matches.length - 1));
          } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            moveTo(Math.max(cursor - 1, 0));
          } else if (e.key === 'Enter' && matches[cursor]) {
            onChoose(matches[cursor].id);
          } else if (e.key === 'Escape' && onCancel) {
            e.stopPropagation();
            onCancel();
          }
        }}
      />
      <ul ref={list} id="degree-options" role="listbox" className={styles.options}>
        {matches.map((d, i) => (
          <ProgramOption
            key={d.id}
            program={d}
            detail={detailOf(d)}
            position={i}
            isActive={i === cursor}
            onHover={setCursor}
            onChoose={onChoose}
          />
        ))}
        {matches.length === 0 && <li className={styles.optionEmpty}>No programs match.</li>}
      </ul>
    </div>
  );
}

/**
 * Properties for one program in the combobox's list.
 */
interface ProgramOptionProps {
  readonly program: ProgramSummary;
  readonly detail: string;
  readonly position: number;
  readonly isActive: boolean;
  readonly onHover: (position: number) => void;
  readonly onChoose: (programId: string) => void;
}

/**
 * Renders one choice. Its own component, so moving the cursor re-renders
 * the two rows it leaves and enters rather than every program.
 */
function ProgramOption(props: ProgramOptionProps): React.JSX.Element {
  const { program, detail, position, isActive, onHover, onChoose } = props;
  return (
    <li
      id={`degree-${program.id}`}
      role="option"
      aria-selected={isActive}
      className={`${styles.option} ${isActive ? styles.optionOn : ''}`}
      onMouseEnter={() => onHover(position)}
      // Choose on mousedown so the input's blur doesn't close first.
      onMouseDown={(e) => {
        e.preventDefault();
        onChoose(program.id);
      }}
    >
      <span className={styles.optionText}>
        <span>{program.name}</span>
        {detail && <span className={styles.optionEmphasis}>{detail}</span>}
      </span>
      <TypeChip type={typeOf(program)} />
    </li>
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
