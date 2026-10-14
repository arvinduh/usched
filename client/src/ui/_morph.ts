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
 * in `flushSync`. A `type` lets CSS name elements for this transition only,
 * through `:active-view-transition-type(<type>)`; browsers without types
 * still run the transition, just without those names.
 */
export function morph(update: () => void, type?: string): void {
  if (!('startViewTransition' in document)) {
    update();
    return;
  }
  const transition = document.startViewTransition(update);
  if (type && 'types' in transition) {
    transition.types.add(type);
  }
  // A skipped animation (hidden tab, rapid toggling) rejects `ready`; the
  // update itself still applies, so the rejection is noise.
  transition.ready.catch(() => {});
}
