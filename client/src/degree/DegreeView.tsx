/**
 * The student's degree, as the column beside the week shows it at rest.
 *
 * Composes the program picker, the requirement tree, the GE strip, and
 * credits (AP exams; courses taken are typed into the column's input). Unit totals live in the top
 * bar's meter, so they are not repeated here. All data arrives as props;
 * opening courses and plan edits go back through callbacks.
 */

import React, { useMemo, useState } from 'react';
import { Check, Lock, Search } from 'lucide-react';
import { courseKey, displayCode } from '../lib/degree';
import type {
  ApCredit,
  ApExam,
  GeProgress,
  Program,
  ProgramAudit,
  ProgramSummary,
} from '../types';
import { DegreePicker } from './DegreePicker';
import { placePopover } from './popover';
import { RequirementTree } from './Requirement';
import type { ChipContext } from './Requirement';
import styles from './Degree.module.css';

/**
 * Properties for the Degree space.
 */
export interface DegreeViewProps {
  /** The planning term, for links and prerequisite checks. */
  readonly term: number;
  readonly programs: readonly ProgramSummary[];
  readonly programId: string;
  readonly onSelectProgram: (programId: string) => void;
  readonly program: Program | null;
  readonly audit: ProgramAudit | null;
  readonly geProgress: readonly GeProgress[] | null;
  readonly apExams: readonly ApExam[];
  readonly apCredits: readonly ApCredit[];
  readonly onToggleAp: (examId: string) => void;
  /** Completed courses keyed by `courseKey`. */
  readonly completed: ReadonlySet<string>;
  /** Courses on the active week keyed by `courseKey`. */
  readonly planned: ReadonlySet<string>;
  readonly plannedUnits: number;
  readonly onOpenCourse: (code: string, title: string | null) => void;
  readonly onToggleTaken: (code: string) => void;
  readonly onBrowseGe: (letter: string) => void;
  /** Counts one more seat of a GE category by hand, or clears a full one. */
  readonly onCountGe: (code: string, isFull: boolean) => void;
}

/**
 * Renders the Degree space.
 */
export function DegreeView(props: DegreeViewProps): React.JSX.Element {
  const { program, audit, completed, planned, plannedUnits } = props;
  const [hovered, setHovered] = useState<string | null>(null);

  const locked = useMemo(
    () =>
      new Map(
        Object.entries(audit?.locked ?? {}).map(([code, blockers]) => [
          courseKey(code),
          blockers.map(courseKey),
        ]),
      ),
    [audit],
  );

  // Hovering a locked course lights up the courses blocking it.
  const highlighted = useMemo(
    () => new Set(hovered ? (locked.get(hovered) ?? []) : []),
    [hovered, locked],
  );

  const ctx: ChipContext = {
    locked,
    completed,
    planned,
    highlighted,
    term: props.term,
    onHover: setHovered,
    onOpen: props.onOpenCourse,
    onToggleTaken: props.onToggleTaken,
  };

  const total = program?.total_units ?? 0;
  const done = audit?.units ?? 0;
  const share = (n: number): string =>
    total > 0 ? `${Math.min(100, (n / total) * 100)}%` : '0%';
  const remaining = Math.max(0, total - done - plannedUnits);

  return (
    <div className={styles.page}>
      <DegreePicker
        programs={props.programs}
        selectedId={props.programId}
        onSelect={props.onSelectProgram}
      />

      {program && (
        <>
          {total > 0 && (
            <div className={styles.hero}>
              <p className={styles.heroFigure}>
                {done}
                <span className={styles.muted}> / {total}</span>
              </p>
              <div className={styles.heroBar}>
                <span className={styles.heroDone} style={{ width: share(done) }} />
                <span
                  className={styles.heroPlanned}
                  style={{ width: share(plannedUnits) }}
                />
              </div>
              <p className={styles.heroLine}>
                {plannedUnits > 0 && (
                  <>
                    <span className={styles.plus}>+{plannedUnits} this term</span>
                    {' · '}
                  </>
                )}
                {remaining} to go
              </p>
            </div>
          )}

          <section className={styles.group}>
            <h2 className={styles.heading}>Requirements</h2>
            <Legend />
            <RequirementTree program={program} audit={audit} ctx={ctx} />
          </section>
        </>
      )}

      {props.geProgress && (
        <GeStrip
          progress={props.geProgress}
          apExams={props.apExams}
          onBrowse={props.onBrowseGe}
          onCount={props.onCountGe}
        />
      )}

      <Credits
        exams={props.apExams}
        credits={props.apCredits}
        onToggleAp={props.onToggleAp}
      />
    </div>
  );
}

/**
 * Explains chip states: taken counts toward the degree already, and this
 * term means a section is on the active week.
 */
