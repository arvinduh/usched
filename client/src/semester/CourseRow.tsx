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
import { Bookmark, Check, CircleCheck, Lock } from 'lucide-react';
import { courseKey, displayCode } from '../lib/degree';
import {
  compatible,
  groupByType,
  missingComponents,
  timedMeetings,
  unmetPrereqs,
} from '../lib/schedule';
import { formatRange } from '../lib/time';
import { setFocus, toggleExpanded, usePreview } from '../state/preview';
import { ContextMenu } from '../ui/ContextMenu';
import { DayStrip, RatingPair, SeatMeter, TypeSwatch } from '../ui/Glyphs';
import { hueFor } from '../ui/encoding';
import type { Course, CourseRef, RequisiteGroup, Section, Units } from '../types';
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
  /** Marks the course completed (taken in a past term) or not. */
  readonly onToggleTaken: (course: Course) => void;
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

function refCode(ref: CourseRef): string {
  return displayCode(ref.resolved ?? ref.code);
}

function prereqLabel(groups: readonly RequisiteGroup[]): string {
  const group = (g: RequisiteGroup): string => {
    const options = g.options.map((o) => o.map(refCode).join(' and '));
    return g.required_count > 1
      ? `${g.required_count} of ${options.join(', ')}`
      : options.join(' or ');
  };
  return `Needs ${groups.map(group).join('; ')}`;
}

