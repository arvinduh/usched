/**
 * A course as a line in any list, and as the card it opens into.
 *
 * Every place a course appears (search results, saved courses, the degree
 * tree, advisor replies, the week) opens the same `CourseCard`: what the
 * course is, whether the student can take it, the three things they can do
 * with it (take a section this term, save it, mark it taken), and its
 * sections, which the week ghosts while the card is open. `CourseLine` is
 * the compact form with the same save and taken toggles. Plan edits go to
 * the caller; lines carry `data-nav` hooks for arrow-key navigation.
 */

import React, { useCallback, useState } from 'react';
import { ArrowLeft, Bookmark, Check, CircleCheck, Lock } from 'lucide-react';
import { courseKey, displayCode } from '../lib/degree';
import {
  compatible,
  groupByType,
  missingComponents,
  timedMeetings,
  unmetPrereqs,
} from '../lib/schedule';
import { formatRange } from '../lib/time';
import { setFocus } from '../state/preview';
import { ContextMenu } from '../ui/ContextMenu';
import { DayStrip, RatingPair, SeatMeter, TypeSwatch } from '../ui/Glyphs';
import { hueFor } from '../ui/encoding';
import type { Course, CourseRef, RequisiteGroup, Section, Units } from '../types';
import styles from './Course.module.css';

/**
 * What a line or card needs to know about the student's plan.
 */
export interface CoursePlan {
  readonly completed: ReadonlySet<string>;
  readonly watched: ReadonlySet<string>;
  readonly activeSectionIds: ReadonlySet<string>;
  /** Courses on the active week in hue order. */
  readonly scheduledCourseIds: readonly string[];
  readonly onToggleSave: (code: string) => void;
  /** Marks the course completed (taken in a past term) or not. */
  readonly onToggleTaken: (code: string) => void;
}

/**
 * Properties for a course line.
 */
