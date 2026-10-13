/**
 * Resolves the course and section records the student's plan points at.
 *
 * The persisted store keeps only codes and section numbers, so it cannot
 * render the week or the shortlist on its own. This hook keeps an
 * in-memory cache of the planning term's referenced courses and fetches
 * any reference it cannot resolve: on boot, on a term switch, after another
 * tab edits the plan, or when an advisor chip names a section never shown.
 * Search results stay out of it: courses enter when the student opens,
 * picks, or saves them, so paging through results never touches the week.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { getCourses, getSections } from '../api/client';
import type { components } from '../api/schema';
import { usePreview } from './preview';
import { useTermPlan } from './store';

/**
 * Lookup tables for every course and section the client knows this term.
 */
export interface PlanCourses {
  readonly coursesByCode: ReadonlyMap<string, components['schemas']['Course']>;
  readonly sectionsById: ReadonlyMap<string, components['schemas']['Section']>;
  /** Pins a course so it outlives the catalog page it came from. */
  readonly remember: (course: components['schemas']['Course']) => void;
}

interface TermCache {
  readonly term: number;
  readonly courses: ReadonlyMap<string, components['schemas']['Course']>;
}

/**
 * Resolves cached plan courses and hydrates misses, including
 * `wantedCodes` the caller is about to show (next up).
 */
export function usePlanCourses(
  term: number,
  wantedCodes: readonly string[],
): PlanCourses {
  const configurations = useTermPlan((p) => p.configurations);
  const watched = useTermPlan((p) => p.watchedCourseIds);
  const proposals = usePreview((p) => p.proposals);

  const [cache, setCache] = useState<TermCache>(() => ({
    term,
    courses: new Map(),
  }));
  // References already requested this term; failures are never retried.
  const requested = useRef({ term, ids: new Set<string>() });
  const cached = cache.term === term ? cache.courses : undefined;

  const coursesByCode = useMemo(
    () => cached ?? new Map<string, components['schemas']['Course']>(),
    [cached],
  );

  const sectionsById = useMemo(() => {
    const map = new Map<string, components['schemas']['Section']>();
    for (const course of coursesByCode.values()) {
      for (const section of course.sections) {
        map.set(section.id, section);
      }
    }
    return map;
  }, [coursesByCode]);

  const add = useCallback(
    (forTerm: number, courses: readonly components['schemas']['Course'][]): void => {
      setCache((prev) => {
        const base = prev.term === forTerm ? prev.courses : new Map();
        const next = new Map(base);
        for (const course of courses) {
          next.set(course.code, course);
        }
        return { term: forTerm, courses: next };
      });
    },
    [],
  );

  const remember = useCallback(
    (course: components['schemas']['Course']): void => {
      if (!cached?.has(course.code)) {
        add(course.term, [course]);
      }
    },
    [add, cached],
  );

  useEffect(() => {
    if (requested.current.term !== term) {
      requested.current = { term, ids: new Set() };
    }
    const ids = requested.current.ids;
    const sectionIds = [
      ...new Set([
        ...configurations.flatMap((c) => c.section_ids),
        ...proposals.flatMap((p) => p.sectionIds),
      ]),
    ].filter((id) => !sectionsById.has(id) && !ids.has(`s:${id}`));
    const codes = [...new Set([...watched, ...wantedCodes])].filter(
      (code) => !coursesByCode.has(code) && !ids.has(`c:${code}`),
    );
    if (sectionIds.length === 0 && codes.length === 0) {
      return;
    }
    for (const id of sectionIds) {
      ids.add(`s:${id}`);
    }
    for (const code of codes) {
      ids.add(`c:${code}`);
    }
    // Two requests at most: sections name their courses, then one batch
    // loads every missing course.
    const hydrate = async (): Promise<void> => {
      const sections = await getSections(term, sectionIds);
      const toFetch = new Set([...codes, ...sections.map((s) => s.course_code)]);
      add(term, await getCourses(term, [...toFetch]));
    };
    hydrate().catch(console.error);
  }, [
    add,
    configurations,
    coursesByCode,
    proposals,
    sectionsById,
    term,
    wantedCodes,
    watched,
  ]);

  return { coursesByCode, sectionsById, remember };
}
