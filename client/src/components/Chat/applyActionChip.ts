/**
 * Translates advisor action chips into plan mutations and navigation.
 *
 * Small plan edits go straight to the store actions. Whole-schedule
 * suggestions become proposals the user keeps or discards on the week, and
 * anything that changes what the user is looking at goes through the
 * caller-supplied `ChipEffects`, so this module stays independent of the
 * app shell's view state.
 */

import { enrollSection, recordCompleted, toggleWatch } from '../../state/actions';
import { setProposal } from '../../state/preview';
import type { Chip } from '../../types';

/**
 * View-level effects a chip may trigger.
 */
export interface ChipEffects {
  /** Brings the week into view, keeping the conversation open. */
  readonly showWeek: () => void;
  readonly showDegree: () => void;
  /** Leaves the conversation for the Library with this query. */
  readonly search: (query: string) => void;
}

/**
 * Applies one chip; the union's `action` narrows each case's fields.
 */
export function applyActionChip(chip: Chip, effects: ChipEffects): void {
  switch (chip.action) {
    case 'propose_schedule':
      setProposal({ name: chip.name, sectionIds: chip.section_ids });
      effects.showWeek();
      return;
    case 'enroll_section':
      // usePlanCourses hydrates the section once it is in the plan.
      enrollSection(chip.section_id);
      effects.showWeek();
      return;
    case 'watch_course':
      toggleWatch(chip.course_code);
      return;
    case 'mark_completed':
      recordCompleted(chip.course_codes);
      return;
    case 'show':
      if (chip.view === 'degree') {
        effects.showDegree();
      } else {
        effects.showWeek();
      }
      return;
    case 'search':
      effects.search(chip.query);
      return;
  }
}
