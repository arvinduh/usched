/**
 * Two-step control that erases all locally stored plan data.
 *
 * The first click arms the button for a few seconds; only a second click
 * inside that window calls `onReset`. What "all data" means is the caller's
 * concern.
 */

import React, { useEffect, useState } from 'react';
import styles from './ResetButton.module.css';

const ARM_WINDOW_MS = 3000;

/**
 * Properties for the reset control.
 */
export interface ResetButtonProps {
  readonly onReset: () => void;
}

/**
 * Renders a quiet text button that asks for a confirming second click.
 */
export function ResetButton({ onReset }: ResetButtonProps): React.JSX.Element {
  const [armed, setArmed] = useState(false);

  useEffect(() => {
    if (!armed) {
      return;
    }
    const timer = setTimeout(() => setArmed(false), ARM_WINDOW_MS);
    return () => clearTimeout(timer);
  }, [armed]);

  return (
    <button
      type="button"
      className={`${styles.button} ${armed ? styles.armed : ''}`}
      onClick={() => {
        if (armed) {
          setArmed(false);
          onReset();
        } else {
          setArmed(true);
        }
      }}
    >
      {armed ? 'Click again to erase' : 'Reset all data'}
    </button>
  );
}
