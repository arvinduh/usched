/**
 * The week canvas: the active variant's sections as blocks, plus ghosts of
 * the course being browsed. While the advisor proposes schedules, the week
 * projects one at a time in their place, dashing the sections it would add
 * and captioning the trade-off it wins, until the user flips to another,
 * keeps one, or discards them.
 *
 * Owns layout only: fitting the hour range to the content, splitting
 * overlapping blocks into lanes, and texturing blocks by section type. Ghost
 * state comes from the preview store; plan edits go to the caller.
 */

import React, { useMemo, useState } from 'react';
import { ChevronLeft, ChevronRight, Copy, Plus, X } from 'lucide-react';
import {
  bySectionOrder,
  clashes,
  findOverlaps,
  isTba,
  isTimed,
  missingComponents,
  packIntervals,
  timedMeetings,
  totalUnits,
} from './_schedule';
import type { Lane, TimedMeeting } from './_schedule';
import {
  DAYS_OF_WEEK,
  DEFAULT_END_HOUR,
  DEFAULT_START_HOUR,
  EXTENDED_DAYS_OF_WEEK,
  OVERLOAD_UNITS,
} from '../config';
import { displayCode } from '../degree/_degree';
import { formatHour, formatRange } from './_time';
import { cycleProposal, setFocus, shownProposal, usePreview } from '../state/preview';
import type { Proposal } from '../state/preview';
import { showToast } from '../state/toast';
import type { ScheduleConfiguration } from '../state/store';
import { ContextMenu } from '../ui/ContextMenu';
import { CountUp } from '../ui/CountUp';
import { RatingPair } from '../ui/Glyphs';
import { blockBackground, hueFor, textureBackground } from '../ui/encoding';
import type { components } from '../api/schema';
import styles from './Week.module.css';

/**
 * Properties for the week canvas.
 */
export interface WeekProps {
  readonly configurations: readonly ScheduleConfiguration[];
  readonly activeConfigId: string;
  /** Sections of the active variant that have resolved records. */
  readonly sections: readonly components['schemas']['Section'][];
  readonly sectionsById: ReadonlyMap<string, components['schemas']['Section']>;
  readonly coursesByCode: ReadonlyMap<string, components['schemas']['Course']>;
  readonly scheduledCourseIds: readonly string[];
  readonly onSelectVariant: (configId: string) => void;
  readonly onRenameVariant: (configId: string, name: string) => void;
  readonly onDeleteVariant: (config: ScheduleConfiguration) => void;
  /** Starts an empty variant. */
  readonly onNewVariant: () => void;
  readonly onDuplicateVariant: (configId: string) => void;
  readonly onToggleSection: (
    section: components['schemas']['Section'],
    course: components['schemas']['Course'],
  ) => void;
  readonly onRemove: (section: components['schemas']['Section']) => void;
  readonly onFocusCourse: (course: components['schemas']['Course']) => void;
  /** Shows a clicked block's other sections on the week, or hides them. */
  readonly onPickBlock: (course: components['schemas']['Course']) => void;
  /** Stops showing a block's other sections: a press on the empty week. */
  readonly onClearPick: () => void;
  readonly onKeepProposal: (proposal: Proposal) => void;
  readonly onDiscardProposal: () => void;
}

/** One timed meeting of a section: what the canvas draws. */
interface Block extends TimedMeeting {
  readonly key: string;
  readonly section: components['schemas']['Section'];
}

function blocksOf(sections: readonly components['schemas']['Section'][]): readonly Block[] {
  return sections.flatMap((section) =>
    timedMeetings(section).map((m, i) => ({
      ...m,
      key: `${section.id}:${i}`,
      section,
    })),
  );
}

/**
 * Assigns side-by-side lanes to overlapping blocks on one day.
 */
function layoutLanes(dayBlocks: readonly Block[]): ReadonlyMap<string, Lane> {
  return packIntervals(
    dayBlocks.map((b) => ({ id: b.key, start: b.start, end: b.end })),
  );
}

/**
 * Keys of a day's blocks that overlap another block that day. A section
 * whose Monday meeting clashes is not marked on its free Wednesday.
 */
