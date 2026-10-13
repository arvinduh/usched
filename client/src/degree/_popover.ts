/**
 * Placement for the degree's chip popovers inside the clipping column.
 *
 * Popovers open rightward from their chip by default. The column the
 * degree lives in clips overflow, so a chip near its right edge anchors its
 * popover to the right instead. Styling lives in Degree.module.css.
 */

import type React from 'react';

/** The popover's widest extent, matching `.chipPop`'s max-width. */
const POPOVER_PX = 260;

/**
 * Anchors a chip's popover to its right edge when opening rightward would
 * cross the enclosing section. Writes a data attribute rather than state so
 * hovering never re-renders the tree.
 */
export function placePopover(e: React.SyntheticEvent<HTMLElement>): void {
  const chip = e.currentTarget;
  const bound = chip.closest('section')?.getBoundingClientRect().right ?? window.innerWidth;
  chip.dataset.flip = String(chip.getBoundingClientRect().left + POPOVER_PX > bound);
}
