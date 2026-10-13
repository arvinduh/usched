/**
 * The Degree space: one calm column showing how far along the student is.
 *
 * Composes the program picker, a hero unit bar that includes this term's
 * planned units, the requirement tree, the GE strip, and credits (AP exams
 * plus pasted transcripts). All data arrives as props; plan edits and
 * navigation go back through callbacks.
 */

import React, { useEffect, useMemo, useState } from 'react';
import { lookupCourses } from '../api/client';
import { courseKey, displayCode, extractCourseCodes } from '../lib/degree';
import type {
  ApCredit,
  ApExam,
  GeProgress,
  KnownCourse,
  Program,
  ProgramAudit,
  ProgramSummary,
} from '../types';
import { DegreePicker } from './DegreePicker';
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
  readonly onToggleCompleted: (code: string) => void;
  readonly onRecordCompleted: (codes: readonly string[]) => void;
  readonly onFindSections: (code: string) => void;
  readonly onBrowseGe: (letter: string) => void;
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
    onToggle: props.onToggleCompleted,
    onFind: props.onFindSections,
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
            <RequirementTree program={program} audit={audit} ctx={ctx} />
          </section>
        </>
      )}

      {props.geProgress && (
        <GeStrip
          progress={props.geProgress}
          apExams={props.apExams}
          onBrowse={props.onBrowseGe}
        />
      )}

      <Credits
        exams={props.apExams}
        credits={props.apCredits}
        completed={completed}
        onToggleAp={props.onToggleAp}
        onRecord={props.onRecordCompleted}
      />
    </div>
  );
}

function GeStrip({
  progress,
  apExams,
  onBrowse,
}: {
  readonly progress: readonly GeProgress[];
  readonly apExams: readonly ApExam[];
  readonly onBrowse: (letter: string) => void;
}): React.JSX.Element {
  const examNames = new Map(apExams.map((e) => [e.id, e.name]));
  const filled = (p: GeProgress): number => p.courses.length + p.exams.length;
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
          ];
          return (
            <span key={cat.code} className={styles.geWrap}>
              <button
                type="button"
                className={`${styles.geCell} ${styles[fill]}`}
                onClick={() => onBrowse(letter)}
                aria-label={`${cat.code} ${cat.name}: ${
                  isMet ? 'satisfied' : 'open'
                }. Find courses.`}
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
  completed,
  onToggleAp,
  onRecord,
}: {
  readonly exams: readonly ApExam[];
  readonly credits: readonly ApCredit[];
  readonly completed: ReadonlySet<string>;
  readonly onToggleAp: (examId: string) => void;
  readonly onRecord: (courseIds: readonly string[]) => void;
}): React.JSX.Element {
  const [pasted, setPasted] = useState('');
  const candidates = useMemo(() => extractCourseCodes(pasted), [pasted]);
  const lookupKey = candidates.join(',');
  // The catalog decides what is a course; remembers which text it answered.
  const [lookup, setLookup] = useState<{
    readonly key: string;
    readonly known: readonly KnownCourse[];
  } | null>(null);
  useEffect(() => {
    if (!lookupKey) {
      return;
    }
    let stale = false;
    const timer = setTimeout(() => {
      lookupCourses(lookupKey.split(','))
        .then((known) => !stale && setLookup({ key: lookupKey, known }))
        .catch(console.error);
    }, 300);
    return () => {
      stale = true;
      clearTimeout(timer);
    };
  }, [lookupKey]);

  const earned = new Set(credits.map((c) => c.exam_id));
  const known = lookupKey && lookup?.key === lookupKey ? lookup.known : null;
  const recognized = new Set(known?.map((c) => courseKey(c.code)));
  const found = (known ?? []).filter((c) => !completed.has(courseKey(c.code)));
  const unknown = known ? candidates.filter((k) => !recognized.has(k)) : [];

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

      <div className={styles.paste}>
        <textarea
          className={styles.pasteInput}
          value={pasted}
          onChange={(e) => setPasted(e.target.value)}
          placeholder="Paste courses you've taken, like CSCI 103L, MATH 125"
          rows={pasted ? 3 : 1}
        />
        {found.length > 0 && (
          <div className={styles.pasteFound}>
            <span className={styles.chips}>
              {found.map((c) => (
                <span key={c.code} className={styles.miniChip} title={c.title}>
                  {displayCode(c.code)}
                </span>
              ))}
            </span>
            <button
              type="button"
              className={styles.primary}
              onClick={() => {
                onRecord(found.map((c) => c.code));
                setPasted('');
              }}
            >
              Mark {found.length} done
            </button>
          </div>
        )}
        {unknown.length > 0 && (
          <p className={styles.pasteUnknown}>
            Not USC courses: {unknown.map(displayCode).join(', ')}
          </p>
        )}
      </div>
    </section>
  );
}
