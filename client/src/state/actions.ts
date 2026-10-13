/**
 * Named mutations over the persisted plan store.
 *
 * Each action is a pure recipe applied through `update`, so callers never
 * touch storage or close over stale state. Destructive actions return their
 * inverse so callers can offer undo. Fetching and rendering belong to hooks
 * and components; this module only edits user-authored data.
 */

import { courseKey } from '../degree/_degree';
import { displaces } from '../semester/_schedule';
import { update, updateTerm } from './store';
import type { ScheduleConfiguration, TermPlan } from './store';
import type { components } from '../api/schema';

function toggle(ids: readonly string[], id: string): readonly string[] {
  return ids.includes(id) ? ids.filter((x) => x !== id) : [...ids, id];
}

function editConfig(
  s: TermPlan,
  configId: string,
  edit: (c: ScheduleConfiguration) => ScheduleConfiguration,
): TermPlan {
  return {
    ...s,
    configurations: s.configurations.map((c) =>
      c.id === configId ? edit(c) : c,
    ),
  };
}

/** Names variants A, B, C... by first unused letter, then by number. */
function nextName(configs: readonly ScheduleConfiguration[]): string {
  const used = new Set(configs.map((c) => c.name));
  for (let i = 0; i < 26; i++) {
    const letter = String.fromCharCode(65 + i);
    if (!used.has(letter)) {
      return letter;
    }
  }
  return `${configs.length + 1}`;
}

function appendConfig(
  s: TermPlan,
  id: string,
  sectionIds: readonly string[],
  name?: string,
): TermPlan {
  return {
    ...s,
    configurations: [
      ...s.configurations,
      { id, name: name || nextName(s.configurations), section_ids: sectionIds },
    ],
    activeConfigId: id,
  };
}

/**
 * Adds a schedule variant, makes it active, and returns its ID.
 */
export function createConfig(
  name?: string,
  sectionIds: readonly string[] = [],
): string {
  const id = `config-${Date.now()}`;
  updateTerm((s) => appendConfig(s, id, sectionIds, name));
  return id;
}

/**
 * Forks the active variant into a new active variant with the same sections.
 */
export function duplicateActiveConfig(): void {
  updateTerm((s) => {
    const active = s.configurations.find((c) => c.id === s.activeConfigId);
    return appendConfig(s, `config-${Date.now()}`, active?.section_ids ?? []);
  });
}

/**
 * Makes the given configuration the one the calendar shows.
 */
export function selectConfig(configId: string): void {
  updateTerm((s) => ({ ...s, activeConfigId: configId }));
}

/**
 * Activates the variant `step` places after the active one, wrapping around.
 */
export function cycleConfig(step: 1 | -1): void {
  updateTerm((s) => {
    const n = s.configurations.length;
    const i = s.configurations.findIndex((c) => c.id === s.activeConfigId);
    return { ...s, activeConfigId: s.configurations[(i + step + n) % n].id };
  });
}

/**
 * Renames a schedule configuration.
 */
export function renameConfig(configId: string, name: string): void {
  updateTerm((s) => editConfig(s, configId, (c) => ({ ...c, name })));
}

/**
 * Replaces every section in a configuration (the active one by default).
 */
export function overwriteConfig(
  sectionIds: readonly string[],
  configId?: string,
): void {
  updateTerm((s) =>
    editConfig(s, configId ?? s.activeConfigId, (c) => ({
      ...c,
      section_ids: sectionIds,
    })),
  );
}

/**
 * Deletes a configuration, refusing to remove the last one, and activates a
 * neighbor when the active one goes. Returns the inverse, which restores the
 * variant at its old position and reactivates it.
 */
export function deleteConfig(configId: string): () => void {
  let removed: ScheduleConfiguration | undefined;
  let index = -1;
  let wasActive = false;
  updateTerm((s) => {
    index = s.configurations.findIndex((c) => c.id === configId);
    if (s.configurations.length <= 1 || index === -1) {
      return s;
    }
    removed = s.configurations[index];
    wasActive = s.activeConfigId === configId;
    const configurations = s.configurations.filter((c) => c.id !== configId);
    return {
      ...s,
      configurations,
      activeConfigId: wasActive
        ? configurations[Math.max(0, index - 1)].id
        : s.activeConfigId,
    };
  });
  return () => {
    if (!removed) {
      return;
    }
    const restored = removed;
    updateTerm((s) => {
      const configurations = [...s.configurations];
      configurations.splice(index, 0, restored);
      return {
        ...s,
        configurations,
        activeConfigId: wasActive ? restored.id : s.activeConfigId,
      };
    });
  };
}

/**
 * Adds a section to a configuration (the active one by default).
 */
export function enrollSection(sectionId: string, configId?: string): void {
  updateTerm((s) =>
    editConfig(s, configId ?? s.activeConfigId, (c) =>
      c.section_ids.includes(sectionId)
        ? c
        : { ...c, section_ids: [...c.section_ids, sectionId] },
    ),
  );
}

