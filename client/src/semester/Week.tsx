/**
 * The week canvas: the active variant's sections as blocks, plus ghosts of
 * the course being browsed. While the advisor proposes a schedule, the week
 * shows that proposal instead, dashed, until the user keeps or discards it.
 *
 * Owns layout only: fitting the hour range to the content, splitting
 * overlapping blocks into lanes, and texturing blocks by section type. Ghost
 * state comes from the preview store; plan edits go to the caller.
 */

import React, { useMemo, useState } from 'react';
import { Copy, Plus, X } from 'lucide-react';
import {
  WEEKDAYS,
  bySectionOrder,
  clashes,
  findOverlaps,
  isTimed,
  missingComponents,
  totalUnits,
} from '../lib/schedule';
import { displayCode } from '../lib/degree';
import { formatHour, formatRange } from '../lib/time';
import { setFocus, usePreview } from '../state/preview';
import type { Proposal } from '../state/preview';
import { showToast } from '../state/toast';
import { RatingPair } from '../ui/Glyphs';
import { hueFor, textureBackground } from '../ui/encoding';
import type { Course, ScheduleConfiguration, Section } from '../types';
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
  readonly coursesById: ReadonlyMap<string, Course>;
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

/**
 * Assigns side-by-side lanes to overlapping sections on one day. Each
 * cluster of transitively overlapping sections shares one lane count.
 */
