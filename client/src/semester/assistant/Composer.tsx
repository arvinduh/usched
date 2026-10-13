/**
 * The column's single input, in one of three modes set by its first
 * character, never guessed from the words.
 *
 * Plain text talks to the advisor. ">" finds courses, whose matches fill
 * the column above. "/" runs a command: "/took CSCI 103L, MATH 125"
 * records courses taken, "/new" starts a new chat, and "/degree" opens
 * degree progress. While a command is named, or a code typed after
 * "/took", a small list above the input offers completions. The input
 * states what Enter will do; routing lives here, and its effects belong to
 * the caller.
 */

import React, { useState } from 'react';
import { CornerDownLeft } from 'lucide-react';
import { courseKey, displayCode, extractCourseCodes } from '../../degree/_degree';
import type { Bar } from '../_search/_query';
import type { components } from '../../api/schema';
import styles from './Assistant.module.css';

/** Commands other than /took, which takes course codes. */
export type CommandName = 'new' | 'degree';

/** Every command, in the order a list of them shows. */
const COMMANDS: readonly { readonly name: 'took' | CommandName; readonly hint: string }[] =
  [
    { name: 'took', hint: 'Mark courses you have taken' },
    { name: 'new', hint: 'Start a new chat' },
    { name: 'degree', hint: 'Open degree progress' },
  ];

/** Course completions shown for a code after "/took". */
const MAX_SUGGESTIONS = 6;

/** One row of the completion list. */
interface Completion {
  readonly key: string;
  readonly label: string;
  readonly detail: string;
  /** Enter: runs a command, or adds a course. */
  readonly choose: () => void;
  /** Tab: completes the text without running anything. */
  readonly fill: () => void;
}

/**
 * Properties for the composer.
 */
export interface ComposerProps {
  readonly text: string;
  readonly setText: (text: string) => void;
  readonly bar: Bar;
  /** The best catalog match for a ">" search, if any. */
  readonly top: components['schemas']['Course'] | null;
  /** Catalog matches for the code being typed after "/took". */
  readonly suggestions: readonly components['schemas']['Course'][];
  /** True while the advisor is still replying; asking again waits. */
  readonly busy: boolean;
  readonly inputRef: React.RefObject<HTMLInputElement | null>;
  readonly onOpen: (course: components['schemas']['Course']) => void;
  readonly onAsk: (text: string) => void;
  /** Records courses as taken, given as identities. */
  readonly onTaken: (codes: readonly string[]) => void;
  readonly onCommand: (name: CommandName) => void;
  readonly onEscape: () => void;
  /** Moves focus up into the matches. */
  readonly onArrowUp: () => void;
}

/** What Enter does for the bar as it reads now, or null for nothing. */
function enterLabel(
  bar: Bar,
  top: components['schemas']['Course'] | null,
  busy: boolean,
): string | null {
  switch (bar.kind) {
    case 'chat':
      return bar.text ? (busy ? 'Replying…' : 'Ask') : null;
    case 'courses':
      return top ? `Open ${displayCode(top.code)}` : null;
    case 'took':
      return bar.codes.length > 0 ? `Mark ${bar.codes.length} taken` : null;
    case 'commands':
      return null;
  }
}

/**
 * Renders the input, its completions, and what Enter will do.
 */
