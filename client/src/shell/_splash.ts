/**
 * Hands the page from the loading splash to the app's first screen.
 *
 * The splash is static markup in index.html, so it shows before any script
 * has loaded. While the root carries `data-booting`, splash.css pauses the
 * app's entrance animations underneath it; revealing removes both in one
 * view transition, so the splash wordmark glides into the screen's own
 * wordmark while the screen rises in.
 */

import { useEffect } from 'react';
import { morph } from '../ui/_morph';

let revealed = false;

function reveal(): void {
  const splash = document.querySelector('.splash');
  if (revealed || !splash) {
    return;
  }
  revealed = true;
  const finish = (): void => {
    splash.remove();
    delete document.documentElement.dataset.booting;
  };
  // A load quicker than the splash's delayed fade-in skips the hand-off:
  // morphing a wordmark nobody saw yet reads as a glitch, not an entrance.
  const mark = splash.querySelector('.splash-mark');
  if (!mark || Number(getComputedStyle(mark).opacity) < 0.5) {
    finish();
  } else {
    morph(finish);
  }
}

/**
 * Reveals the app once `ready` turns true; later calls do nothing.
 */
export function useRevealApp(ready: boolean): void {
  useEffect(() => {
    if (ready) {
      reveal();
    }
  }, [ready]);
}