function layoutLanes(daySections: readonly Section[]): ReadonlyMap<string, Lane> {
  const sorted = [...daySections].sort((a, b) => a.start_minute - b.start_minute);
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
  for (const s of sorted) {
    if (s.start_minute >= clusterEnd) {
      flush();
    }
    let lane = laneEnds.findIndex((end) => end <= s.start_minute);
    if (lane === -1) {
      lane = laneEnds.length;
      laneEnds.push(s.end_minute);
    } else {
      laneEnds[lane] = s.end_minute;
    }
    cluster.push({ id: s.id, lane });
    clusterEnd = Math.max(clusterEnd, s.end_minute);
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
    coursesById,
    onToggleSection,
    onRemove,
    onFocusCourse,
    onKeepProposal,
    onDiscardProposal,
  } = props;
  const expanded = usePreview((p) => p.expanded);
  const focusId = usePreview((p) => p.focusId);
  const proposal = usePreview((p) => p.proposal);

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
      proposed ? [...new Set(proposed.map((s) => s.course_id))] : props.scheduledCourseIds,
    [proposed, props.scheduledCourseIds],
  );
  // Hues follow the real week first, so a course keeps its color inside a
  // proposal; courses new to the proposal take the following hues.
  const hueOrder = useMemo(
    () => [...new Set([...props.scheduledCourseIds, ...scheduledCourseIds])],
    [props.scheduledCourseIds, scheduledCourseIds],
  );

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

  const everything = [...timed, ...ghosts];
  const lo = Math.min(9, ...everything.map((s) => Math.floor(s.start_minute / 60)));
  const hi = Math.max(17, ...everything.map((s) => Math.ceil(s.end_minute / 60)));
  const span = (hi - lo) * 60;
  const pct = (minute: number): string => `${((minute - lo * 60) / span) * 100}%`;
  const days: readonly string[] = everything.some((s) => s.days.includes('Sat'))
    ? [...WEEKDAYS, 'Sat']
    : WEEKDAYS;
  const hours = Array.from({ length: hi - lo }, (_, i) => lo + i);

  const units = totalUnits(sections, coursesById);
  const tba = sections.filter((s) => !isTimed(s));
  const incomplete = scheduledCourseIds.flatMap((id) => {
    const course = coursesById.get(id);
    if (!course) {
      return [];
    }
    const missing = missingComponents(
      course,
      sections.filter((s) => s.course_id === id),
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
          const dayBlocks = timed.filter((s) => s.days.includes(day));
          const lanes = layoutLanes(dayBlocks);
          const flipPopover = day === 'Fri' || day === 'Sat';
          return (
            <div key={day} className={styles.column}>
              {hours.map((h) => (
                <span key={h} className={styles.rule} style={{ top: pct(h * 60) }} />
              ))}

              {dayBlocks.map((s) => {
                const course = coursesById.get(s.course_id);
                const hue = hueFor(s.course_id, hueOrder);
                const lane = lanes.get(s.id) ?? { lane: 0, lanes: 1 };
                return (
                  <div
                    key={s.id}
                    className={`${styles.block} ${overlapping.has(s.id) ? styles.clash : ''} ${
                      proposal ? styles.proposed : ''
                    }`}
                    style={{
                      top: pct(s.start_minute),
                      height: `calc(${pct(s.end_minute)} - ${pct(s.start_minute)})`,
                      left: `${(lane.lane / lane.lanes) * 100}%`,
                      width: `${100 / lane.lanes}%`,
                    }}
                    // Focusable so keyboard users reach the popover's actions.
                    tabIndex={0}
                    aria-label={`${displayCode(s.course_id)} ${s.section_type}, ${s.days.join(' ')} ${formatRange(s.start_minute, s.end_minute)}`}
                  >
                    <div
                      className={styles.face}
                      style={{
                        background: textureBackground(s.section_type, hue.fill),
                        borderColor: hue.ink,
                        color: hue.ink,
                      }}
                    >
                      <span className={styles.code}>{displayCode(s.course_id)}</span>
                      <span className={styles.blockMeta}>
                        {formatRange(s.start_minute, s.end_minute)}
                        {s.section_type !== 'Lecture' && ` · ${s.section_type}`}
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
                ghosts
                  .filter((g) => g.days.includes(day))
                  .map((g) => {
                    const hue = hueFor(g.course_id, hueOrder);
                    const bad = clashes(g, timed);
                    return (
                      <button
                        key={g.id}
                        type="button"
                        className={`${styles.ghost} ${bad ? styles.ghostBad : ''} ${
                          focusId === g.id ? styles.ghostFocus : ''
                        }`}
                        style={{
                          top: pct(g.start_minute),
                          height: `calc(${pct(g.end_minute)} - ${pct(g.start_minute)})`,
                          color: bad ? undefined : hue.ink,
                          background: bad ? undefined : textureBackground(g.section_type, hue.fill),
                        }}
                        onMouseEnter={() => setFocus(g.id)}
                        onMouseLeave={() => setFocus(null)}
                        onClick={() => onToggleSection(g, expanded)}
                        aria-label={`Add ${g.course_id} ${g.section_type} ${g.days.join(' ')} ${formatRange(g.start_minute, g.end_minute)}`}
                      >
                        <span className={styles.blockMeta}>
                          {formatRange(g.start_minute, g.end_minute)}
                        </span>
                      </button>
                    );
                  })}
            </div>
          );
        })}

        {timed.length === 0 && ghosts.length === 0 && (
          <p className={styles.empty}>
            Press <kbd>/</kbd> to find a course
          </p>
        )}
      </div>

      {(tba.length > 0 || incomplete.length > 0) && (
        <footer className={styles.trays}>
          {incomplete.map(({ course, missing }) => (
            <button
              key={course.id}
              type="button"
              className={styles.tray}
              onClick={() => onFocusCourse(course)}
            >
              <span className={styles.code}>{displayCode(course.id)}</span>
              needs a {missing.join(' and a ')}
            </button>
          ))}
          {[...tba].sort(bySectionOrder).map((s) => (
            <span key={s.id} className={styles.tray}>
              <span className={styles.code}>{displayCode(s.course_id)}</span>
              {s.section_type} · TBA
              {!proposal && (
                <button
                  type="button"
                  className={styles.trayRemove}
                  onClick={() => onRemove(s)}
                  aria-label={`Remove ${s.course_id} ${s.section_type}`}
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
  const instructor = section.instructor;
  const copy = (): void => {
    navigator.clipboard
      .writeText(section.id)
      .then(() => showToast(`Copied section ${section.id}`))
      .catch(console.error);
  };
  return (
    <div className={`${styles.popover} ${flip ? styles.popoverFlip : ''}`}>
      <p className={styles.popTitle}>{course?.title ?? section.course_id}</p>
      <p className={styles.popLine}>
        {section.section_type} · {section.days.join(' ')}{' '}
        {formatRange(section.start_minute, section.end_minute)}
      </p>
      {instructor && (
        <p className={styles.popLine}>
          <span>{instructor.name}</span>
          <RatingPair
            rating={instructor.rmp_rating}
            difficulty={instructor.rmp_difficulty}
            count={instructor.rmp_num_ratings}
          />
        </p>
      )}
      {section.capacity > 0 && (
        <p className={styles.popLine}>
          {section.enrolled} / {section.capacity} seats
          {section.waitlist > 0 && ` · ${section.waitlist} waitlisted`}
        </p>
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
