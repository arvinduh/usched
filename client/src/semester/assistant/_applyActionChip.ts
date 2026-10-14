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
import { showToast } from '../../state/toast';
import type { components } from '../../api/schema';

/**
 * The schedules among `chips`, in the order the advisor ranked them.
 */
export function proposalsOf(
  chips: readonly components['schemas']['ClosingEvent']['action_chips'][number][],
): readonly Proposal[] {
  return chips.flatMap((c) => {
    if (c.action !== 'propose_schedule') {
      return [];
    }
    const sectionIds = (c.section_ids ?? [])
      .map((id) => (typeof id === 'string' ? id.trim() : ''))
      .filter((id) => id.length > 0);
    return sectionIds.length > 0
      ? [{ name: c.name || 'Proposal', sectionIds }]
      : [];
  });
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
export function applyActionChip(
  chip: components['schemas']['ClosingEvent']['action_chips'][number],
  effects: ChipEffects,
): void {
  if (!chip || typeof chip !== 'object' || !('action' in chip)) {
    showToast('Invalid action chip.');
    return;
  }
  switch (chip.action) {
    case 'propose_schedule': {
      const validSectionIds = (chip.section_ids ?? [])
        .map((id) => (typeof id === 'string' ? id.trim() : ''))
        .filter((id) => id.length > 0);
      if (validSectionIds.length === 0) {
        showToast('Cannot propose schedule: no valid section IDs provided.');
        return;
      }
      setProposals([{ name: chip.name || 'Proposal', sectionIds: validSectionIds }]);
      return;
    }
    case 'enroll_section': {
      const sectionId = typeof chip.section_id === 'string' ? chip.section_id.trim() : '';
      if (!sectionId) {
        showToast('Cannot enroll: section ID is missing or invalid.');
        return;
      }
      // usePlanCourses hydrates the section once it is in the plan.
      enrollSection(sectionId);
      return;
    }
    case 'watch_course': {
      const courseCode = typeof chip.course_code === 'string' ? chip.course_code.trim() : '';
      if (!courseCode) {
        showToast('Cannot watch course: course code is missing or invalid.');
        return;
      }
      toggleWatch(courseCode);
      return;
    }
    case 'mark_taken': {
      const validCodes = (chip.course_codes ?? [])
        .map((code) => (typeof code === 'string' ? code.trim() : ''))
        .filter((code) => code.length > 0);
      if (validCodes.length === 0) {
        showToast('Cannot mark taken: no course codes provided.');
        return;
      }
      recordCompleted(validCodes);
      return;
    }
    case 'search': {
      const query = typeof chip.query === 'string' ? chip.query.trim() : '';
      if (!query) {
        showToast('Cannot search: query is empty.');
        return;
      }
      effects.search(query);
      return;
    }
  }
}
