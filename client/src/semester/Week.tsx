/**
 * The week canvas: the active variant's sections as blocks, plus ghosts of
 * the course being browsed. While the advisor proposes schedules, the week
 * projects one at a time in their place, dashing the sections it would add,
 * until the user flips to another, keeps one, or discards them.
 *
 * Owns layout only: fitting the hour range to the content, splitting
 * overlapping blocks into lanes, and texturing blocks by section type. Ghost
 * state comes from the preview store; plan edits go to the caller.
 */

import React, { useMemo, useState } from 'react';
import { ChevronLeft, ChevronRight, Copy, Plus, X } from 'lucide-react';
import {
  WEEKDAYS,
  bySectionOrder,
  clashes,
  findOverlaps,
  isTimed,
  missingComponents,
  timedMeetings,
  totalUnits,
} from '../lib/schedule';
import type { TimedMeeting } from '../lib/schedule';
import { displayCode } from '../lib/degree';
import { formatHour, formatRange } from '../lib/time';
import { cycleProposal, setFocus, shownProposal, usePreview } from '../state/preview';
import type { Proposal } from '../state/preview';
import { showToast } from '../state/toast';
import { RatingPair } from '../ui/Glyphs';
import { hueFor, textureBackground } from '../ui/encoding';
import type { Course, ScheduleConfiguration, Section, Weekday } from '../types';
import styles from './Week.module.css';

/** USC charges overload tuition above this many units. */
const OVERLOAD_UNITS = 18;

/**
 * Properties for the week canvas.
 */
export interface WeekProps {
  readonly configurations: readonly ScheduleConfiguration[];
  readonly activeConfigId: string;
  /** Sections of the active variant that have resolved records. */
  readonly sections: readonly Section[];
  readonly sectionsById: ReadonlyMap<string, Section>;
  readonly coursesByCode: ReadonlyMap<string, Course>;
  readonly scheduledCourseIds: readonly string[];
  readonly onSelectVariant: (configId: string) => void;
  readonly onRenameVariant: (configId: string, name: string) => void;
  readonly onDeleteVariant: (config: ScheduleConfiguration) => void;
  readonly onDuplicateVariant: () => void;
  readonly onToggleSection: (section: Section, course: Course) => void;
  readonly onRemove: (section: Section) => void;
  readonly onFocusCourse: (course: Course) => void;
  readonly onKeepProposal: (proposal: Proposal) => void;
  readonly onDiscardProposal: () => void;
}

interface Lane {
  readonly lane: number;
  readonly lanes: number;
}

/** One timed meeting of a section: what the canvas draws. */
interface Block extends TimedMeeting {
  readonly key: string;
  readonly section: Section;
}

function blocksOf(sections: readonly Section[]): readonly Block[] {
  return sections.flatMap((section) =>
    timedMeetings(section).map((m, i) => ({
      ...m,
      key: `${section.id}:${i}`,
      section,
    })),
  );
}

/**
 * Assigns side-by-side lanes to overlapping blocks on one day. Each
 * cluster of transitively overlapping blocks shares one lane count.
 */
function layoutLanes(dayBlocks: readonly Block[]): ReadonlyMap<string, Lane> {
  const sorted = [...dayBlocks].sort((a, b) => a.start - b.start);
  const result = new Map<string, Lane>();
  let cluster: { readonly id: string; readonly lane: number }[] = [];
  let laneEnds: number[] = [];
  let clusterEnd = -1;
  const flush = (): void => {
    for (const item of cluster) {
      result.set(item.id, { lane: item.lane, lanes: laneEnds.length });
    }
    cluster = [];
    laneEnds = [];
  };
  for (const b of sorted) {
    if (b.start >= clusterEnd) {
      flush();
    }
    let lane = laneEnds.findIndex((end) => end <= b.start);
    if (lane === -1) {
      lane = laneEnds.length;
      laneEnds.push(b.end);
    } else {
      laneEnds[lane] = b.end;
    }
    cluster.push({ id: b.key, lane });
    clusterEnd = Math.max(clusterEnd, b.end);
  }
  flush();
  return result;
}

/**
 * Renders variant tabs, the time grid, blocks, ghosts, and the trays for
 * TBA sections and courses missing a component.
 */
