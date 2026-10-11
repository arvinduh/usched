/**
 * The advisor conversation, shown in the Library's place.
 *
 * Renders replies as plain text (bold and line breaks only) with action
 * chips, plus a follow-up input. The conversation itself lives in
 * `useAdvisorChat`; chip effects are the caller's.
 */

import React, { useEffect, useRef, useState } from 'react';
import { ArrowLeft, ArrowUp } from 'lucide-react';
import type { ActionChip, ChatMessage } from '../types';
import styles from './AskPane.module.css';

const SUGGESTIONS = [
  'What should I take next semester?',
  'Find an easy GE that fits my week',
  'Am I on track to graduate?',
] as const;

/**
 * Properties for the advisor pane.
 */
export interface AskPaneProps {
  readonly messages: readonly ChatMessage[];
  readonly isLoading: boolean;
  readonly onSend: (text: string) => void;
  readonly onChip: (chip: ActionChip) => void;
  readonly onBack: () => void;
}

function renderInline(text: string): React.ReactNode {
  return text.split(/(\*\*.*?\*\*)/g).map((part, i) =>
    part.startsWith('**') && part.endsWith('**') ? (
      <strong key={i}>{part.slice(2, -2)}</strong>
    ) : (
      part
    ),
  );
}

/**
 * Renders the transcript, chips, and follow-up input.
 */
export function AskPane(props: AskPaneProps): React.JSX.Element {
  const { messages, isLoading, onSend, onChip, onBack } = props;
  const [draft, setDraft] = useState('');
  const end = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    end.current?.scrollIntoView({ block: 'end' });
  }, [messages]);

  useEffect(() => {
    input.current?.focus();
  }, []);

  const submit = (e: React.FormEvent): void => {
    e.preventDefault();
    if (draft.trim() && !isLoading) {
      onSend(draft.trim());
      setDraft('');
    }
  };

  return (
    <div className={styles.pane}>
      <button type="button" className={styles.back} onClick={onBack}>
        <ArrowLeft size={14} />
        Search
      </button>

      <div className={styles.transcript}>
        {messages.length === 0 && (
          <div className={styles.suggestions}>
            {SUGGESTIONS.map((s) => (
              <button
                key={s}
                type="button"
                className={styles.suggestion}
                onClick={() => onSend(s)}
              >
                {s}
              </button>
            ))}
          </div>
        )}
        {messages.map((m, i) =>
          m.role === 'user' ? (
            <p key={i} className={styles.user}>
              {m.content}
            </p>
          ) : (
            <div key={i} className={styles.reply}>
              {m.content ? (
                m.content.split('\n').map((line, j) => (
                  <p key={j}>{renderInline(line)}</p>
                ))
              ) : (
                <span className={styles.thinking} aria-label="Thinking">
                  <span />
                  <span />
                  <span />
                </span>
              )}
              {m.action_chips && m.action_chips.length > 0 && (
                <div className={styles.chips}>
                  {m.action_chips.map((chip, j) => (
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
            </div>
          ),
        )}
        <div ref={end} />
      </div>

      <form className={styles.composer} onSubmit={submit}>
        <input
          ref={input}
          className={styles.input}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Escape') {
              onBack();
            }
          }}
          placeholder="Ask a follow-up"
          aria-label="Message the advisor"
        />
        <button
          type="submit"
          className={styles.send}
          aria-label="Send"
          disabled={!draft.trim() || isLoading}
        >
          <ArrowUp size={14} />
        </button>
      </form>
    </div>
  );
}
