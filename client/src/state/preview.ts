/**
 * Transient "what if" state that the week renders as ghosts.
 *
 * Hover, expansion, and advisor proposals change often and must never be
 * persisted until the user commits, so they live in their own store: only
 * the Library rows and the week subscribe, and the app root never re-renders
 * on hover.
 */

import { createExternalStore, useSelector } from '../lib/externalStore';
import type { Course } from '../types';

/**
 * A whole schedule suggested by the advisor, shown before it is kept.
 */
export interface Proposal {
  readonly name: string;
  readonly sectionIds: readonly string[];
}

interface Preview {
  /** Course whose sections are offered as ghosts on the week. */
  readonly expanded: Course | null;
  /** Section the pointer or keyboard is on; its ghost is emphasized. */
  readonly focusId: string | null;
  /** Schedules the advisor proposed; the week projects one at a time. */
  readonly proposals: readonly Proposal[];
  /** Index of the projected proposal; meaningless when there are none. */
  readonly shown: number;
}

const preview = createExternalStore<Preview>({
  expanded: null,
  focusId: null,
  proposals: [],
  shown: 0,
});

/**
 * Selects a slice of the preview state.
 */
export function usePreview<T>(selector: (p: Preview) => T): T {
  return useSelector(preview, selector);
}

/**
 * Expands a course (ghosting its sections), or collapses with `null`.
 */
export function setExpanded(course: Course | null): void {
  preview.set({ ...preview.get(), expanded: course, focusId: null });
}

/**
 * Reports whether any course is expanded, for handlers outside React.
 */
export function hasExpanded(): boolean {
  return preview.get().expanded !== null;
}

/**
 * Collapses `course` if it is expanded, otherwise expands it.
 */
export function toggleExpanded(course: Course): void {
  setExpanded(preview.get().expanded?.code === course.code ? null : course);
}

/**
 * Emphasizes one section's ghost, or clears emphasis with `null`.
 */
export function setFocus(sectionId: string | null): void {
  const current = preview.get();
  if (current.focusId !== sectionId) {
    preview.set({ ...current, focusId: sectionId });
  }
}

/**
 * The proposal the week projects, or null; stable for `usePreview`.
 */
export function shownProposal(p: Preview): Proposal | null {
  return p.proposals[p.shown] ?? null;
}

/**
 * Projects advisor proposals onto the week, first one first; an empty list
 * clears them.
 */
export function setProposals(proposals: readonly Proposal[]): void {
  preview.set({ ...preview.get(), proposals, shown: 0, expanded: null, focusId: null });
}

/**
 * Projects the next (`1`) or previous (`-1`) proposal, wrapping around.
 */
export function cycleProposal(step: 1 | -1): void {
  const current = preview.get();
  const count = current.proposals.length;
  if (count > 1) {
    preview.set({ ...current, shown: (current.shown + step + count) % count });
  }
}