export function Week(props: WeekProps): React.JSX.Element {
  const {
    sectionsById,
    coursesByCode,
    onToggleSection,
    onRemove,
    onFocusCourse,
    onKeepProposal,
    onDiscardProposal,
  } = props;
  const expanded = usePreview((p) => p.expanded);
  const focusId = usePreview((p) => p.focusId);
  const proposal = usePreview(shownProposal);
  const proposalCount = usePreview((p) => p.proposals.length);
  const shownIndex = usePreview((p) => p.shown);

  // The proposal, when present, replaces the active variant on screen.
  const proposed = useMemo(
    () =>
      proposal?.sectionIds
        .map((id) => sectionsById.get(id))
        .filter((s): s is Section => s !== undefined) ?? null,
    [proposal, sectionsById],
  );
  const sections = proposed ?? props.sections;
  const scheduledCourseIds = useMemo(
    () =>
      proposed ? [...new Set(proposed.map((s) => s.course_code))] : props.scheduledCourseIds,
    [proposed, props.scheduledCourseIds],
  );
  // Hues follow the real week first, so a course keeps its color inside a
  // proposal; courses new to the proposal take the following hues.
  const hueOrder = useMemo(
    () => [...new Set([...props.scheduledCourseIds, ...scheduledCourseIds])],
    [props.scheduledCourseIds, scheduledCourseIds],
  );

  // Sections already on the real week stay solid inside a proposal.
  const kept = useMemo(() => new Set(props.sections.map((s) => s.id)), [props.sections]);
  const timed = useMemo(() => sections.filter(isTimed), [sections]);
  const activeIds = useMemo(() => new Set(sections.map((s) => s.id)), [sections]);
  const ghosts = useMemo(
    () =>
      expanded && !proposal
        ? expanded.sections.filter((s) => isTimed(s) && !activeIds.has(s.id))
        : [],
    [expanded, proposal, activeIds],
  );
  const { overlapping, overlapCount } = useMemo(() => {
    const pairs = findOverlaps(timed);
    const ids = new Set<string>();
    for (const { a, b } of pairs) {
      ids.add(a.id);
      ids.add(b.id);
    }
    return { overlapping: ids, overlapCount: pairs.length };
  }, [timed]);

  const blocks = useMemo(() => blocksOf(timed), [timed]);
  const ghostBlocks = useMemo(() => blocksOf(ghosts), [ghosts]);
  const everything = [...blocks, ...ghostBlocks];
  const lo = Math.min(9, ...everything.map((b) => Math.floor(b.start / 60)));
  const hi = Math.max(17, ...everything.map((b) => Math.ceil(b.end / 60)));
  const span = (hi - lo) * 60;
  const pct = (minute: number): string => `${((minute - lo * 60) / span) * 100}%`;
  const days: readonly Weekday[] = everything.some((b) => b.days.includes('Sat'))
    ? [...WEEKDAYS, 'Sat']
    : WEEKDAYS;
  const hours = Array.from({ length: hi - lo }, (_, i) => lo + i);

  const units = totalUnits(sections, coursesByCode);
  const tba = sections.filter((s) => !isTimed(s));
  const incomplete = scheduledCourseIds.flatMap((id) => {
    const course = coursesByCode.get(id);
    if (!course) {
      return [];
    }
    const missing = missingComponents(
      course,
      sections.filter((s) => s.course_code === id),
    );
    return missing.length > 0 ? [{ course, missing }] : [];
  });

  return (
    <div className={styles.week}>
      <header className={styles.header}>
        <Variants {...props} proposalName={proposal?.name ?? null} />
        <span className={styles.stats}>
          <span className={units > OVERLOAD_UNITS ? styles.warn : undefined}>
            <span className={styles.num}>{units}</span> units
          </span>
          {overlapCount > 0 && (
            <span className={styles.danger}>
              {overlapCount} overlap{overlapCount === 1 ? '' : 's'}
            </span>
          )}
          {proposal && (
            <>
              {proposalCount > 1 && (
                <span className={styles.cycle}>
                  <button type="button" onClick={() => cycleProposal(-1)} aria-label="Previous option">
                    <ChevronLeft size={14} />
                  </button>
                  <span className={styles.num}>
                    {shownIndex + 1} of {proposalCount}
                  </span>
                  <button type="button" onClick={() => cycleProposal(1)} aria-label="Next option">
                    <ChevronRight size={14} />
                  </button>
                </span>
              )}
              <button type="button" className={styles.keep} onClick={() => onKeepProposal(proposal)}>
                Keep
              </button>
              <button type="button" className={styles.discard} onClick={onDiscardProposal}>
                Discard
              </button>
            </>
          )}
        </span>
      </header>

      <div className={styles.grid} style={{ gridTemplateColumns: `36px repeat(${days.length}, minmax(0, 1fr))` }}>
        <span />
        {days.map((d) => (
          <span key={d} className={styles.dayLabel}>
            {d}
          </span>
        ))}

        <div className={styles.axis}>
          {hours.map((h) => (
            <span key={h} className={styles.hour} style={{ top: pct(h * 60) }}>
              {formatHour(h)}
            </span>
          ))}
        </div>

        {days.map((day) => {
          const dayBlocks = blocks.filter((b) => b.days.includes(day));
          const lanes = layoutLanes(dayBlocks);
          // Ghosts share lanes among themselves so same-time options sit
          // side by side instead of hiding one another.
          const dayGhosts = ghostBlocks.filter((b) => b.days.includes(day));
          const ghostLanes = layoutLanes(dayGhosts);
          const flipPopover = day === 'Fri' || day === 'Sat';
          return (
            <div key={day} className={styles.column}>
              {hours.map((h) => (
                <span key={h} className={styles.rule} style={{ top: pct(h * 60) }} />
              ))}

              {dayBlocks.map((b) => {
                const s = b.section;
                const course = coursesByCode.get(s.course_code);
                const hue = hueFor(s.course_code, hueOrder);
                const lane = lanes.get(b.key) ?? { lane: 0, lanes: 1 };
                return (
                  <div
                    key={b.key}
                    className={`${styles.block} ${overlapping.has(s.id) ? styles.clash : ''} ${
                      proposal && !kept.has(s.id) ? styles.proposed : ''
                    }`}
                    style={{
                      top: pct(b.start),
                      height: `calc(${pct(b.end)} - ${pct(b.start)})`,
                      left: `${(lane.lane / lane.lanes) * 100}%`,
                      width: `${100 / lane.lanes}%`,
                    }}
                    // Focusable so keyboard users reach the popover's actions.
                    tabIndex={0}
                    onClick={(e) => {
                      // The popover's own buttons act on the section instead.
                      if (course && !(e.target as HTMLElement).closest('button')) {
                        onFocusCourse(course);
                      }
                    }}
                    aria-label={`${displayCode(s.course_code)} ${s.type}, ${b.days.join(' ')} ${formatRange(b.start, b.end)}`}
                  >
                    <div
                      className={styles.face}
                      style={{
                        background: textureBackground(s.type, hue.fill),
                        borderColor: hue.ink,
                        color: hue.ink,
                      }}
                    >
                      <span className={styles.code}>{displayCode(s.course_code)}</span>
                      <span className={styles.blockMeta}>
                        {formatRange(b.start, b.end)}
                        {s.type !== 'Lecture' && ` · ${s.type}`}
                      </span>
                    </div>
                    <Popover
                      section={s}
                      course={course}
                      flip={flipPopover}
                      onRemove={proposal ? undefined : () => onRemove(s)}
                    />
                  </div>
                );
              })}

              {expanded &&
                dayGhosts.map((b) => {
                    const g = b.section;
                    const hue = hueFor(g.course_code, hueOrder);
                    const bad = clashes(g, timed);
                    const lane = ghostLanes.get(b.key) ?? { lane: 0, lanes: 1 };
                    return (
                      <button
                        key={b.key}
                        type="button"
                        className={`${styles.ghost} ${bad ? styles.ghostBad : ''} ${
                          focusId === g.id ? styles.ghostFocus : ''
                        }`}
                        style={{
                          top: pct(b.start),
                          height: `calc(${pct(b.end)} - ${pct(b.start)})`,
                          left: `calc(${(lane.lane / lane.lanes) * 100}% + 2px)`,
                          width: `calc(${100 / lane.lanes}% - 4px)`,
                          color: bad ? undefined : hue.ink,
                          background: bad ? undefined : textureBackground(g.type, hue.fill),
                        }}
                        onMouseEnter={() => setFocus(g.id)}
                        onMouseLeave={() => setFocus(null)}
                        onClick={() => onToggleSection(g, expanded)}
                        aria-label={`Add ${g.course_code} ${g.type} ${b.days.join(' ')} ${formatRange(b.start, b.end)}`}
                      >
                        <span className={styles.blockMeta}>
                          {formatRange(b.start, b.end)}
                        </span>
                      </button>
                    );
                  })}
            </div>
          );
        })}

        {timed.length === 0 && ghosts.length === 0 && (
          <p className={styles.empty}>
            Type a course below, or ask for a schedule
          </p>
        )}
      </div>

      {(tba.length > 0 || incomplete.length > 0) && (
        <footer className={styles.trays}>
          {incomplete.map(({ course, missing }) => (
            <button
              key={course.code}
              type="button"
              className={styles.tray}
              onClick={() => onFocusCourse(course)}
            >
              <span className={styles.code}>{displayCode(course.code)}</span>
              needs a {missing.join(' and a ')}
            </button>
          ))}
          {[...tba].sort(bySectionOrder).map((s) => (
            <span key={s.id} className={styles.tray}>
              <span className={styles.code}>{displayCode(s.course_code)}</span>
              {s.type} · TBA
              {!proposal && (
                <button
                  type="button"
                  className={styles.trayRemove}
                  onClick={() => onRemove(s)}
                  aria-label={`Remove ${s.course_code} ${s.type}`}
                >
                  <X size={11} />
                </button>
              )}
            </span>
          ))}
        </footer>
      )}
    </div>
  );
}

