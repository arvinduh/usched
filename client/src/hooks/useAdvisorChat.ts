/**
 * Ephemeral advisor conversation state and token streaming.
 *
 * Holds the message list in memory only, so a reload starts a fresh
 * conversation. Plan context (enrolled, watched, completed, degree) is passed
 * in per message by the caller; this hook never reads the plan store.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { streamAdvisorChat } from '../api/client';
import type { ChatMessage } from '../types';

/**
 * Plan snapshot sent alongside each message to ground the advisor.
 */
export interface AdvisorContext {
  readonly enrolledCourseIds: readonly string[];
  readonly watchedCourseIds: readonly string[];
  readonly completedCourseIds: readonly string[];
  readonly degreeId: string;
}

/**
 * Conversation transcript and the controls that change it.
 */
export interface AdvisorChat {
  readonly messages: readonly ChatMessage[];
  readonly isLoading: boolean;
  readonly send: (text: string, context: AdvisorContext) => Promise<void>;
  /** Restarts the conversation; a reply still streaming is discarded. */
  readonly clear: () => void;
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
  // Bumped by `clear` so a stream still in flight stops writing.
  const generation = useRef(0);

  const send = useCallback(
    async (text: string, context: AdvisorContext): Promise<void> => {
      const gen = generation.current;
      const isCurrent = (): boolean => gen === generation.current;
      const patchLast = (patch: Partial<ChatMessage>): void => {
        if (isCurrent()) {
          setMessages((prev) => [
            ...prev.slice(0, -1),
            { ...prev[prev.length - 1], ...patch },
          ]);
        }
      };

      const history: readonly ChatMessage[] = [
        ...latest.current,
        { role: 'user', content: text },
      ];
      setMessages([...history, { role: 'assistant', content: '' }]);
      setIsLoading(true);

      let content = '';
      await streamAdvisorChat(
        text,
        history,
        context.enrolledCourseIds,
        context.watchedCourseIds,
        context.completedCourseIds,
        context.degreeId,
        (token) => {
          content += token;
          patchLast({ content });
        },
        (chips) => patchLast({ action_chips: chips }),
        () => {
          if (isCurrent()) {
            setIsLoading(false);
          }
        },
      );
    },
    [],
  );

  const clear = useCallback((): void => {
    generation.current += 1;
    setMessages([]);
    setIsLoading(false);
  }, []);

  return { messages, isLoading, send, clear };
}