function Legend(): React.JSX.Element {
  return (
    <span className={styles.legend}>
      <span className={`${styles.miniChip} ${styles.done}`}>
        <Check size={10} /> Taken
      </span>
      <span className={`${styles.miniChip} ${styles.planned}`}>This term</span>
      <span className={`${styles.miniChip} ${styles.open}`}>To take</span>
      <span className={`${styles.miniChip} ${styles.locked}`}>
        <Lock size={9} /> Needs prerequisites
      </span>
    </span>
  );
}

/**
 * Renders one cell per GE category. A click counts one seat taken
 * elsewhere until the category is full, then clears the count; the
 * popover finds courses for it.
 */
function GeStrip({
  progress,
  apExams,
  onBrowse,
  onCount,
}: {
  readonly progress: readonly GeProgress[];
  readonly apExams: readonly ApExam[];
  readonly onBrowse: (letter: string) => void;
  readonly onCount: (code: string, isFull: boolean) => void;
}): React.JSX.Element {
  const examNames = new Map(apExams.map((e) => [e.id, e.name]));
  const filled = (p: GeProgress): number => p.courses.length + p.exams.length + p.counted;
  const required = progress.reduce((n, p) => n + p.required_count, 0);
  const satisfied = progress.reduce(
    (n, p) => n + Math.min(filled(p), p.required_count),
    0,
  );
  return (
    <section>
      <header className={styles.headingRow}>
        <h2 className={styles.heading}>General education</h2>
        <span className={styles.reqUnits}>
          {satisfied}
          <span className={styles.muted}> / {required}</span>
        </span>
      </header>
      <div className={styles.geStrip}>
        {progress.map((cat) => {
          const letter = cat.code.replace('GE-', '');
          const isMet = filled(cat) >= cat.required_count;
          const fill = isMet ? 'full' : filled(cat) > 0 ? 'half' : 'empty';
          const by = [
            ...cat.courses.map(displayCode),
            ...cat.exams.map((id) => examNames.get(id) ?? id),
            ...(cat.counted > 0 ? [`${cat.counted} counted by you`] : []),
          ];
          const hint = !isMet
            ? 'Click to count one taken elsewhere'
            : cat.counted > 0
              ? 'Click to clear your count'
              : null;
          return (
            <span
              key={cat.code}
              className={styles.geWrap}
              onMouseEnter={placePopover}
              onFocus={placePopover}
            >
              <button
                type="button"
                className={`${styles.geCell} ${styles[fill]}`}
                onClick={() => onCount(cat.code, isMet)}
                aria-label={`${cat.code} ${cat.name}: ${filled(cat)} of ${cat.required_count}.${
                  hint ? ` ${hint}.` : ''
                }`}
              >
                {letter}
              </button>
              <span className={styles.chipPop} role="tooltip">
                <span className={styles.popTitle}>{cat.name}</span>
                <span className={styles.popMeta}>
                  {by.length > 0
                    ? `Met by ${by.join(', ')}`
                    : `Needs ${cat.required_count} course${cat.required_count === 1 ? '' : 's'}`}
                </span>
                {hint && <span className={styles.popHint}>{hint}</span>}
                <span className={styles.popActions}>
                  <button
                    type="button"
                    className={styles.popAction}
                    onClick={() => onBrowse(letter)}
                  >
                    <Search size={11} />
                    Find courses
                  </button>
                </span>
              </span>
            </span>
          );
        })}
      </div>
    </section>
  );
}

function Credits({
  exams,
  credits,
  onToggleAp,
}: {
  readonly exams: readonly ApExam[];
  readonly credits: readonly ApCredit[];
  readonly onToggleAp: (examId: string) => void;
}): React.JSX.Element {
  const earned = new Set(credits.map((c) => c.exam_id));
  return (
    <section>
      <h2 className={styles.heading}>Credits</h2>
      <div className={styles.chips}>
        {exams.map((exam) => {
          const benefits = [
            exam.ge.length > 0 && `Fulfills ${exam.ge.join(', ')}`,
            exam.waives.length > 0 &&
              `Waives ${exam.waives.map((w) => displayCode(w.code)).join(', ')}`,
            `${exam.units} units with a ${exam.min_score}+`,
          ]
            .filter(Boolean)
            .join(' · ');
          return (
            <button
              key={exam.id}
              type="button"
              className={`${styles.chip} ${styles.sans} ${
                earned.has(exam.id) ? styles.done : styles.open
              }`}
              aria-pressed={earned.has(exam.id)}
              title={benefits}
              onClick={() => onToggleAp(exam.id)}
            >
              {exam.name}
            </button>
          );
        })}
      </div>
      <p className={styles.creditsHint}>
        Taken a course? Click it above to mark it, or type “took CSCI 103L,
        MATH 125” into the planner.
      </p>
    </section>
  );
}