function Variants(
  props: WeekProps & { readonly proposalName: string | null },
): React.JSX.Element {
  const {
    configurations,
    proposalName,
    onSelectVariant,
    onRenameVariant,
    onDeleteVariant,
    onDuplicateVariant,
  } = props;
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState('');
  // A shown proposal takes the selection away from the real variants.
  const activeConfigId = proposalName === null ? props.activeConfigId : null;

  const commit = (configId: string): void => {
    if (draft.trim()) {
      onRenameVariant(configId, draft.trim());
    }
    setEditing(null);
  };

  return (
    <div className={styles.variants} role="tablist" aria-label="Schedule variants">
      {configurations.map((c) =>
        editing === c.id ? (
          <input
            key={c.id}
            className={styles.rename}
            value={draft}
            autoFocus
            size={Math.max(2, draft.length)}
            onChange={(e) => setDraft(e.target.value)}
            onBlur={() => commit(c.id)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                commit(c.id);
              } else if (e.key === 'Escape') {
                setEditing(null);
              }
            }}
          />
        ) : (
          <span key={c.id} className={styles.variantWrap}>
            <button
              type="button"
              role="tab"
              aria-selected={c.id === activeConfigId}
              className={`${styles.variant} ${c.id === activeConfigId ? styles.variantOn : ''}`}
              onClick={() => onSelectVariant(c.id)}
              onDoubleClick={() => {
                setDraft(c.name);
                setEditing(c.id);
              }}
              title="Double-click to rename"
            >
              {c.name}
            </button>
            {configurations.length > 1 && (
              <button
                type="button"
                className={styles.variantDelete}
                onClick={() => onDeleteVariant(c)}
                aria-label={`Delete ${c.name}`}
              >
                <X size={9} />
              </button>
            )}
          </span>
        ),
      )}
      {proposalName !== null && (
        <span
          role="tab"
          aria-selected
          className={`${styles.variant} ${styles.variantProposed}`}
          title="Suggested by the advisor"
        >
          {proposalName}?
        </span>
      )}
      <button
        type="button"
        className={styles.duplicate}
        onClick={onDuplicateVariant}
        title="Duplicate this week"
        aria-label="Duplicate this week"
      >
        <Plus size={13} />
      </button>
    </div>
  );
}

