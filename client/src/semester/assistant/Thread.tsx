/**
 * The advisor conversation inside the Assistant pane.
 *
 * Lays out the transcript: the student's messages, each reply (rendered by
 * `Reply`, which links the course codes it names), its follow-up chips, and
 * a note on any course the catalog lacks. Sending messages and chip effects
 * belong to the caller.
 */

import React, { useEffect, useRef } from 'react';
import { CalendarDays, Check } from 'lucide-react';
import { setFocus } from '../../state/preview';
import type { components } from '../../api/schema';
import type { ChatMessage } from './_useAdvisorChat';
import { Reply } from './Reply';
import type { CourseState } from './Reply';
import styles from './Thread.module.css';

/**
 * Properties for the conversation.
 */
export interface ThreadProps {
  readonly messages: readonly ChatMessage[];
  readonly onChip: (chip: components['schemas']['ClosingEvent']['action_chips'][number]) => void;
  /** Projects a reply's proposed schedules onto the week again. */
  readonly onProject: (chips: readonly components['schemas']['ClosingEvent']['action_chips'][number][]) => void;
  /** Opens a course mentioned in a reply, given as "DEPT-123X". */
  readonly onOpenCourse: (courseId: string) => void;
  readonly onNewChat: () => void;
  readonly stateOf: (courseId: string) => CourseState;
  /** True while the last reply is still streaming. */
  readonly busy: boolean;
}

/**
 * Renders the transcript, keeping the newest message in view.
 */
export function Thread(props: ThreadProps): React.JSX.Element {
  const { messages, onChip, onProject, onOpenCourse, onNewChat, stateOf, busy } = props;
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
            {(m.steps?.length || m.thinking) && (
              <Work
                steps={m.steps ?? []}
                thinking={m.thinking ?? ''}
                live={busy && i === messages.length - 1}
                reply={(text) => (
                  <Reply
                    text={text}
                    unverified={new Set()}
                    onOpenCourse={onOpenCourse}
                    stateOf={stateOf}
                  />
                )}
              />
            )}
            {m.content ? (
              <Reply
                text={m.content}
                unverified={new Set(m.unverified)}
                onOpenCourse={onOpenCourse}
                stateOf={stateOf}
              />
            ) : m.steps?.length || m.thinking ? null : (
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
  readonly chips: readonly components['schemas']['ClosingEvent']['action_chips'][number][];
  readonly onChip: (chip: components['schemas']['ClosingEvent']['action_chips'][number]) => void;
  readonly onProject: (chips: readonly components['schemas']['ClosingEvent']['action_chips'][number][]) => void;
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
      {others.map((chip, i) => {
        const sectionId = chip.action === 'enroll_section' ? chip.section_id : null;
        return (
          <button
            key={i}
            type="button"
            className={styles.chip}
            onClick={() => onChip(chip)}
            onMouseEnter={sectionId ? () => setFocus(sectionId) : undefined}
            onMouseLeave={sectionId ? () => setFocus(null) : undefined}
          >
            {chip.label}
          </button>
        );
      })}
    </div>
  );
}

/**
 * What the advisor did for a reply: while it works, the step under way;
 * after, a quiet summary that opens to every step and its reasoning.
 */
function Work({
  steps,
  thinking,
  live,
  reply,
}: {
  readonly steps: readonly string[];
  readonly thinking: string;
  readonly live: boolean;
  /** Renders the reasoning the way replies render. */
  readonly reply: (text: string) => React.ReactNode;
}): React.JSX.Element {
  const counted = steps.length === 1 ? '1 step' : `${steps.length} steps`;
  const summary = live
    ? `${steps.at(-1) ?? 'Thinking'}…`
    : [thinking && 'Thought', steps.length > 0 && counted].filter(Boolean).join(' · ');
  return (
    <details className={styles.work}>
      <summary className={`${styles.workSummary} ${live ? styles.live : ''}`}>
        {summary}
      </summary>
      {steps.length > 0 && (
        <ol className={styles.steps}>
          {steps.map((step, i) => (
            <li key={i}>
              <Check size={11} aria-hidden />
              {step}
            </li>
          ))}
        </ol>
      )}
      {thinking && <div className={styles.thought}>{reply(thinking)}</div>}
    </details>
  );
}
