/**
 * The column's single input: ask the advisor or find a course.
 *
 * Matches appear in the column above as you type, so the input itself only
 * states what Enter will do: open the best match for course-like text, or
 * ask the advisor for questions. Cmd/Ctrl+Enter always asks. Routing
 * decisions live here; their effects belong to the caller.
 */

import React from 'react';
import { CornerDownLeft } from 'lucide-react';
import { displayCode } from '../lib/degree';
import { looksLikeQuestion } from '../lib/query';
import type { Course } from '../types';
import styles from './Assistant.module.css';

/**
 * Properties for the composer.
 */
export interface ComposerProps {
  readonly text: string;
  readonly setText: (text: string) => void;
  /** The best catalog match for `text`, if any. */
  readonly top: Course | null;
  /** True while the advisor is still replying; asking again waits. */
  readonly busy: boolean;
  readonly inputRef: React.RefObject<HTMLInputElement | null>;
  readonly onOpen: (course: Course) => void;
  readonly onAsk: (text: string) => void;
  readonly onEscape: () => void;
  /** Moves focus up into the matches. */
  readonly onArrowUp: () => void;
}

/**
 * Renders the input and its Enter hint.
 */
export function Composer(props: ComposerProps): React.JSX.Element {
  const { text, setText, top, busy, inputRef, onOpen, onAsk, onEscape, onArrowUp } = props;
  const query = text.trim();
  // A question asks; anything else opens the best match when there is one.
  const opens = query !== '' && !looksLikeQuestion(text) && top !== null;

  const onKey = (e: React.KeyboardEvent<HTMLInputElement>): void => {
    if (e.key === 'Enter') {
      e.preventDefault();
      if (opens && top && !(e.metaKey || e.ctrlKey)) {
        onOpen(top);
      } else if (query && !busy) {
        onAsk(query);
      }
    } else if (e.key === 'ArrowUp' && query) {
      e.preventDefault();
      onArrowUp();
    } else if (e.key === 'Escape') {
      e.stopPropagation();
      onEscape();
    }
  };

  return (
    <div className={styles.composer}>
      <div className={styles.inputWrap}>
        <input
          ref={inputRef}
          className={styles.input}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={onKey}
          placeholder="Ask anything, or type a course"
          aria-label="Ask the advisor or search courses"
          spellCheck={false}
        />
        <span className={styles.hint} aria-live="polite">
          {query ? (
            <>
              <CornerDownLeft size={11} />
              {opens && top ? `Open ${displayCode(top.code)}` : busy ? 'Replying…' : 'Ask'}
            </>
          ) : (
            <kbd className={styles.kbd}>/</kbd>
          )}
        </span>
      </div>
    </div>
  );
}