function Popover({
  section,
  course,
  flip,
  onRemove,
}: {
  readonly section: Section;
  readonly course: Course | undefined;
  readonly flip: boolean;
  readonly onRemove: (() => void) | undefined;
}): React.JSX.Element {
  const rated = section.instructors.find((i) => i.rmp?.rating != null);
  const copy = (): void => {
    navigator.clipboard
      .writeText(section.id)
      .then(() => showToast(`Copied section ${section.id}`))
      .catch(console.error);
  };
  return (
    <div className={`${styles.popover} ${flip ? styles.popoverFlip : ''}`}>
      <p className={styles.popTitle}>{course?.title ?? section.course_code}</p>
      {timedMeetings(section).map((m, i) => (
        <p key={i} className={styles.popLine}>
          {i === 0 && `${section.type} · `}
          {m.days.join(' ')} {formatRange(m.start, m.end)}
        </p>
      ))}
      {section.instructors.length > 0 && (
        <p className={styles.popLine}>
          <span>{section.instructors.map((i) => i.name).join(', ')}</span>
          {rated?.rmp && (
            <RatingPair
              rating={rated.rmp.rating}
              difficulty={rated.rmp.difficulty}
              count={rated.rmp.num_ratings}
            />
          )}
        </p>
      )}
      {section.capacity > 0 && (
        <p className={styles.popLine}>
          {section.registered} / {section.capacity} seats
          {section.waitlisted > 0 && ` · ${section.waitlisted} waitlisted`}
        </p>
      )}
      {section.requires_d_clearance && (
        <p className={styles.popLine}>Needs D-clearance</p>
      )}
      <div className={styles.popActions}>
        <button type="button" className={styles.popButton} onClick={copy}>
          <Copy size={11} />
          {section.id}
        </button>
        {onRemove && (
          <button type="button" className={styles.popButton} onClick={onRemove}>
            Remove
          </button>
        )}
      </div>
    </div>
  );
}
