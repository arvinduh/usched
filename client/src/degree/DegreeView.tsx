/**
 * The Degree space: one calm column showing how far along the student is.
 *
 * Composes the program picker, a hero unit bar that includes this term's
 * planned units, requirement chip groups, the GE strip, and credits (AP
 * exams plus pasted transcripts). All data arrives as props; plan edits and
 * navigation go back through callbacks.
 */

import React, { useEffect, useMemo, useState } from 'react';
import { getDepartments } from '../api/client';
import { courseKey, displayCode, extractCourseCodes } from '../lib/degree';
import type {
  ApExamDefinition,
  DegreeAuditResponse,
  DegreeProgram,
  GeAuditSummary,
  PrereqNode,
  UserApCredit,
} from '../types';
import { DegreePicker } from './DegreePicker';
import { Requirement } from './Requirement';
import type { ChipContext } from './Requirement';
import styles from './Degree.module.css';

/**
 * Properties for the Degree space.
 */
export interface DegreeViewProps {
  readonly degrees: readonly DegreeProgram[];
  readonly degreeId: string;
  readonly onSelectDegree: (degreeId: string) => void;
  readonly audit: DegreeAuditResponse | null;
  readonly geAudit: GeAuditSummary | null;
  readonly apDefinitions: readonly ApExamDefinition[];
  readonly apCredits: readonly UserApCredit[];
  readonly onToggleAp: (examId: string) => void;
  /** Completed courses keyed by `courseKey`. */
  readonly completed: ReadonlySet<string>;
  /** Courses on the active week keyed by `courseKey`. */
  readonly planned: ReadonlySet<string>;
  readonly plannedUnits: number;
  readonly onToggleCompleted: (courseId: string) => void;
  readonly onRecordCompleted: (courseIds: readonly string[]) => void;
  readonly onFindSections: (courseId: string) => void;
  readonly onBrowseGe: (letter: string) => void;
}

/**
 * Renders the Degree space.
 */
export function DegreeView(props: DegreeViewProps): React.JSX.Element {
  const { audit, completed, planned, plannedUnits } = props;
  const [hovered, setHovered] = useState<string | null>(null);

  const nodes = useMemo(() => {
    const map = new Map<string, PrereqNode>();
    for (const node of audit?.prereq_graph ?? []) {
      map.set(courseKey(node.course_id), node);
    }
    return map;
  }, [audit]);

  // Hovering a locked course lights up the unmet courses blocking it.
  const highlighted = useMemo(() => {
    const node = hovered ? nodes.get(hovered) : undefined;
    if (!node || node.status !== 'locked') {
      return new Set<string>();
    }
    return new Set(
      node.prerequisites
        .filter((group) => !group.some((id) => completed.has(courseKey(id))))
        .flat()
        .map(courseKey),
    );
  }, [hovered, nodes, completed]);

  const ctx: ChipContext = {
    nodes,
    completed,
    planned,
    highlighted,
    onHover: setHovered,
    onToggle: props.onToggleCompleted,
    onFind: props.onFindSections,
  };

  const total = audit?.degree.total_units ?? 0;
  const done = audit?.total_completed_units ?? 0;
  const share = (n: number): string =>
    total > 0 ? `${Math.min(100, (n / total) * 100)}%` : '0%';
  const remaining = Math.max(0, total - done - plannedUnits);

  return (
    <div className={styles.page}>
      <DegreePicker
        degrees={props.degrees}
        selectedId={props.degreeId}
        onSelect={props.onSelectDegree}
      />

      {audit && (
        <>
          <div className={styles.hero}>
            <p className={styles.heroFigure}>
              {done}
              <span className={styles.muted}> / {total}</span>
            </p>
            <div className={styles.heroBar}>
              <span className={styles.heroDone} style={{ width: share(done) }} />
              <span className={styles.heroPlanned} style={{ width: share(plannedUnits) }} />
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

          <section className={styles.group}>
            <h2 className={styles.heading}>Requirements</h2>
            {audit.degree.categories.map((category) => (
              <Requirement key={category.name} category={category} ctx={ctx} />
            ))}
          </section>
        </>
      )}

      {props.geAudit && <GeStrip summary={props.geAudit} onBrowse={props.onBrowseGe} />}

      <Credits
        definitions={props.apDefinitions}
        credits={props.apCredits}
        completed={completed}
        onToggleAp={props.onToggleAp}
        onRecord={props.onRecordCompleted}
      />
    </div>
  );
}

function GeStrip({
  summary,
  onBrowse,
}: {
  readonly summary: GeAuditSummary;
  readonly onBrowse: (letter: string) => void;
}): React.JSX.Element {
  return (
    <section>
      <header className={styles.headingRow}>
        <h2 className={styles.heading}>General education</h2>
        <span className={styles.reqUnits}>
          {summary.total_satisfied}
          <span className={styles.muted}> / {summary.total_required}</span>
        </span>
      </header>
      <div className={styles.geStrip}>
        {summary.categories.map((cat) => {
          const letter = cat.category.replace('GE-', '');
          const fill = cat.is_satisfied
            ? 'full'
            : cat.completed_count > 0
              ? 'half'
              : 'empty';
          const by = [...cat.satisfying_courses.map(displayCode), ...cat.satisfying_ap];
          return (
            <span key={cat.category} className={styles.geWrap}>
              <button
                type="button"
                className={`${styles.geCell} ${styles[fill]}`}
                onClick={() => onBrowse(letter)}
                aria-label={`${cat.category} ${cat.name}: ${
                  cat.is_satisfied ? 'satisfied' : 'open'
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
  definitions,
  credits,
  completed,
  onToggleAp,
  onRecord,
}: {
  readonly definitions: readonly ApExamDefinition[];
  readonly credits: readonly UserApCredit[];
  readonly completed: ReadonlySet<string>;
  readonly onToggleAp: (examId: string) => void;
  readonly onRecord: (courseIds: readonly string[]) => void;
}): React.JSX.Element {
  const [pasted, setPasted] = useState('');
  // Real department codes, loaded on first paste, weed out look-alikes such
  // as "the 100 level".
  const [departments, setDepartments] = useState<ReadonlySet<string> | null>(null);
  const wantsDepartments = pasted !== '' && departments === null;
  useEffect(() => {
    if (wantsDepartments) {
      getDepartments()
        .then((list) => setDepartments(new Set(list)))
        .catch(console.error);
    }
  }, [wantsDepartments]);

  const earned = new Set(credits.map((c) => c.exam_id));
  const found = extractCourseCodes(pasted).filter(
    (k) => !completed.has(k) && (departments?.has(k.split('-')[0]) ?? false),
  );

  return (
    <section>
      <h2 className={styles.heading}>Credits</h2>
      <div className={styles.chips}>
        {definitions.map((exam) => {
          const benefits = [
            exam.fulfills_ge_category && `Fulfills ${exam.fulfills_ge_category}`,
            exam.waives_courses.length > 0 &&
              `Waives ${exam.waives_courses.map(displayCode).join(', ')}`,
            `${exam.units} units`,
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
          placeholder="Paste courses you've taken, like a STARS report"
          rows={pasted ? 3 : 1}
        />
        {found.length > 0 && (
          <div className={styles.pasteFound}>
            <span className={styles.chips}>
              {found.map((k) => (
                <span key={k} className={styles.miniChip}>
                  {displayCode(k)}
                </span>
              ))}
            </span>
            <button
              type="button"
              className={styles.primary}
              onClick={() => {
                onRecord(found);
                setPasted('');
              }}
            >
              Mark {found.length} done
            </button>
          </div>
        )}
      </div>
    </section>
  );
}
