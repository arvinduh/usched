/**
 * The advisor conversation inside the Assistant pane.
 *
 * Lays out the transcript: the student's messages, each reply (rendered by
 * `Reply`, which links the course codes it names), its follow-up chips, and
 * a note on any course the catalog lacks. Sending messages and chip effects
 * belong to the caller.
 */

import React, { useEffect, useRef } from 'react';
import type { Chip, ChatMessage } from '../types';
import { Reply } from './Reply';
import styles from './Thread.module.css';

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
              <Reply
                text={m.content}
                unverified={new Set(m.unverified)}
                onOpenCourse={onOpenCourse}
              />
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
                {m.unverified.join(', ')}{' '}
                {m.unverified.length === 1 ? "isn't" : "aren't"} in USC's catalog;
                the advisor may have {m.unverified.length === 1 ? 'it' : 'them'} wrong.
              </p>
            )}
          </div>
        ),
      )}
      <div ref={end} />
    </div>
  );
}