export function Composer(props: ComposerProps): React.JSX.Element {
  const { text, setText, bar, top, busy, inputRef, onEscape, onArrowUp } = props;
  const [cursor, setCursor] = useState(0);

  const runCommand = (name: 'took' | CommandName): void => {
    if (name === 'took') {
      setText('/took ');
    } else {
      setText('');
      props.onCommand(name);
    }
  };
  // Swaps the code being typed for a chosen one, ready for the next.
  const complete = (code: string): void => {
    if (bar.kind === 'took') {
      setText(`${text.slice(0, text.lastIndexOf(bar.partial))}${displayCode(code)}, `);
      setCursor(0);
    }
  };

  const listed = new Set(bar.kind === 'took' ? bar.codes.map(courseKey) : []);
  const completions: readonly Completion[] =
    bar.kind === 'commands'
      ? COMMANDS.filter((c) => c.name.startsWith(bar.name)).map((c) => ({
          key: c.name,
          label: `/${c.name}`,
          detail: c.hint,
          choose: () => runCommand(c.name),
          fill: () => {
            setText(c.name === 'took' ? '/took ' : `/${c.name}`);
            setCursor(0);
          },
        }))
      : bar.kind === 'took' && bar.partial
        ? props.suggestions
            .filter((c) => !listed.has(courseKey(c.code)))
            .slice(0, MAX_SUGGESTIONS)
            .map((c) => ({
              key: c.code,
              label: displayCode(c.code),
              detail: c.title,
              choose: () => complete(c.code),
              fill: () => complete(c.code),
            }))
        : [];
  const active = completions[Math.min(cursor, completions.length - 1)];
  // Enter finishes an unfinished code; a whole code is already listed.
  const completing =
    active !== undefined &&
    (bar.kind === 'commands' ||
      (bar.kind === 'took' && extractCourseCodes(bar.partial).length === 0));

  const onEnter = (ask: boolean): void => {
    if (completing) {
      active.choose();
      return;
    }
    switch (bar.kind) {
      case 'chat':
        if (bar.text && !busy) {
          props.onAsk(bar.text);
        }
        return;
      case 'courses':
        if (ask && bar.query && !busy) {
          props.onAsk(bar.query);
        } else if (top) {
          props.onOpen(top);
        }
        return;
      case 'took':
        if (bar.codes.length > 0) {
          props.onTaken(bar.codes);
        }
        return;
      case 'commands':
        return;
    }
  };

  const onKey = (e: React.KeyboardEvent<HTMLInputElement>): void => {
    if (completions.length > 0 && (e.key === 'ArrowDown' || e.key === 'ArrowUp')) {
      e.preventDefault();
      const step = e.key === 'ArrowDown' ? 1 : -1;
      setCursor((Math.min(cursor, completions.length - 1) + step + completions.length) % completions.length);
    } else if (e.key === 'Tab' && active) {
      e.preventDefault();
      active.fill();
    } else if (e.key === 'Enter') {
      e.preventDefault();
      onEnter(e.metaKey || e.ctrlKey);
    } else if (e.key === 'ArrowUp' && bar.kind === 'courses' && bar.query) {
      e.preventDefault();
      onArrowUp();
    } else if (e.key === 'Escape') {
      e.stopPropagation();
      onEscape();
    }
  };

  const label = completing
    ? `${bar.kind === 'commands' ? 'Run' : 'Add'} ${active.label}`
    : enterLabel(bar, top, busy);
  return (
    <div className={styles.composer}>
      {completions.length > 0 && (
        <ul id="bar-completions" role="listbox" className={styles.completions}>
          {completions.map((c) => (
            <li
              key={c.key}
              id={`bar-${c.key}`}
              role="option"
              aria-selected={c === active}
              className={`${styles.completion} ${c === active ? styles.completionOn : ''}`}
              onMouseEnter={() => setCursor(completions.indexOf(c))}
              // Choose on mousedown, so the input keeps focus.
              onMouseDown={(e) => {
                e.preventDefault();
                c.choose();
              }}
            >
              <span className={styles.completionLabel}>{c.label}</span>
              <span className={styles.completionDetail}>{c.detail}</span>
            </li>
          ))}
        </ul>
      )}
      <div className={styles.inputWrap}>
        <input
          ref={inputRef}
          className={styles.input}
          value={text}
          role="combobox"
          aria-expanded={completions.length > 0}
          aria-controls="bar-completions"
          aria-activedescendant={active ? `bar-${active.key}` : undefined}
          onChange={(e) => {
            setText(e.target.value);
            setCursor(0);
          }}
          onKeyDown={onKey}
          placeholder="Ask anything"
          aria-label="Ask the advisor; start with > to find courses, / for commands"
          spellCheck={false}
        />
        <span className={styles.hint} aria-live="polite">
          {text ? (
            label && (
              <>
                <CornerDownLeft size={11} />
                {label}
              </>
            )
          ) : (
            <>
              <kbd className={styles.kbd}>&gt;</kbd> courses
              <kbd className={styles.kbd}>/</kbd> commands
            </>
          )}
        </span>
      </div>
    </div>
  );
}
