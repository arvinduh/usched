/**
 * The column's single input, in one of three modes set by its first
 * character, never guessed from the words.
 *
 * Plain text talks to the advisor. ">" finds courses, whose matches fill
 * the column above. "/" runs a command: "/took CSCI 103L, MATH 125"
 * records courses taken, "/new" starts a new chat, and "/degree" opens
 * degree progress. The input states what Enter will do; routing lives
 * here, and its effects belong to the caller.
 */

import React from 'react';
import { CornerDownLeft } from 'lucide-react';
import { displayCode } from '../lib/degree';
import type { Bar } from '../lib/query';
import type { Course } from '../types';
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

/**
 * Properties for the composer.
 */
export interface ComposerProps {
  readonly text: string;
  readonly setText: (text: string) => void;
  readonly bar: Bar;
  /** The best catalog match for a ">" search, if any. */
  readonly top: Course | null;
  /** True while the advisor is still replying; asking again waits. */
  readonly busy: boolean;
  readonly inputRef: React.RefObject<HTMLInputElement | null>;
  readonly onOpen: (course: Course) => void;
  readonly onAsk: (text: string) => void;
  /** Records courses as taken, given as identities. */
  readonly onTaken: (codes: readonly string[]) => void;
  readonly onCommand: (name: CommandName) => void;
  readonly onEscape: () => void;
  /** Moves focus up into the matches. */
  readonly onArrowUp: () => void;
}

/** What Enter does for the bar as it reads now, or null for nothing. */
function enterLabel(bar: Bar, top: Course | null, busy: boolean): string | null {
  switch (bar.kind) {
    case 'chat':
      return bar.text ? (busy ? 'Replying…' : 'Ask') : null;
    case 'courses':
      return top ? `Open ${displayCode(top.code)}` : null;
    case 'took':
      return bar.codes.length > 0 ? `Mark ${bar.codes.length} taken` : null;
    case 'commands':
      return COMMANDS.some((c) => c.name === bar.name) ? `Run /${bar.name}` : null;
  }
}

/**
 * Renders the input and what Enter will do.
 */
export function Composer(props: ComposerProps): React.JSX.Element {
  const { text, setText, bar, top, busy, inputRef, onEscape, onArrowUp } = props;

  const onEnter = (ask: boolean): void => {
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
        if (bar.name === 'took') {
          setText('/took ');
        } else if (bar.name === 'new' || bar.name === 'degree') {
          setText('');
          props.onCommand(bar.name);
        }
        return;
    }
  };

  const onKey = (e: React.KeyboardEvent<HTMLInputElement>): void => {
    if (e.key === 'Enter') {
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

  const label = enterLabel(bar, top, busy);
  return (
    <div className={styles.composer}>
      <div className={styles.inputWrap}>
        <input
          ref={inputRef}
          className={styles.input}
          value={text}
          onChange={(e) => setText(e.target.value)}
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
