/**
 * The advisor conversation inside the Assistant pane.
 *
 * Lays out the transcript: the student's messages, each reply (rendered by
 * `Reply`, which links the course codes it names), its follow-up chips, and
 * a note on any course the catalog lacks. Sending messages and chip effects
 * belong to the caller.
 */

import React, { useEffect, useRef } from 'react';
import { CalendarDays } from 'lucide-react';
import type { Chip, ChatMessage } from '../types';
import { Reply } from './Reply';
import type { CourseState } from './Reply';
import styles from './Thread.module.css';

/**
 * Properties for the conversation.
 */
export interface ThreadProps {
  readonly messages: readonly ChatMessage[];
  readonly onChip: (chip: Chip) => void;
  /** Projects a reply's proposed schedules onto the week again. */
  readonly onProject: (chips: readonly Chip[]) => void;
  /** Opens a course mentioned in a reply, given as "DEPT-123X". */
  readonly onOpenCourse: (courseId: string) => void;
  readonly onNewChat: () => void;
  readonly stateOf: (courseId: string) => CourseState;
}

/**
 * Renders the transcript, keeping the newest message in view.
 */
export function Thread(props: ThreadProps): React.JSX.Element {
  const { messages, onChip, onProject, onOpenCourse, onNewChat, stateOf } = props;
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
                stateOf={stateOf}
              />
            ) : (
              <span className={styles.thinking} aria-label="Thinking">
                <span />
                <span />
                <span />
              </span>
            )}
            {m.chips && <Chips chips={m.chips} onChip={onChip} onProject={onProject} />}
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

/**
 * A reply's follow-ups. Proposed schedules are already on the week, so they
 * collapse into one control that projects them again after a discard.
 */
function Chips({
  chips,
  onChip,
  onProject,
}: {
  readonly chips: readonly Chip[];
  readonly onChip: (chip: Chip) => void;
  readonly onProject: (chips: readonly Chip[]) => void;
}): React.JSX.Element | null {
  const schedules = chips.filter((c) => c.action === 'propose_schedule').length;
  // Recorded courses were applied when the reply ended; the toast offered undo.
  const others = chips.filter(
    (c) => c.action !== 'propose_schedule' && c.action !== 'mark_taken',
  );
  if (schedules === 0 && others.length === 0) {
    return null;
  }
  return (
    <div className={styles.chips}>
      {schedules > 0 && (
        <button type="button" className={styles.chip} onClick={() => onProject(chips)}>
          <CalendarDays size={12} />
          {schedules === 1 ? 'Schedule' : `${schedules} schedules`} on your week
        </button>
      )}
      {others.map((chip, i) => (
        <button key={i} type="button" className={styles.chip} onClick={() => onChip(chip)}>
          {chip.label}
        </button>
      ))}
    </div>
  );
}
