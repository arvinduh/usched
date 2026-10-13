/**
 * A program's requirement tree rendered in the chip grammar.
 *
 * Each requirement shows its title, progress, any prose rules, and its
 * slots: a loose chip is a course to take; chips gathered in a box are
 * alternatives, any one of which fills the slot. Nested requirements
 * indent beneath their parent. Chip fill encodes state (done, planned this
 * term, available, locked). Clicking a chip opens that course's card;
 * plan edits and navigation go to the caller.
 */

import React from 'react';
import { Check, ExternalLink, Lock } from 'lucide-react';
import { uscCourseUrl } from '../api/client';
import { courseKey, displayCode } from '../lib/degree';
import type {
  Program,
  ProgramAudit,
  Requirement,
  RequirementChoice,
  RequirementProgress,
  Units,
} from '../types';
import { placePopover } from './popover';
import styles from './Degree.module.css';

/**
 * Shared lookups and callbacks for every chip on the page.
 */
export interface ChipContext {
  /** Locked courses mapped to the courses blocking them, by `courseKey`. */
  readonly locked: ReadonlyMap<string, readonly string[]>;
  readonly completed: ReadonlySet<string>;
  readonly planned: ReadonlySet<string>;
  /** Courses blocking the chip under the pointer, keyed by `courseKey`. */
  readonly highlighted: ReadonlySet<string>;
  /** Term for links to USC's Schedule of Classes. */
  readonly term: number;
  readonly onHover: (key: string | null) => void;
  /** Opens the course's card; `title` covers courses this term lacks. */
  readonly onOpen: (code: string, title: string | null) => void;
}

type ChipState = 'done' | 'planned' | 'open' | 'locked';

/** Notes longer than this collapse behind their first line. */
const LONG_NOTES = 160;

function codeOf(choice: RequirementChoice): string {
  return choice.course.resolved ?? choice.course.code;
}

function stateOf(key: string, ctx: ChipContext): ChipState {
  if (ctx.completed.has(key)) {
    return 'done';
  }
  if (ctx.planned.has(key)) {
    return 'planned';
  }
  return ctx.locked.has(key) ? 'locked' : 'open';
}

function unitsText(units: Units): string {
  return units.min === units.max ? `${units.min}` : `${units.min}–${units.max}`;
}

/**
 * Renders a program's requirements as an indented tree.
 */
export function RequirementTree({
  program,
  audit,
  ctx,
}: {
  readonly program: Program;
  readonly audit: ProgramAudit | null;
  readonly ctx: ChipContext;
}): React.JSX.Element {
  const children = new Map<number | null, Requirement[]>();
  for (const req of program.requirements) {
    const siblings = children.get(req.parent) ?? [];
    siblings.push(req);
    children.set(req.parent, siblings);
  }
  const progress = new Map(audit?.requirements.map((p) => [p.position, p]));
  const render = (req: Requirement, depth: number): React.JSX.Element => (
    <RequirementNode
      key={req.position}
      req={req}
      progress={progress.get(req.position)}
      depth={depth}
      ctx={ctx}
    >
      {(children.get(req.position) ?? []).map((child) => render(child, depth + 1))}
    </RequirementNode>
  );
  return <>{(children.get(null) ?? []).map((req) => render(req, 0))}</>;
}

function RequirementNode({
  req,
  progress,
  depth,
  ctx,
  children,
}: {
  readonly req: Requirement;
  readonly progress: RequirementProgress | undefined;
  readonly depth: number;
  readonly ctx: ChipContext;
  readonly children: React.ReactNode;
}): React.JSX.Element {
  const done = progress?.status === 'done';
  const plannedUnits = req.slots
    .flat()
    .filter((c) => {
      const key = courseKey(codeOf(c));
      return ctx.planned.has(key) && !ctx.completed.has(key);
    })
    .reduce((sum, c) => sum + (c.units?.min ?? 0), 0);

  return (
    <section
      className={`${styles.requirement} ${depth > 0 ? styles.nested : ''}`}
      data-depth={Math.min(depth, 3)}
    >
      <header className={styles.reqHeader}>
        <span className={depth === 0 ? styles.reqName : styles.reqSubName}>
          {req.title}
        </span>
        {req.units && (
          <span className={styles.reqUnits}>
            {done && <Check size={12} className={styles.reqCheck} />}
            {progress?.units ?? 0}
            {plannedUnits > 0 && <span className={styles.plus}> +{plannedUnits}</span>}
            <span className={styles.muted}> / {unitsText(req.units)}</span>
          </span>
        )}
        {!req.units && done && (
          <span className={styles.reqUnits}>
            <Check size={12} className={styles.reqCheck} />
          </span>
        )}
      </header>
      {req.notes && <Notes text={req.notes} />}
      {req.slots.length > 0 && (
        <div className={styles.chips}>
          {req.slots.map((slot, i) => {
            const chips = slot.map((choice) => (
              <Chip
                key={choice.course.code}
                choice={choice}
                ctx={ctx}
                faded={done && !ctx.completed.has(courseKey(codeOf(choice)))}
              />
            ));
            return slot.length > 1 ? (
              <span key={i} className={styles.choiceBox}>
                {chips}
              </span>
            ) : (
              chips
            );
          })}
        </div>
      )}
      {children}
    </section>
  );
}

function Notes({ text }: { readonly text: string }): React.JSX.Element {
  if (text.length <= LONG_NOTES) {
    return <p className={styles.reqNotes}>{text}</p>;
  }
  return (
    <details className={styles.reqNotes}>
      <summary>{`${text.slice(0, LONG_NOTES).trimEnd()}…`}</summary>
      {text}
    </details>
  );
}

function Chip({
  choice,
  ctx,
  faded,
}: {
  readonly choice: RequirementChoice;
  readonly ctx: ChipContext;
  readonly faded: boolean;
}): React.JSX.Element {
  const code = codeOf(choice);
  const key = courseKey(code);
  const state = stateOf(key, ctx);
  const blockers = ctx.locked.get(key) ?? [];
  const classes = [
    styles.chip,
    styles[state],
    faded ? styles.faded : '',
    ctx.highlighted.has(key) ? styles.blocker : '',
  ].join(' ');

  return (
    <span
      className={styles.chipWrap}
      onMouseEnter={(e) => {
        placePopover(e);
        ctx.onHover(key);
      }}
      onFocus={placePopover}
      onMouseLeave={() => ctx.onHover(null)}
    >
      <button
        type="button"
        className={classes}
        onClick={() => ctx.onOpen(code, choice.title)}
        aria-label={`${displayCode(code)}, ${state}. Open.`}
      >
        {state === 'done' && <Check size={11} />}
        {state === 'locked' && <Lock size={10} />}
        {displayCode(choice.course.code)}
      </button>
      <span className={styles.chipPop} role="tooltip">
        <span className={styles.popTitle}>
          {choice.title ?? displayCode(choice.course.code)}
        </span>
        {choice.units && (
          <span className={styles.popMeta}>{unitsText(choice.units)} units</span>
        )}
        {blockers.length > 0 && (
          <span className={styles.popPrereqs}>
            <span className={styles.popMeta}>Needs</span>
            {blockers.map((b) => (
              <span key={b} className={styles.miniChip}>
                {displayCode(b)}
              </span>
            ))}
          </span>
        )}
        <span className={styles.popActions}>
          <a
            className={styles.popLink}
            href={uscCourseUrl(code, ctx.term)}
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
