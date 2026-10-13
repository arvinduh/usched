/**
 * The advisor conversation inside the Assistant pane.
 *
 * Renders replies as plain text (bold, line breaks, and "- " bullets) and
 * turns any course code the advisor mentions into a link that opens that
 * course, so an answer is always one click from the week. Sending messages
 * and chip effects belong to the caller.
 */

import React, { useEffect, useRef } from 'react';
import type { Chip, ChatMessage } from '../types';
import styles from './Thread.module.css';

/** Course codes as the advisor writes them: "CSCI-104L" or "CSCI 104L". */
const CODE = /\b([A-Z]{2,5})[- ](\d{3}[A-Za-z]{0,2})\b/g;

/**
 * Properties for the conversation.
 */
export interface ThreadProps {
  readonly messages: readonly ChatMessage[];
  readonly onChip: (chip: Chip) => void;
  /** Opens a course mentioned in a reply, given as "DEPT-123X". */
  readonly onOpenCourse: (courseId: string) => void;
  readonly onNewChat: () => void;
}

function linkCodes(
  text: string,
  onOpen: (courseId: string) => void,
): React.ReactNode[] {
  const parts: React.ReactNode[] = [];
  let last = 0;
  for (const m of text.matchAll(CODE)) {
    const at = m.index ?? 0;
    parts.push(text.slice(last, at));
    const id = `${m[1]}-${m[2]}`;
    parts.push(
      <button
        key={`${id}-${at}`}
        type="button"
        className={styles.code}
        onClick={() => onOpen(id)}
      >
        {m[0]}
      </button>,
    );
    last = at + m[0].length;
  }
  parts.push(text.slice(last));
  return parts;
}

function renderLine(line: string, onOpen: (courseId: string) => void): React.ReactNode {
  return line.split(/(\*\*.*?\*\*)/g).map((part, i) =>
    part.startsWith('**') && part.endsWith('**') ? (
      <strong key={i}>{linkCodes(part.slice(2, -2), onOpen)}</strong>
    ) : (
      <React.Fragment key={i}>{linkCodes(part, onOpen)}</React.Fragment>
    ),
  );
}

/**
 * Renders the transcript, keeping the newest message in view.
 */
export function Thread(props: ThreadProps): React.JSX.Element {
  const { messages, onChip, onOpenCourse, onNewChat } = props;
  const end = useRef<HTMLDivElement>(null);

  useEffect(() => {
    end.current?.scrollIntoView({ block: 'end' });
  }, [messages]);

  return (
    <div className={styles.thread}>
      <button type="button" className={styles.newChat} onClick={onNewChat}>
        New chat
      </button>
      {messages.map((m, i) =>
        m.role === 'user' ? (
          <p key={i} className={styles.user}>
            {m.content}
          </p>
        ) : (
          <div key={i} className={styles.reply}>
            {m.content ? (
              m.content.split('\n').map((line, j) => (
                <p key={j}>{renderLine(line.replace(/^\s*[*-]\s+/, '• '), onOpenCourse)}</p>
              ))
            ) : (
              <span className={styles.thinking} aria-label="Thinking">
                <span />
                <span />
                <span />
              </span>
            )}
            {m.chips && m.chips.length > 0 && (
              <div className={styles.chips}>
                {m.chips.map((chip, j) => (
                  <button
                    key={j}
                    type="button"
                    className={styles.chip}
                    onClick={() => onChip(chip)}
                  >
                    {chip.label}
                  </button>
                ))}
              </div>
            )}
            {m.unverified && m.unverified.length > 0 && (
              <p className={styles.unverified}>
                Couldn't verify {m.unverified.join(', ')}; check before relying
                on {m.unverified.length === 1 ? 'it' : 'them'}.
              </p>
            )}
          </div>
        ),
      )}
      <div ref={end} />
    </div>
  );
}
