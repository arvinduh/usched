/**
 * Bottom-center toast host with an optional undo action.
 *
 * Renders whatever `state/toast` currently holds; the store owns timing.
 */

import React from 'react';
import { undoLast, useToast } from '../state/toast';
import styles from './Toast.module.css';

/**
 * Renders the active toast, keyed so each new one replays its entrance.
 */
export function ToastHost(): React.JSX.Element | null {
  const toast = useToast();
  if (!toast) {
    return null;
  }
  return (
    <div key={toast.id} className={styles.toast} role="status">
      <span>{toast.message}</span>
      {toast.undo && (
        <button type="button" className={styles.undo} onClick={undoLast}>
          Undo
        </button>
      )}
    </div>
  );
}
