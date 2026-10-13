/**
 * Translates advisor action chips into plan mutations and navigation.
 *
 * Small plan edits go straight to the store actions. Whole-schedule
 * suggestions become proposals the user keeps or discards on the week, and
 * opening or searching goes through the caller-supplied `ChipEffects`, so
 * this module stays independent of the app shell's view state.
 */

import { enrollSection, recordCompleted, toggleWatch } from '../../state/actions';
import { setProposals } from '../../state/preview';
import type { Proposal } from '../../state/preview';
import type { Chip } from '../../types';

/**
 * The schedules among `chips`, in the order the advisor ranked them.
 */
export function proposalsOf(chips: readonly Chip[]): readonly Proposal[] {
  return chips.flatMap((c) =>
    c.action === 'propose_schedule' ? [{ name: c.name, sectionIds: c.section_ids }] : [],
  );
}

/**
 * View-level effects a chip may trigger.
 */
export interface ChipEffects {
  /** Opens a course by code, or searches for anything else. */
  readonly search: (query: string) => void;
}

/**
 * Applies one chip; the union's `action` narrows each case's fields.
 */
export function applyActionChip(chip: Chip, effects: ChipEffects): void {
  switch (chip.action) {
    case 'propose_schedule':
      setProposals([{ name: chip.name, sectionIds: chip.section_ids }]);
      return;
    case 'enroll_section':
      // usePlanCourses hydrates the section once it is in the plan.
      enrollSection(chip.section_id);
      return;
    case 'watch_course':
      toggleWatch(chip.course_code);
      return;
    case 'mark_taken':
      recordCompleted(chip.course_codes);
      return;
    case 'search':
      effects.search(chip.query);
      return;
  }
}
