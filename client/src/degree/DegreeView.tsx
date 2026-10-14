/**
 * The student's degree, as the column beside the week shows it at rest.
 *
 * Composes the program picker, the requirement tree, and the GE strip. AP
 * exams appear beside what they satisfy: as an alternative to the courses
 * they waive and in the popover of the GE categories they fill, so an exam
 * that touches neither is not offered. Unit totals live in the top bar's
 * meter, so they are not repeated here. All data arrives as props;
 * opening courses and plan edits go back through callbacks.
 */

import { ArrowRight, Check, Lock, Search } from "lucide-react";
import React, { useMemo, useState } from "react";
import type { components } from "../api/schema";
import { courseKey, displayCode, levelOf } from "./_degree";
import { placePopover } from "./_popover";
import styles from "./Degree.module.css";
import { DegreePicker } from "./DegreePicker";
import type { ChipContext } from "./Requirement";
import { RequirementTree } from "./Requirement";

/**
 * Properties for the Degree space.
 */
export interface DegreeViewProps {
  /** The planning term, for links and prerequisite checks. */
  readonly term: number;
  readonly programs: readonly components["schemas"]["ProgramSummary"][];
  readonly programId: string;
  readonly onSelectProgram: (programId: string) => void;
  readonly program: components["schemas"]["Program"] | null;
  readonly audit: components["schemas"]["ProgramAudit"] | null;
  readonly geAudit: components["schemas"]["GeAudit"] | null;
  readonly apExams: readonly components["schemas"]["ApExam"][];
  readonly apCredits: readonly components["schemas"]["ApCredit"][];
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
  /** Returns to the planner. */
  readonly onContinue: () => void;
}

/**
 * Renders the Degree space.
 */
export const DegreeView = React.memo(function DegreeView(
  props: DegreeViewProps,
): React.JSX.Element {
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

  const { apExams, apCredits } = props;
  const examsFor = useMemo(() => {
    const byCourse = new Map<string, components["schemas"]["ApExam"][]>();
    for (const exam of apExams) {
      for (const course of exam.waives) {
        const key = courseKey(course.resolved ?? course.code);
        byCourse.set(key, [...(byCourse.get(key) ?? []), exam]);
      }
    }
    return byCourse;
  }, [apExams]);
  const earned = useMemo(
    () => new Set(apCredits.map((c) => c.exam_id)),
    [apCredits],
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
    examsFor,
    earned,
    onToggleAp: props.onToggleAp,
  };

  // GE is undergraduate policy; master's and doctoral students owe none.
  const level = program ? levelOf(program) : null;
  const isGraduate = level === "master" || level === "doctoral";
  const total = program?.total_units ?? 0;
  const done = audit?.units ?? 0;
  const share = (n: number): string =>
    total > 0 ? `${Math.min(100, (n / total) * 100)}%` : "0%";
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
                <span
                  className={styles.heroDone}
                  style={{ width: share(done) }}
                />
                <span
                  className={styles.heroPlanned}
                  style={{ width: share(plannedUnits) }}
                />
              </div>
              <p className={styles.heroLine}>
                {plannedUnits > 0 && (
                  <>
                    <span className={styles.plus}>
                      +{plannedUnits} this term
                    </span>
                    {" · "}
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
            <p className={styles.creditsHint}>
              Taken a course? Click it above to mark it, or type “/took CSCI
              103L, MATH 125” into the planner.
            </p>
          </section>
        </>
      )}

      {props.geAudit && !isGraduate && (
        <GeStrip
          audit={props.geAudit}
          apExams={apExams}
          earned={earned}
          onToggleAp={props.onToggleAp}
          onBrowse={props.onBrowseGe}
          onCount={props.onCountGe}
        />
      )}

      <button
        type="button"
        className={styles.continue}
        onClick={props.onContinue}
        aria-label="Continue to schedule"
      >
        <span>Continue to schedule</span>
        <ArrowRight size={14} className={styles.continueArrow} />
      </button>
    </div>
  );
});

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
 * popover lists the AP exams that fill it and finds courses for it.
 */
function GeStrip({
  audit,
  apExams,
  earned,
  onToggleAp,
  onBrowse,
  onCount,
}: {
  readonly audit: components["schemas"]["GeAudit"];
  readonly apExams: readonly components["schemas"]["ApExam"][];
  readonly earned: ReadonlySet<string>;
  readonly onToggleAp: (examId: string) => void;
  readonly onBrowse: (letter: string) => void;
  readonly onCount: (code: string, isFull: boolean) => void;
}): React.JSX.Element {
  const examNames = new Map(apExams.map((e) => [e.id, e.name]));
  const filled = (p: components["schemas"]["GeProgress"]): number =>
    p.courses.length + p.exams.length + p.counted;
  return (
    <section>
      <header className={styles.headingRow}>
        <h2 className={styles.heading}>General education</h2>
        <span className={styles.reqUnits}>
          {audit.units}
          <span className={styles.muted}> / {audit.required_units} units</span>
        </span>
      </header>
      <div className={styles.geStrip}>
        {audit.categories.map((cat) => {
          const letter = cat.code.replace("GE-", "");
          const isMet = filled(cat) >= cat.required_count;
          const fill = isMet ? "full" : filled(cat) > 0 ? "half" : "empty";
          const by = [
            ...cat.courses.map(displayCode),
            ...cat.exams.map((id) => examNames.get(id) ?? id),
            ...(cat.counted > 0 ? [`${cat.counted} counted by you`] : []),
          ];
          const hint = !isMet
            ? "Click to count one taken elsewhere"
            : cat.counted > 0
              ? "Click to clear your count"
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
                  hint ? ` ${hint}.` : ""
                }`}
              >
                {letter}
              </button>
              <span className={styles.chipPop} role="tooltip">
                <span className={styles.popTitle}>{cat.name}</span>
                <span className={styles.popMeta}>
                  {by.length > 0
                    ? `Met by ${by.join(", ")}`
                    : `Needs ${cat.required_count} course${cat.required_count === 1 ? "" : "s"}`}
                </span>
                {hint && <span className={styles.popHint}>{hint}</span>}
                <ExamToggles
                  exams={apExams.filter((e) => e.ge.includes(cat.code))}
                  earned={earned}
                  onToggle={onToggleAp}
                />
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

/**
 * The AP exams that fill a GE category, as toggles for passing each.
 */
function ExamToggles({
  exams,
  earned,
  onToggle,
}: {
  readonly exams: readonly components["schemas"]["ApExam"][];
  readonly earned: ReadonlySet<string>;
  readonly onToggle: (examId: string) => void;
}): React.JSX.Element | null {
  if (exams.length === 0) {
    return null;
  }
  return (
    <span className={styles.popPrereqs}>
      <span className={styles.popMeta}>Or with</span>
      {exams.map((exam) => (
        <button
          key={exam.id}
          type="button"
          className={`${styles.miniChip} ${
            earned.has(exam.id) ? styles.done : styles.open
          }`}
          aria-pressed={earned.has(exam.id)}
          title={`${exam.units} units with a ${exam.min_score}+`}
          onClick={() => onToggle(exam.id)}
        >
          {exam.name}
        </button>
      ))}
    </span>
  );
}
