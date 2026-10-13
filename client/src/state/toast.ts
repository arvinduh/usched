/**
 * Single-slot toast queue for confirmations and undo.
 *
 * Destructive actions apply immediately and announce themselves here with
 * an inverse operation, replacing confirmation dialogs. A new toast replaces
 * the current one; each auto-dismisses after a few seconds.
 */

import { createExternalStore, useSelector } from './_externalStore';

const LIFETIME_MS = 5000;

/**
 * A visible toast; `undo` reverses the action it announces.
 */
export interface Toast {
  readonly id: number;
  readonly message: string;
  readonly undo?: () => void;
}

const toasts = createExternalStore<Toast | null>(null);
let nextId = 1;
let timer: ReturnType<typeof setTimeout> | undefined;

/**
 * Shows a toast, replacing any current one.
 */
export function showToast(message: string, undo?: () => void): void {
  clearTimeout(timer);
  const toast = { id: nextId++, message, undo };
  toasts.set(toast);
  timer = setTimeout(() => dismissToast(toast.id), LIFETIME_MS);
}

/**
 * Hides the toast with `id` if it is still showing.
 */
export function dismissToast(id: number): void {
  if (toasts.get()?.id === id) {
    toasts.set(null);
  }
}

/**
 * Runs the current toast's undo, if any, and hides it. Returns whether
 * there was something to undo.
 */
export function undoLast(): boolean {
  const toast = toasts.get();
  if (!toast?.undo) {
    return false;
  }
  toast.undo();
  toasts.set(null);
  return true;
}

/**
 * Selects the visible toast.
 */
export function useToast(): Toast | null {
  return useSelector(toasts, (t) => t);
}
