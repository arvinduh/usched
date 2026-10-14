/**
 * Runs a DOM update as a view transition where the browser supports them.
 *
 * Elements that share a `view-transition-name` across the update morph
 * from one to the other; everything else swaps at once and runs its own
 * CSS entrance. Browsers without the API, and reduced motion (index.css
 * cancels the animations), get the plain update.
 */

/**
 * Applies `update`, animated as a view transition when supported.
 *
 * The update must change the DOM synchronously: wrap React state changes
 * in `flushSync`.
 */
export function morph(update: () => void): void {
  if (!('startViewTransition' in document)) {
    update();
    return;
  }
  // A skipped animation (hidden tab, rapid toggling) rejects `ready`; the
  // update itself still applies, so the rejection is noise.
  document.startViewTransition(update).ready.catch(() => {});
}