/**
 * Removes a section from a configuration (the active one by default) and
 * returns the inverse.
 */
export function dropSection(sectionId: string, configId?: string): () => void {
  let target = configId;
  updateTerm((s) => {
    target ??= s.activeConfigId;
    return editConfig(s, target, (c) => ({
      ...c,
      section_ids: c.section_ids.filter((id) => id !== sectionId),
    }));
  });
  return () => enrollSection(sectionId, target);
}

/**
 * Puts `section` in a variant, removing the course's sections it displaces:
 * one of the same type (a student takes one lecture, one lab, ...) or from
 * another link group.
 */
function withSection(
  c: ScheduleConfiguration,
  section: components['schemas']['Section'],
  courseSections: readonly components['schemas']['Section'][],
): ScheduleConfiguration {
  const rivals = new Set(
    courseSections.filter((x) => displaces(section, x)).map((x) => x.id),
  );
  return {
    ...c,
    section_ids: [
      ...c.section_ids.filter((id) => !rivals.has(id)),
      section.id,
    ],
  };
}

/**
 * Adds a section to a variant (the active one by default), swapping out a
 * same-type sibling.
 */
export function addSection(
  section: components['schemas']['Section'],
  courseSections: readonly components['schemas']['Section'][],
  configId?: string,
): void {
  updateTerm((s) =>
    editConfig(s, configId ?? s.activeConfigId, (c) =>
      withSection(c, section, courseSections),
    ),
  );
}

/**
 * Toggles a section in the active variant, swapping out a same-type sibling
 * when adding.
 */
export function toggleSection(
  section: components['schemas']['Section'],
  courseSections: readonly components['schemas']['Section'][],
): void {
  updateTerm((s) =>
    editConfig(s, s.activeConfigId, (c) =>
      c.section_ids.includes(section.id)
        ? { ...c, section_ids: c.section_ids.filter((id) => id !== section.id) }
        : withSection(c, section, courseSections),
    ),
  );
}

/**
 * Adds or removes a course from this term's shortlist.
 */
export function toggleWatch(courseId: string): void {
  updateTerm((s) => ({
    ...s,
    watchedCourseIds: toggle(s.watchedCourseIds, courseId),
  }));
}

/**
 * Adds or removes a course from the completed list, matching IDs
 * case-insensitively. Returns the inverse.
 */
export function toggleCompleted(courseId: string): () => void {
  const key = courseKey(courseId);
  update((s) => {
    const kept = s.completedCourseIds.filter((id) => courseKey(id) !== key);
    return {
      ...s,
      completedCourseIds:
        kept.length < s.completedCourseIds.length ? kept : [...kept, key],
    };
  });
  return () => {
    toggleCompleted(key);
  };
}

/**
 * Marks courses completed, ignoring ones already recorded. Returns the
 * inverse, which unmarks only the courses this call added.
 */
export function recordCompleted(courseIds: readonly string[]): () => void {
  let added: ReadonlySet<string> = new Set();
  update((s) => {
    const have = new Set(s.completedCourseIds.map(courseKey));
    added = new Set(courseIds.map(courseKey).filter((k) => !have.has(k)));
    return added.size === 0
      ? s
      : { ...s, completedCourseIds: [...s.completedCourseIds, ...added] };
  });
  return () =>
    update((s) => ({
      ...s,
      completedCourseIds: s.completedCourseIds.filter(
        (id) => !added.has(courseKey(id)),
      ),
    }));
}

/**
 * Counts one more GE seat by hand, or clears the category's count once it
 * is full, so repeated clicks cycle from empty to full and back. Returns
 * the inverse.
 */
export function countGeSeat(code: string, isFull: boolean): () => void {
  let before: Readonly<Record<string, number>> = {};
  update((s) => {
    before = s.geCounted;
    const { [code]: count = 0, ...rest } = s.geCounted;
    return { ...s, geCounted: isFull ? rest : { ...rest, [code]: count + 1 } };
  });
  return () => update((s) => ({ ...s, geCounted: before }));
}

/**
 * Adds or removes AP credit for an exam, recorded as a passing score of 5.
 */
export function toggleApCredit(examId: string): void {
  update((s) => ({
    ...s,
    apCredits: s.apCredits.some((c) => c.exam_id === examId)
      ? s.apCredits.filter((c) => c.exam_id !== examId)
      : [...s.apCredits, { exam_id: examId, score: 5 }],
  }));
}

/**
 * Sets the program audited on the degree view.
 */
export function selectProgram(programId: string): void {
  update((s) => ({ ...s, programId, welcomed: true }));
}

/**
 * Dismisses the first-run welcome without choosing a program.
 */
export function skipWelcome(): void {
  update((s) => (s.welcomed ? s : { ...s, welcomed: true }));
}

/**
 * Switches the term being planned; each term keeps its own schedules.
 */
export function selectTerm(term: number): void {
  update((s) => (s.term === term ? s : { ...s, term }));
}
