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
import { getPlan } from '../../state/store';
import type { ActionChip } from '../../types';

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

function str(payload: Record<string, unknown>, key: string): string | undefined {
  const value = payload[key];
  return typeof value === 'string' ? value : undefined;
}

function strs(
  payload: Record<string, unknown>,
  key: string,
): readonly string[] | undefined {
  const value = payload[key];
  return Array.isArray(value) ? (value as string[]) : undefined;
}

/**
 * Applies one chip. Payload fields take precedence over top-level chip
 * fields, matching how the advisor tools emit them.
 */
export function applyActionChip(chip: ActionChip, effects: ChipEffects): void {
  const payload = chip.payload ?? {};
  switch (chip.action) {
    case 'CREATE_CONFIGURATION':
    case 'OVERWRITE_CONFIGURATION':
      setProposal({
        name: str(payload, 'name') ?? chip.config_name ?? 'Suggested',
        sectionIds: strs(payload, 'section_ids') ?? chip.section_ids ?? [],
        targetConfigId:
          chip.action === 'OVERWRITE_CONFIGURATION'
            ? (str(payload, 'config_id') ??
              chip.config_id ??
              getPlan().activeConfigId)
            : undefined,
      });
      effects.showWeek();
      return;
    case 'WATCH_COURSE': {
      const courseId = str(payload, 'course_id') ?? chip.course_id;
      if (courseId) {
        toggleWatch(courseId);
      }
      return;
    }
    case 'RECORD_COMPLETED_COURSES':
    case 'MARK_TAKEN': {
      const courses =
        strs(payload, 'courses') ?? (chip.course_id ? [chip.course_id] : []);
      if (courses.length > 0) {
        recordCompleted(courses);
      }
      return;
    }
    case 'ENROLL_SECTION': {
      // The section record is hydrated by usePlanCourses once it is enrolled.
      const sectionId = str(payload, 'section_id') ?? chip.section_id;
      if (sectionId) {
        enrollSection(sectionId);
        effects.showWeek();
      }
      return;
    }
    case 'tab_degree':
      effects.showDegree();
      return;
    case 'tab_calendar':
    case 'tab_explorer':
      effects.showWeek();
      return;
    case 'NAVIGATE_TAB':
      if ((str(payload, 'tab') ?? chip.target) === 'degree') {
        effects.showDegree();
      } else {
        effects.showWeek();
      }
      return;
    case 'FILTER_EXPLORER':
    case 'search_course':
      effects.search(str(payload, 'query') ?? chip.target ?? '');
      return;
  }
}