function clashesOn(dayBlocks: readonly Block[]): ReadonlySet<string> {
  const keys = new Set<string>();
  for (const [i, a] of dayBlocks.entries()) {
    for (const b of dayBlocks.slice(i + 1)) {
      if (a.start < b.end && b.start < a.end) {
        keys.add(a.key);
        keys.add(b.key);
      }
    }
  }
  return keys;
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
    onPickBlock,
    onClearPick,
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
        .filter((s): s is components['schemas']['Section'] => s !== undefined) ?? null,
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
  const overlapCount = useMemo(() => findOverlaps(timed).length, [timed]);

  const blocks = useMemo(() => blocksOf(timed), [timed]);
  const ghostBlocks = useMemo(() => blocksOf(ghosts), [ghosts]);
  const everything = [...blocks, ...ghostBlocks];
  const lo = Math.min(DEFAULT_START_HOUR, ...everything.map((b) => Math.floor(b.start / 60)));
  const hi = Math.max(lo + 1, DEFAULT_END_HOUR, ...everything.map((b) => Math.ceil(b.end / 60)));
  const span = Math.max(60, (hi - lo) * 60);
  const pct = (minute: number): string => `${((minute - lo * 60) / span) * 100}%`;
  const days: readonly components['schemas']['Weekday'][] = everything.some((b) => b.days.includes('Sat'))
    ? EXTENDED_DAYS_OF_WEEK
    : DAYS_OF_WEEK;
  const hours = Array.from({ length: Math.max(1, hi - lo) }, (_, i) => lo + i);

  const units = totalUnits(sections, coursesByCode);
  const overload = units - OVERLOAD_UNITS;
  const tba = sections.filter(isTba);
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
          <span
            className={overload > 0 ? styles.warn : undefined}
            title={
              overload > 0
                ? `${overload} past the ${OVERLOAD_UNITS}-unit flat-tuition maximum; each extra unit costs extra`
                : undefined
            }
          >
            <span className={styles.num}>
              <CountUp value={units} />
            </span>{' '}
            units
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
      {proposal?.tradeoff && (
        <p className={styles.tradeoff} title={proposal.tradeoff}>
          {proposal.tradeoff}
        </p>
      )}

      <div
        className={styles.grid}
        style={{ gridTemplateColumns: `36px repeat(${days.length}, minmax(0, 1fr))` }}
        onClick={(e) => {
          if (!(e.target as HTMLElement).closest(`.${styles.block}, button`)) {
            onClearPick();
          }
        }}
      >
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
          const dayGhosts = ghostBlocks.filter((b) => b.days.includes(day));
          // Blocks and ghosts share lanes, so anything meeting at the same
          // time sits side by side; nothing is drawn over a chosen class.
          const lanes = layoutLanes([...dayBlocks, ...dayGhosts]);
          const clashing = clashesOn(dayBlocks);
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
                    className={`${styles.block} ${clashing.has(b.key) ? styles.clash : ''} ${
                      proposal && !kept.has(s.id) ? styles.proposed : ''
                    } ${focusId === s.id ? styles.blockFocus : ''} ${
                      expanded?.code === s.course_code ? styles.blockPicked : ''
                    }`}
                    style={{
                      top: pct(b.start),
                      height: `calc(${pct(b.end)} - ${pct(b.start)})`,
                      left: `${(lane.lane / lane.lanes) * 100}%`,
                      width: `${100 / lane.lanes}%`,
                    }}
                    // Focusable so keyboard users reach the popover's actions.
                    tabIndex={0}
                    // Pairs with the card: its row for this section lights up.
                    onMouseEnter={() => setFocus(s.id)}
                    onMouseLeave={() => setFocus(null)}
                    onClick={(e) => {
                      // The popover's own buttons act on the section instead.
                      if (course && !(e.target as HTMLElement).closest('button')) {
                        onPickBlock(course);
                      }
                    }}
                    aria-label={`${displayCode(s.course_code)} ${s.type}, ${b.days.join(' ')} ${formatRange(b.start, b.end)}`}
                  >
                    <div
                      className={styles.face}
                      style={{
                        background: blockBackground(s.type, hue),
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
                      note={
                        expanded?.code === s.course_code
                          ? 'Click to hide other sections'
                          : 'Click for other sections'
                      }
                    />
                  </div>
                );
              })}

              {expanded &&
                dayGhosts.map((b) => {
                    const g = b.section;
                    const hue = hueFor(g.course_code, hueOrder);
                    const bad = clashes(g, timed);
                    const lane = lanes.get(b.key) ?? { lane: 0, lanes: 1 };
                    // The slot holds the ghost and, beside it on hover, the same
                    // popover a chosen block shows, so a prospective section can
                    // be weighed before it is taken.
                    return (
                      <div
                        key={b.key}
                        className={styles.ghostSlot}
                        style={{
                          top: pct(b.start),
                          height: `calc(${pct(b.end)} - ${pct(b.start)})`,
                          left: `calc(${(lane.lane / lane.lanes) * 100}% + 2px)`,
                          width: `calc(${100 / lane.lanes}% - 4px)`,
                        }}
                        onMouseEnter={() => setFocus(g.id)}
                        onMouseLeave={() => setFocus(null)}
                      >
                        <button
                          type="button"
                          className={`${styles.ghost} ${bad ? styles.ghostBad : ''} ${
                            focusId === g.id ? styles.ghostFocus : ''
                          }`}
                          style={{
                            color: bad ? undefined : hue.ink,
                            background: bad ? undefined : textureBackground(g.type, hue.fill),
                          }}
                          onClick={() => onToggleSection(g, expanded)}
                          aria-label={`Add ${g.course_code} ${g.type} ${b.days.join(' ')} ${formatRange(b.start, b.end)}`}
                        >
                          <span className={styles.blockMeta}>
                            {formatRange(b.start, b.end)}
                          </span>
                        </button>
                        <Popover
                          section={g}
                          course={expanded}
                          flip={flipPopover}
                          onRemove={undefined}
                          note={bad ? 'Overlaps your week · click to take it anyway' : 'Click to take this section'}
                        />
                      </div>
                    );
                  })}
            </div>
          );
        })}

        {timed.length === 0 && ghosts.length === 0 && (
          <p className={styles.empty}>
            Type &gt; and a course below, or ask for a schedule
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
    onNewVariant,
    onDuplicateVariant,
  } = props;
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState('');
  const [menu, setMenu] = useState<{
    readonly x: number;
    readonly y: number;
    readonly config: ScheduleConfiguration;
  } | null>(null);
  const startRename = (c: ScheduleConfiguration): void => {
    setDraft(c.name);
    setEditing(c.id);
  };
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
              onDoubleClick={() => startRename(c)}
              onContextMenu={(e) => {
                e.preventDefault();
                setMenu({ x: e.clientX, y: e.clientY, config: c });
              }}
              title="Double-click to rename, right-click for more"
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
        onClick={onNewVariant}
        title="New empty week"
        aria-label="New empty week"
      >
        <Plus size={13} />
      </button>
      {menu && (
        <ContextMenu
          x={menu.x}
          y={menu.y}
          onClose={() => setMenu(null)}
          items={[
            {
              label: 'Duplicate',
              onSelect: () => onDuplicateVariant(menu.config.id),
            },
            { label: 'Rename', onSelect: () => startRename(menu.config) },
            ...(configurations.length > 1
              ? [
                  {
                    label: 'Delete',
                    onSelect: () => onDeleteVariant(menu.config),
                  },
                ]
              : []),
          ]}
        />
      )}
    </div>
  );
}

function Popover({
  section,
  course,
  flip,
  onRemove,
  note,
}: {
  readonly section: components['schemas']['Section'];
  readonly course: components['schemas']['Course'] | undefined;
  readonly flip: boolean;
  readonly onRemove: (() => void) | undefined;
  /** What a click on the block does, when that is not obvious. */
  readonly note?: string;
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
          {section.registered} / {section.capacity} seats taken
          {section.waitlisted > 0 && ` · ${section.waitlisted} waitlisted`}
        </p>
      )}
      {section.requires_d_clearance && (
        <p className={styles.popLine}>Needs D-clearance</p>
      )}
      {note && <p className={styles.popNote}>{note}</p>}
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
