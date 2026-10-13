/**
 * Minimal observable value for state that lives outside React.
 *
 * Lets frequently changing state (hover previews, toasts) and persisted
 * state share one subscription mechanism, while only the components that
 * select a slice re-render when it changes.
 */

import { useSyncExternalStore } from 'react';

/**
 * An observable value.
 */
export interface ExternalStore<T> {
  readonly get: () => T;
  /** Replaces the value and notifies subscribers unless `next` is identical. */
  readonly set: (next: T) => void;
  readonly subscribe: (listener: () => void) => () => void;
}

/**
 * Creates an observable holding `initial`.
 */
export function createExternalStore<T>(initial: T): ExternalStore<T> {
  let value = initial;
  const listeners = new Set<() => void>();
  return {
    get: () => value,
    set: (next) => {
      if (next === value) {
        return;
      }
      value = next;
      for (const listener of listeners) {
        listener();
      }
    },
    subscribe: (listener) => {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
  };
}

/**
 * Selects a slice of a store and re-renders when it changes. The selector
 * must return a reference held in the value, not a freshly built object.
 */
export function useSelector<T, S>(
  store: ExternalStore<T>,
  selector: (value: T) => S,
): S {
  return useSyncExternalStore(store.subscribe, () => selector(store.get()));
}
