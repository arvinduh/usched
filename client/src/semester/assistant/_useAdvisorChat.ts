/**
 * Ephemeral advisor conversation state and token streaming.
 *
 * Holds the message list in memory only, so a reload starts a fresh
 * conversation. Plan context (term, schedules, shortlist, completed,
 * program) and what is on screen are passed in per message by the caller;
 * this hook never reads the plan store.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { streamChat } from '../../api/client';
import type { components } from '../../api/schema';

/**
 * A message in the advisor thread; lives only until reload.
 */
export interface ChatMessage {
  readonly id: string;
  readonly role: 'user' | 'assistant';
  readonly content: string;
  /** Tools the advisor ran while replying, in words, in order. */
  readonly steps?: readonly string[];
  /** The advisor's reasoning summary for this reply. */
  readonly thinking?: string;
  readonly chips?: components['schemas']['ClosingEvent']['action_chips'];
  /** Courses the reply names that the catalog does not have. */
  readonly unverified?: readonly string[];
}

/**
 * Plan snapshot sent alongside each message to ground the advisor.
 */
export interface AdvisorContext {
  readonly term: number;
  /** Sections in the active schedule. */
  readonly sectionIds: readonly string[];
  readonly shortlistedCodes: readonly string[];
  readonly completedCodes: readonly string[];
  readonly apCredits: readonly components['schemas']['ApCredit'][];
  /** GE seats counted by hand, by category code. */
  readonly geCounted: Readonly<Record<string, number>>;
  readonly programId: string;
  /** The student's other schedules. */
  readonly variants: readonly components['schemas']['Variant'][];
  /** What the student is looking at as they ask. */
  readonly screen: components['schemas']['Screen'];
}

/**
 * Conversation transcript and the controls that change it.
 */
export interface AdvisorChat {
  readonly messages: readonly ChatMessage[];
  readonly isLoading: boolean;
  readonly send: (text: string, context: AdvisorContext) => void;
  /** Restarts the conversation; a reply still streaming is discarded. */
  readonly clear: () => void;
}

let nextId = 0;

function message(role: ChatMessage['role'], content: string): ChatMessage {
  nextId += 1;
  return { id: `m${nextId}`, role, content };
}

/**
 * Streams advisor replies into the last message as tokens arrive, and hands
 * each finished reply's chips to `onChips` so the caller can act on them
 * without a click (projecting proposed schedules, for one).
 */
export function useAdvisorChat(
  onChips: (chips: components['schemas']['ClosingEvent']['action_chips']) => void,
): AdvisorChat {
  const [messages, setMessages] = useState<readonly ChatMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  // Mirrors `messages` so `send` can build history without re-binding.
  const latest = useRef(messages);
  useEffect(() => {
    latest.current = messages;
  }, [messages]);
  const chipsHandler = useRef(onChips);
  useEffect(() => {
    chipsHandler.current = onChips;
  }, [onChips]);
  // Aborts the reply in flight; `clear` uses it to stop a stream.
  const abort = useRef<(() => void) | null>(null);

  const send = useCallback((text: string, context: AdvisorContext): void => {
    abort.current?.();
    const reply = message('assistant', '');
    const patchReply = (patch: Partial<ChatMessage>): void =>
      setMessages((prev) =>
        prev.map((m) => (m.id === reply.id ? { ...m, ...patch } : m)),
      );
    const history = latest.current;
    setMessages([...history, message('user', text), reply]);
    setIsLoading(true);

    let content = '';
    let steps: readonly string[] = [];
    let thinking = '';
    abort.current = streamChat(
      {
        message: text,
        // Chips ride along so the advisor remembers what each reply offered.
        history: history.map(({ role, content: c, chips }) => ({
          role,
          content: c,
          action_chips: chips ? [...chips] : [],
        })),
        term: context.term,
        program_id: context.programId || null,
        section_ids: [...context.sectionIds],
        shortlisted: [...context.shortlistedCodes],
        completed: [...context.completedCodes],
        ap_credits: [...context.apCredits],
        ge_counted: { ...context.geCounted },
        variants: [...context.variants],
        screen: context.screen,
      },
      {
        onToken: (token) => {
          content += token;
          patchReply({ content });
        },
        onStep: (step) => {
          steps = [...steps, step];
          patchReply({ steps });
        },
        onThought: (text) => {
          thinking += text;
          patchReply({ thinking });
        },
        onClose: (event) => {
          patchReply({ chips: event.action_chips, unverified: event.unverified });
          chipsHandler.current(event.action_chips);
        },
        onDone: () => setIsLoading(false),
      },
    );
  }, []);

  const clear = useCallback((): void => {
    abort.current?.();
    abort.current = null;
    setMessages([]);
    setIsLoading(false);
  }, []);

  return { messages, isLoading, send, clear };
}