/** Units as a label, or null for the usual four. */
function unitsLabel(units: Units): string | null {
  if (units.min === units.max) {
    return units.min === 4 ? null : `${units.min}u`;
  }
  return `${units.min}–${units.max}u`;
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
    onToggleTaken,
    onToggleSection,
    otherVariants,
    onAddToVariant,
  } = props;
  const isExpanded = usePreview((p) => p.expanded?.code === course.code);
  const [menu, setMenu] = useState<MenuState | null>(null);
  const closeMenu = useCallback(() => setMenu(null), []);

  const live = course.sections.filter((s) => !s.is_cancelled);
  const chosen = live.filter((s) => activeSectionIds.has(s.id));
  const missing = chosen.length > 0 ? missingComponents(course, chosen) : [];
  const unmet = unmetPrereqs(course, completed);
  const hue = hueFor(course.code, scheduledCourseIds);
  const geLetters = course.ge.map((g) => g.replace('GE-', ''));
  const isTaken = completed.has(courseKey(course.code));
  const groups = groupByType(live);
  const chosenTypes = new Set(chosen.map((s) => s.type));
  // Link letters only matter when a course has more than one group.
  const showLinks = new Set(live.map((s) => s.link_code ?? '')).size > 1;
  const units = unitsLabel(course.units);

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
          <span className={styles.code}>{displayCode(course.code)}</span>
          <span className={`${styles.title} ${isTaken ? styles.titleTaken : ''}`}>
            {course.title}
          </span>
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
            <span className={styles.meta} title={course.ge.join(', ')}>
              {geLetters.join('')}
            </span>
          )}
          {units && <span className={styles.meta}>{units}</span>}
          {unmet.length > 0 && (
            <span className={styles.lock} title={prereqLabel(unmet)}>
              <Lock size={11} aria-label={prereqLabel(unmet)} />
            </span>
          )}
        </button>
        <button
          type="button"
          className={`${styles.save} ${isTaken ? styles.saved : ''}`}
          onClick={() => onToggleTaken(course)}
          aria-pressed={isTaken}
          aria-label={
            isTaken
              ? `Unmark ${course.code} as taken`
              : `Mark ${course.code} as taken`
          }
          title={isTaken ? 'Taken' : 'Mark as taken'}
        >
          <CircleCheck size={13} />
        </button>
        <button
          type="button"
          className={`${styles.save} ${isSaved ? styles.saved : ''}`}
          onClick={() => onToggleSave(course)}
          aria-pressed={isSaved}
          aria-label={isSaved ? `Unsave ${course.code}` : `Save ${course.code}`}
        >
          <Bookmark size={13} fill={isSaved ? 'currentColor' : 'none'} />
        </button>
      </div>

      {isExpanded && (
        <div className={styles.body}>
          {course.description && (
            <p className={styles.description}>{course.description}</p>
          )}
          {groups.length > 1 && (
            <p className={styles.together}>
              <span className={styles.togetherLabel}>Take together</span>
              {groups.map((g, i) => (
                <React.Fragment key={g.type}>
                  {i > 0 && <span className={styles.plus}>+</span>}
                  <span
                    className={`${styles.part} ${chosenTypes.has(g.type) ? styles.partDone : ''}`}
                  >
                    <TypeSwatch sectionType={g.type} ink={hue.ink} />
                    {g.type}
                    {chosenTypes.has(g.type) && <Check size={11} />}
                  </span>
                </React.Fragment>
              ))}
            </p>
          )}
          <div onMouseLeave={() => setFocus(null)}>
            {groups.map((g) => (
              <section key={g.type} className={styles.group}>
                <header className={styles.groupHead}>
                  <TypeSwatch sectionType={g.type} ink={hue.ink} />
                  <span className={styles.groupName}>{g.type}</span>
                  <span className={styles.groupRule}>
                    {g.sections.length > 1 ? 'choose one' : 'one option'}
                  </span>
                  {chosenTypes.has(g.type) ? (
                    <span className={styles.groupDone} style={{ color: hue.ink }}>
                      <Check size={12} />
                    </span>
                  ) : (
                    chosen.length > 0 && <span className={styles.groupNeeded}>needed</span>
                  )}
                </header>
                <div className={styles.sections}>
                  {g.sections.map((section) => (
                    <SectionRow
                      key={section.id}
                      section={section}
                      ink={hue.ink}
                      fill={hue.fill}
                      isChosen={activeSectionIds.has(section.id)}
                      link={showLinks ? section.link_code : null}
                      isOffGroup={
                        chosen.length > 0 &&
                        !chosen.every((c) => compatible(c, section))
                      }
                      onToggle={() => onToggleSection(section, course)}
                      onMenu={(x, y) => setMenu({ x, y, section })}
                    />
                  ))}
                </div>
              </section>
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
  link,
  isOffGroup,
  onToggle,
  onMenu,
}: {
  readonly section: Section;
  readonly ink: string;
  readonly fill: string;
  readonly isChosen: boolean;
  /** Link letter to show, or null when the course has one group. */
  readonly link: string | null;
  /** Belongs to another link group than the chosen sections. */
  readonly isOffGroup: boolean;
  readonly onToggle: () => void;
  readonly onMenu: (x: number, y: number) => void;
}): React.JSX.Element {
  const [instructor, ...coTeachers] = section.instructors;
  const rated = section.instructors.find((i) => i.rmp?.rating != null)?.rmp;
  const meetings = timedMeetings(section);
  return (
    <button
      type="button"
      className={`${styles.section} ${isOffGroup ? styles.offGroup : ''}`}
      title={isOffGroup ? 'Choosing this switches to its group' : undefined}
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
      <span
        className={`${styles.radio} ${isChosen ? styles.radioOn : ''}`}
        style={{ color: ink }}
        aria-hidden="true"
      />
      {meetings.length > 0 ? (
        <span className={styles.meetings}>
          {meetings.map((m, i) => (
            <span key={i} className={styles.meeting}>
              <DayStrip days={m.days} />
              <span className={styles.time}>{formatRange(m.start, m.end)}</span>
            </span>
          ))}
        </span>
      ) : (
        <span className={styles.tba}>TBA</span>
      )}
      <span className={styles.badges}>
        {link && (
          <span className={styles.badge} title={`Group ${link}`}>
            {link}
          </span>
        )}
        {section.requires_d_clearance && (
          <span
            className={styles.badge}
            title="Needs departmental clearance (D-clearance)"
          >
            D
          </span>
        )}
      </span>
      <span className={instructor ? styles.instructor : styles.tba}>
        {instructor?.name ?? 'Staff'}
        {coTeachers.length > 0 && ` +${coTeachers.length}`}
      </span>
      <span className={styles.stats}>
        {rated && (
          <RatingPair
            rating={rated.rating}
            difficulty={rated.difficulty}
            count={rated.num_ratings}
          />
        )}
        <SeatMeter
          enrolled={section.registered}
          capacity={section.capacity}
          waitlist={section.waitlisted}
        />
      </span>
    </button>
  );
}
