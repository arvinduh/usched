/**
 * Resolves the course and section records the user's plan points at.
 *
 * The persisted store keeps only IDs, and the catalog list holds only the
 * current search page, so neither can render the calendar or watched list on
 * its own. This hook keeps an in-memory cache of referenced courses beside
 * the catalog page and fetches any referenced ID it cannot resolve: on boot,
 * after another tab edits the plan, or when an advisor chip or proposal
 * names a section that was never on screen.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { getCourseDetail, getSections } from '../api/client';
import type { Course, Section } from '../types';
import { usePreview } from './preview';
import { useStore } from './store';

/**
 * Lookup tables for every course and section the client currently knows.
 */
export interface PlanCourses {
  readonly coursesById: ReadonlyMap<string, Course>;
  readonly sectionsById: ReadonlyMap<string, Section>;
  /** Pins a course so it outlives the catalog page it came from. */
  readonly remember: (course: Course) => void;
}

/**
 * Merges the catalog page with cached plan courses and hydrates misses,
 * including `wantedCourseIds` the caller is about to show (suggestions).
 */
export function usePlanCourses(
  catalog: readonly Course[],
  wantedCourseIds: readonly string[],
): PlanCourses {
  const configurations = useStore((s) => s.configurations);
  const watchedCourseIds = useStore((s) => s.watchedCourseIds);
  const proposal = usePreview((p) => p.proposal);

  const [cache, setCache] = useState<ReadonlyMap<string, Course>>(
    () => new Map(),
  );
  // IDs already requested once; a failed or deleted ID is never retried.
  const requested = useRef(new Set<string>());

  const coursesById = useMemo(() => {
    const map = new Map(cache);
    for (const course of catalog) {
      map.set(course.id, course);
    }
    return map;
  }, [cache, catalog]);

  const sectionsById = useMemo(() => {
    const map = new Map<string, Section>();
    for (const course of coursesById.values()) {
      for (const section of course.sections) {
        map.set(section.id, section);
      }
    }
    return map;
  }, [coursesById]);

  const remember = useCallback((course: Course): void => {
    setCache((prev) =>
      prev.has(course.id) ? prev : new Map(prev).set(course.id, course),
    );
  }, []);

  useEffect(() => {
    const unseen = (id: string, known: ReadonlyMap<string, unknown>) =>
      !known.has(id) && !requested.current.has(id);
    const sectionIds = [
      ...new Set([
        ...configurations.flatMap((c) => c.section_ids),
        ...(proposal?.sectionIds ?? []),
      ]),
    ].filter((id) => unseen(id, sectionsById));
    const courseIds = [...new Set([...watchedCourseIds, ...wantedCourseIds])].filter(
      (id) => unseen(id, coursesById),
    );
    if (sectionIds.length === 0 && courseIds.length === 0) {
      return;
    }
    for (const id of [...sectionIds, ...courseIds]) {
      requested.current.add(id);
    }

    const hydrate = async (): Promise<void> => {
      const sections = await getSections(sectionIds);
      const toFetch = new Set([
        ...courseIds,
        ...sections.map((s) => s.course_id),
      ]);
      const fetched = await Promise.all(
        [...toFetch].map((id) => getCourseDetail(id).catch(() => null)),
      );
      setCache((prev) => {
        const next = new Map(prev);
        for (const course of fetched) {
          if (course) {
            next.set(course.id, course);
          }
        }
        return next;
      });
    };
    hydrate().catch(console.error);
  }, [
    configurations,
    proposal,
    watchedCourseIds,
    wantedCourseIds,
    sectionsById,
    coursesById,
  ]);

  return { coursesById, sectionsById, remember };
}
