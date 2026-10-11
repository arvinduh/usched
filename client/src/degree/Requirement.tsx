/**
 * One degree requirement category rendered in the chip grammar.
 *
 * Separate chips mean "take all"; chips fused into one capsule mean "take
 * any"; a dashed "+N units" slot means open units of anything that counts.
 * Chip fill encodes state (done, planned this term, available, locked).
 * Plan edits and navigation are delegated to the caller.
 */

import React from 'react';
import { ArrowUpRight, Check, ExternalLink, Lock } from 'lucide-react';
import { getUscCourseUrl } from '../api/client';
import { categoryShape, courseKey, displayCode } from '../lib/degree';
import type { DegreeCategory, PrereqNode } from '../types';
import styles from './Degree.module.css';

/**
 * Shared lookups and callbacks for every chip on the page.
 */
export interface ChipContext {
  /** Prerequisite nodes keyed by `courseKey`. */
  readonly nodes: ReadonlyMap<string, PrereqNode>;
  readonly completed: ReadonlySet<string>;
  readonly planned: ReadonlySet<string>;
  /** Courses blocking the chip under the pointer, keyed by `courseKey`. */
  readonly highlighted: ReadonlySet<string>;
  readonly onHover: (key: string | null) => void;
  readonly onToggle: (courseId: string) => void;
  readonly onFind: (courseId: string) => void;
}

type ChipState = 'done' | 'planned' | 'open' | 'locked';

function stateOf(key: string, ctx: ChipContext): ChipState {
  if (ctx.completed.has(key)) {
    return 'done';
  }
  if (ctx.planned.has(key)) {
    return 'planned';
  }
  return ctx.nodes.get(key)?.status === 'locked' ? 'locked' : 'open';
}

/**
 * Renders a category heading, its progress, and its chips.
 */
export function Requirement({
  category,
  ctx,
}: {
  readonly category: DegreeCategory;
  readonly ctx: ChipContext;
}): React.JSX.Element {
  const shape = categoryShape(category, (key) => ctx.nodes.get(key)?.units);
  const keys = category.required_courses.map(courseKey);
  const satisfied =
    category.required_units > 0 &&
    category.completed_units >= category.required_units;
  const plannedUnits = keys
    .filter((k) => ctx.planned.has(k) && !ctx.completed.has(k))
    .reduce((sum, k) => sum + (ctx.nodes.get(k)?.units ?? 4), 0);
  const doneCount = keys.filter((k) => ctx.completed.has(k)).length;

  const chips = category.required_courses.map((id) => (
    <Chip
      key={id}
      courseId={id}
      ctx={ctx}
      segment={shape.kind === 'choice'}
      faded={shape.kind === 'choice' && satisfied && !ctx.completed.has(courseKey(id))}
    />
  ));

  return (
    <section className={styles.requirement}>
      <header className={styles.reqHeader}>
        <span className={styles.reqName}>{category.name}</span>
        {shape.kind === 'choice' && !satisfied && (
          <span className={styles.reqRule}>
            {shape.pick === null
              ? 'pick some'
              : `pick ${shape.pick} · ${Math.max(0, shape.pick - doneCount)} left`}
          </span>
        )}
        <span className={styles.reqUnits}>
          {satisfied && <Check size={12} className={styles.reqCheck} />}
          {category.completed_units}
          {plannedUnits > 0 && <span className={styles.plus}> +{plannedUnits}</span>}
          <span className={styles.muted}> / {category.required_units}</span>
        </span>
      </header>
      <div className={styles.chips}>
        {shape.kind === 'choice' ? <span className={styles.capsule}>{chips}</span> : chips}
        {shape.kind === 'pool' && (
          <span className={styles.openSlot}>+ {shape.openUnits} units</span>
        )}
      </div>
    </section>
  );
}

function Chip({
  courseId,
  ctx,
  segment,
  faded,
}: {
  readonly courseId: string;
  readonly ctx: ChipContext;
  readonly segment: boolean;
  readonly faded: boolean;
}): React.JSX.Element {
  const key = courseKey(courseId);
  const node = ctx.nodes.get(key);
  const state = stateOf(key, ctx);
  const classes = [
    styles.chip,
    styles[state],
    segment ? styles.segment : '',
    faded ? styles.faded : '',
    ctx.highlighted.has(key) ? styles.blocker : '',
  ].join(' ');

  return (
    <span
      className={styles.chipWrap}
      onMouseEnter={() => ctx.onHover(key)}
      onMouseLeave={() => ctx.onHover(null)}
    >
      <button
        type="button"
        className={classes}
        onClick={() => ctx.onToggle(courseId)}
        aria-pressed={state === 'done'}
        aria-label={`${displayCode(courseId)}, ${state}. Toggle done.`}
      >
        {state === 'done' && <Check size={11} />}
        {state === 'locked' && <Lock size={10} />}
        {displayCode(courseId)}
      </button>
      <span className={styles.chipPop} role="tooltip">
        <span className={styles.popTitle}>{node?.title ?? displayCode(courseId)}</span>
        {node && <span className={styles.popMeta}>{node.units} units</span>}
        {node && node.prerequisites.length > 0 && (
          <span className={styles.popPrereqs}>
            <span className={styles.popMeta}>Needs</span>
            {node.prerequisites.map((group) => (
              <span key={group.join()} className={group.length > 1 ? styles.miniCapsule : undefined}>
                {group.map((id) => (
                  <span
                    key={id}
                    className={`${styles.miniChip} ${
                      ctx.completed.has(courseKey(id)) ? styles.miniDone : ''
                    }`}
                  >
                    {displayCode(id)}
                  </span>
                ))}
              </span>
            ))}
          </span>
        )}
        <span className={styles.popActions}>
          <button type="button" className={styles.popLink} onClick={() => ctx.onFind(courseId)}>
            Find sections <ArrowUpRight size={11} />
          </button>
          <a
            className={styles.popLink}
            href={getUscCourseUrl(courseId)}
            target="_blank"
            rel="noopener noreferrer"
          >
            classes.usc.edu <ExternalLink size={10} />
          </a>
        </span>
      </span>
    </span>
  );
}