export interface CourseLineProps {
  readonly course: Course;
  readonly plan: CoursePlan;
  readonly onOpen: (course: Course) => void;
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
 * The taken and saved toggles every course carries, line or card.
 */
function Toggles({
  code,
  plan,
  labeled,
}: {
  readonly code: string;
  readonly plan: CoursePlan;
  /** Cards spell the toggles out; lines show icons on hover. */
  readonly labeled: boolean;
}): React.JSX.Element {
  const isTaken = plan.completed.has(courseKey(code));
  const isSaved = plan.watched.has(code);
  const cls = labeled ? styles.toggle : styles.save;
  return (
    <>
      <button
        type="button"
        className={`${cls} ${isTaken ? styles.saved : ''}`}
        onClick={() => plan.onToggleTaken(code)}
        aria-pressed={isTaken}
        aria-label={labeled ? undefined : isTaken ? `Unmark ${code} as taken` : `Mark ${code} as taken`}
        title={labeled ? undefined : isTaken ? 'Taken' : 'Mark as taken'}
      >
        <CircleCheck size={13} />
        {labeled && (isTaken ? 'Taken' : 'Mark taken')}
      </button>
      <button
        type="button"
        className={`${cls} ${isSaved ? styles.saved : ''}`}
        onClick={() => plan.onToggleSave(code)}
        aria-pressed={isSaved}
        aria-label={labeled ? undefined : isSaved ? `Unsave ${code}` : `Save ${code}`}
      >
        <Bookmark size={13} fill={isSaved ? 'currentColor' : 'none'} />
        {labeled && (isSaved ? 'Saved' : 'Save')}
      </button>
    </>
  );
}

/**
 * Renders one course as a line that opens its card.
 */
export function CourseLine({ course, plan, onOpen }: CourseLineProps): React.JSX.Element {
  const chosen = course.sections.filter((s) => plan.activeSectionIds.has(s.id));
  const missing = chosen.length > 0 ? missingComponents(course, chosen) : [];
  const unmet = unmetPrereqs(course, plan.completed);
  const hue = hueFor(course.code, plan.scheduledCourseIds);
  const geLetters = course.ge.map((g) => g.replace('GE-', ''));
  const isTaken = plan.completed.has(courseKey(course.code));
  const units = unitsLabel(course.units);

  return (
    <div className={styles.head} data-course>
      <button
        type="button"
        data-nav="course"
        className={styles.identity}
        onClick={() => onOpen(course)}
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
      <Toggles code={course.code} plan={plan} labeled={false} />
    </div>
  );
}

/**
 * Properties for a course card.
 */
export interface CourseCardProps {
  /** The course as this term offers it, or null when it is not offered. */
  readonly course: Course | null;
  readonly code: string;
  /** A title for a course this term lacks, when the opener knew one. */
  readonly title: string | null;
  readonly termName: string;
  readonly plan: CoursePlan;
  readonly onToggleSection: (section: Section, course: Course) => void;
  /** Variants other than the active one, for "Add to" in the menu. */
  readonly otherVariants: readonly { readonly id: string; readonly name: string }[];
  /** Adds to the given variant, or to a new one when `configId` is null. */
  readonly onAddToVariant: (
    section: Section,
    course: Course,
    configId: string | null,
  ) => void;
  readonly onClose: () => void;
}

/**
 * Renders the card: identity, status and toggles, prerequisites, the
 * description, and the sections to choose from.
 */
export function CourseCard(props: CourseCardProps): React.JSX.Element {
  const { course, code, plan, onClose } = props;
  const [menu, setMenu] = useState<MenuState | null>(null);
  const closeMenu = useCallback(() => setMenu(null), []);

  const header = (
    <header className={styles.cardHead}>
      <button type="button" className={styles.back} onClick={onClose} aria-label="Close">
        <ArrowLeft size={14} />
      </button>
      <span className={styles.cardCode}>{displayCode(course?.code ?? code)}</span>
      {course && unitsLabel(course.units) !== null && (
        <span className={styles.meta}>{unitsLabel(course.units)}</span>
      )}
      {course && course.ge.length > 0 && (
        <span className={styles.meta}>{course.ge.join(' ')}</span>
      )}
    </header>
  );

  if (!course) {
    return (
      <div className={styles.card}>
        {header}
        {props.title && <h2 className={styles.cardTitle}>{props.title}</h2>}
        <div className={styles.cardActions}>
          <Toggles code={code} plan={plan} labeled />
        </div>
        <p className={styles.cardNote}>Not offered in {props.termName}.</p>
      </div>
    );
  }

  const { activeSectionIds, scheduledCourseIds, completed } = plan;
  const live = course.sections.filter((s) => !s.is_cancelled);
  const chosen = live.filter((s) => activeSectionIds.has(s.id));
  const missing = chosen.length > 0 ? missingComponents(course, chosen) : [];
  const unmet = unmetPrereqs(course, completed);
  const hue = hueFor(course.code, scheduledCourseIds);
  const groups = groupByType(live);
  const chosenTypes = new Set(chosen.map((s) => s.type));
  // Link letters only matter when a course has more than one group.
  const showLinks = new Set(live.map((s) => s.link_code ?? '')).size > 1;
  const status =
    chosen.length === 0
      ? 'Pick a section here or on the week.'
      : missing.length > 0
        ? `On your week; still needs a ${missing.join(' and a ')}.`
        : 'On your week.';

  return (
    <div className={styles.card}>
      {header}
      <h2 className={styles.cardTitle}>{course.title}</h2>
      <div className={styles.cardActions}>
        <Toggles code={course.code} plan={plan} labeled />
      </div>
      <p className={styles.cardNote}>
        {unmet.length > 0 && (
          <span className={styles.cardWarn}>
            <Lock size={11} /> {prereqLabel(unmet)}.{' '}
          </span>
        )}
        {status}
      </p>
      {course.description && <p className={styles.description}>{course.description}</p>}
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
                    chosen.length > 0 && !chosen.every((c) => compatible(c, section))
                  }
                  onToggle={() => props.onToggleSection(section, course)}
                  onMenu={(x, y) => setMenu({ x, y, section })}
                />
              ))}
            </div>
          </section>
        ))}
      </div>

      {menu && (
        <ContextMenu
          x={menu.x}
          y={menu.y}
          onClose={closeMenu}
          items={[
            ...props.otherVariants.map((v) => ({
              label: `Add to ${v.name}`,
              onSelect: () => props.onAddToVariant(menu.section, course, v.id),
            })),
            {
              label: 'Add to a new variant',
              onSelect: () => props.onAddToVariant(menu.section, course, null),
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
