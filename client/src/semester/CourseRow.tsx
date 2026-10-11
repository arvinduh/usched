/**
 * One course in the Library: a single identity line that expands into its
 * sections.
 *
 * Expanding a course publishes it to the preview store, which ghosts every
 * section onto the week; hovering a section emphasizes its ghost. Choosing a
 * section is delegated to the caller, as is adding one to another variant
 * from the right-click menu. Rows carry `data-nav` hooks for the Library's
 * arrow-key navigation.
 */

import React, { useCallback, useState } from 'react';
import { Bookmark, Lock } from 'lucide-react';
import { displayCode } from '../lib/degree';
import { bySectionOrder, isTimed, missingComponents, unmetPrereqs } from '../lib/schedule';
import { formatRange } from '../lib/time';
import { setFocus, toggleExpanded, usePreview } from '../state/preview';
import { ContextMenu } from '../ui/ContextMenu';
import { DayStrip, RatingPair, SeatMeter, TypeSwatch } from '../ui/Glyphs';
import { hueFor } from '../ui/encoding';
import type { Course, Section } from '../types';
import styles from './CourseRow.module.css';

/**
 * Properties for a Library course row.
 */
export interface CourseRowProps {
  readonly course: Course;
  readonly isSaved: boolean;
  readonly completed: ReadonlySet<string>;
  readonly activeSectionIds: ReadonlySet<string>;
  /** Courses on the active week in hue order. */
  readonly scheduledCourseIds: readonly string[];
  readonly onToggleSave: (course: Course) => void;
  readonly onToggleSection: (section: Section, course: Course) => void;
  /** Variants other than the active one, for "Add to" in the menu. */
  readonly otherVariants: readonly { readonly id: string; readonly name: string }[];
  /** Adds to the given variant, or to a new one when `configId` is null. */
  readonly onAddToVariant: (
    section: Section,
    course: Course,
    configId: string | null,
  ) => void;
}

interface MenuState {
  readonly x: number;
  readonly y: number;
  readonly section: Section;
}

function prereqLabel(groups: readonly (readonly string[])[]): string {
  return `Needs ${groups.map((g) => g.join(' or ')).join(', ')}`;
}

/**
 * Renders the collapsed identity line and, when expanded, the sections.
 */
export function CourseRow(props: CourseRowProps): React.JSX.Element {
  const {
    course,
    isSaved,
    completed,
    activeSectionIds,
    scheduledCourseIds,
    onToggleSave,
    onToggleSection,
    otherVariants,
    onAddToVariant,
  } = props;
  const isExpanded = usePreview((p) => p.expanded?.id === course.id);
  const [menu, setMenu] = useState<MenuState | null>(null);
  const closeMenu = useCallback(() => setMenu(null), []);

  const chosen = course.sections.filter((s) => activeSectionIds.has(s.id));
  const missing = chosen.length > 0 ? missingComponents(course, chosen) : [];
  const unmet = unmetPrereqs(course, completed);
  const hue = hueFor(course.id, scheduledCourseIds);
  const geLetters = (course.ge_categories ?? []).map((g) => g.replace('GE-', ''));

  return (
    <div className={`${styles.course} ${isExpanded ? styles.open : ''}`} data-course>
      <div className={styles.head}>
        <button
          type="button"
          data-nav="course"
          className={styles.identity}
          onClick={() => toggleExpanded(course)}
          aria-expanded={isExpanded}
        >
          <span className={styles.code}>{displayCode(course.id)}</span>
          <span className={styles.title}>{course.title}</span>
          {chosen.length > 0 && (
            <span
              className={styles.ring}
              style={{ color: hue.ink }}
              title={
                missing.length > 0
                  ? `Still needs a ${missing.join(' and a ')}`
                  : 'All sections chosen'
              }
            >
              {missing.length > 0 ? '◐' : '●'}
            </span>
          )}
          {geLetters.length > 0 && (
            <span className={styles.meta} title={course.ge_categories?.join(', ')}>
              {geLetters.join('')}
            </span>
          )}
          {course.units !== 4 && (
            <span className={styles.meta}>{course.units}u</span>
          )}
          {unmet.length > 0 && (
            <span className={styles.lock} title={prereqLabel(unmet)}>
              <Lock size={11} aria-label={prereqLabel(unmet)} />
            </span>
          )}
        </button>
        <button
          type="button"
          className={`${styles.save} ${isSaved ? styles.saved : ''}`}
          onClick={() => onToggleSave(course)}
          aria-pressed={isSaved}
          aria-label={isSaved ? `Unsave ${course.id}` : `Save ${course.id}`}
        >
          <Bookmark size={13} fill={isSaved ? 'currentColor' : 'none'} />
        </button>
      </div>

      {isExpanded && (
        <div className={styles.body}>
          {course.description && (
            <p className={styles.description}>{course.description}</p>
          )}
          <div
            className={styles.sections}
            onMouseLeave={() => setFocus(null)}
          >
            {[...course.sections].sort(bySectionOrder).map((section) => (
              <SectionRow
                key={section.id}
                section={section}
                ink={hue.ink}
                fill={hue.fill}
                isChosen={activeSectionIds.has(section.id)}
                onToggle={() => onToggleSection(section, course)}
                onMenu={(x, y) => setMenu({ x, y, section })}
              />
            ))}
          </div>
        </div>
      )}

      {menu && (
        <ContextMenu
          x={menu.x}
          y={menu.y}
          onClose={closeMenu}
          items={[
            ...otherVariants.map((v) => ({
              label: `Add to ${v.name}`,
              onSelect: () => onAddToVariant(menu.section, course, v.id),
            })),
            {
              label: 'Add to a new variant',
              onSelect: () => onAddToVariant(menu.section, course, null),
            },
          ]}
        />
      )}
    </div>
  );
}

function SectionRow({
  section,
  ink,
  fill,
  isChosen,
  onToggle,
  onMenu,
}: {
  readonly section: Section;
  readonly ink: string;
  readonly fill: string;
  readonly isChosen: boolean;
  readonly onToggle: () => void;
  readonly onMenu: (x: number, y: number) => void;
}): React.JSX.Element {
  const instructor = section.instructor;
  return (
    <button
      type="button"
      className={styles.section}
      style={isChosen ? { background: fill } : undefined}
      aria-pressed={isChosen}
      data-nav="section"
      onClick={onToggle}
      onContextMenu={(e) => {
        e.preventDefault();
        onMenu(e.clientX, e.clientY);
      }}
      onMouseEnter={() => setFocus(section.id)}
      onFocus={() => setFocus(section.id)}
    >
      <TypeSwatch sectionType={section.section_type} ink={ink} />
      {isTimed(section) ? (
        <>
          <DayStrip days={section.days} />
          <span className={styles.time}>
            {formatRange(section.start_minute, section.end_minute)}
          </span>
        </>
      ) : (
        <span className={styles.tba}>TBA</span>
      )}
      <span className={instructor ? styles.instructor : styles.tba}>
        {instructor?.name ?? 'Staff'}
      </span>
      {instructor && (
        <RatingPair
          rating={instructor.rmp_rating}
          difficulty={instructor.rmp_difficulty}
          count={instructor.rmp_num_ratings}
        />
      )}
      <SeatMeter
        enrolled={section.enrolled}
        capacity={section.capacity}
        waitlist={section.waitlist}
      />
    </button>
  );
}
