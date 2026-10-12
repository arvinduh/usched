/**
 * Ephemeral advisor conversation state and token streaming.
 *
 * Holds the message list in memory only, so a reload starts a fresh
 * conversation. Plan context (term, schedule, shortlist, completed, program)
 * is passed in per message by the caller; this hook never reads the plan
 * store.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { streamChat } from '../api/client';
import type { ChatMessage } from '../types';

/**
 * Plan snapshot sent alongside each message to ground the advisor.
 */
export interface AdvisorContext {
  readonly term: number;
  readonly plannedCodes: readonly string[];
  readonly shortlistedCodes: readonly string[];
  readonly completedCodes: readonly string[];
  readonly programId: string;
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
 * Streams advisor replies into the last message as tokens arrive.
 */
export function useAdvisorChat(): AdvisorChat {
  const [messages, setMessages] = useState<readonly ChatMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  // Mirrors `messages` so `send` can build history without re-binding.
  const latest = useRef(messages);
  useEffect(() => {
    latest.current = messages;
  }, [messages]);
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
    abort.current = streamChat(
      {
        message: text,
        history: history.map(({ role, content: c }) => ({ role, content: c })),
        term: context.term,
        program_id: context.programId || null,
        planned: [...context.plannedCodes],
        shortlisted: [...context.shortlistedCodes],
        completed: [...context.completedCodes],
      },
      {
        onToken: (token) => {
          content += token;
          patchReply({ content });
        },
        onChips: (chips) => patchReply({ chips }),
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
