/**
 * The Assistant pane's single input: ask the advisor or find a course.
 *
 * As you type, catalog matches appear in a tray just above the input, and
 * the input states what Enter will do: open the best course match for short
 * course-like text, or ask the advisor for questions. Cmd/Ctrl+Enter always
 * asks. Routing decisions live here; their effects belong to the caller.
 */

import React from 'react';
import { ArrowUp, CornerDownLeft } from 'lucide-react';
import { displayCode } from '../lib/degree';
import { looksLikeQuestion } from '../lib/query';
import type { Course } from '../types';
import styles from './Assistant.module.css';

/** Matches shown in the tray; the full list lives one click away. */
const TRAY_SIZE = 4;

/**
 * Properties for the composer.
 */
export interface ComposerProps {
  readonly text: string;
  readonly setText: (text: string) => void;
  /** Current catalog matches for `text`, best first. */
  readonly matches: readonly Course[];
  readonly hasMoreMatches: boolean;
  /** True while the advisor is still replying; asking again waits. */
  readonly busy: boolean;
  readonly inputRef: React.RefObject<HTMLInputElement | null>;
  readonly onOpen: (course: Course) => void;
  readonly onSeeAll: () => void;
  readonly onAsk: (text: string) => void;
  /** Hidden while the full results already fill the pane. */
  readonly showTray: boolean;
}

/**
 * Renders the tray and the input.
 */
export function Composer(props: ComposerProps): React.JSX.Element {
  const { text, setText, matches, hasMoreMatches, busy, inputRef, onOpen, onSeeAll, onAsk } =
    props;
  const showTray = props.showTray;
  const query = text.trim();
  const top = matches.slice(0, TRAY_SIZE);
  // A question asks; anything else opens the best match when there is one.
  const opens = query !== '' && !looksLikeQuestion(text) && top.length > 0;

  const ask = (): void => {
    if (query && !busy) {
      onAsk(query);
    }
  };

  // The tray sits above the input, so Up enters it and Down walks back.
  const trayItems = (from: HTMLElement): HTMLElement[] =>
    [...(from.closest('[data-composer]')?.querySelectorAll<HTMLElement>('[data-tray]') ?? [])];

  const onInputKey = (e: React.KeyboardEvent<HTMLInputElement>): void => {
    if (e.key === 'Enter') {
      e.preventDefault();
      if (opens && !(e.metaKey || e.ctrlKey)) {
        onOpen(top[0]);
      } else {
        ask();
      }
    } else if (e.key === 'ArrowUp') {
      const items = trayItems(e.currentTarget);
      if (items.length > 0) {
        e.preventDefault();
        items[items.length - 1].focus();
      }
    } else if (e.key === 'Escape' && text) {
      e.stopPropagation();
      setText('');
    }
  };

  const onTrayKey = (e: React.KeyboardEvent<HTMLDivElement>): void => {
    if (e.key !== 'ArrowUp' && e.key !== 'ArrowDown') {
      return;
    }
    e.preventDefault();
    const items = trayItems(e.target as HTMLElement);
    const index = items.indexOf(e.target as HTMLElement);
    const next = items[index + (e.key === 'ArrowDown' ? 1 : -1)];
    (next ?? (e.key === 'ArrowDown' ? inputRef.current : undefined))?.focus();
  };

  return (
    <div className={styles.composer} data-composer>
      {query && showTray && (
        <div className={styles.tray} onKeyDown={onTrayKey} role="listbox">
          {top.map((course) => (
            <button
              key={course.id}
              type="button"
              data-tray
              className={styles.trayRow}
              onClick={() => onOpen(course)}
            >
              <span className={styles.trayCode}>{displayCode(course.id)}</span>
              <span className={styles.trayTitle}>{course.title}</span>
            </button>
          ))}
          {top.length > 0 && (matches.length > TRAY_SIZE || hasMoreMatches) && (
            <button type="button" data-tray className={styles.trayMore} onClick={onSeeAll}>
              See all results
            </button>
          )}
          <button type="button" data-tray className={styles.trayAsk} onClick={ask}>
            <ArrowUp size={12} />
            Ask “{query}”
          </button>
        </div>
      )}

      <div className={styles.inputWrap}>
        <input
          ref={inputRef}
          className={styles.input}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={onInputKey}
          placeholder="Ask anything, or type a course"
          aria-label="Ask the advisor or search courses"
          spellCheck={false}
        />
        <span className={styles.hint} aria-live="polite">
          {query ? (
            <>
              <CornerDownLeft size={11} />
              {opens ? `Open ${displayCode(top[0].id)}` : busy ? 'Replying…' : 'Ask'}
            </>
          ) : (
            <kbd className={styles.kbd}>/</kbd>
          )}
        </span>
      </div>
    </div>
  );
}
