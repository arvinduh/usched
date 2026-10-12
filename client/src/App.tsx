/**
 * Root application component for the usched academic planner.
 *
 * `App` resolves which term is being planned (the stored one, else the
 * newest with courses) and explains a missing catalog. `Planner` then
 * composes the two spaces (Semester: the Assistant pane beside the week;
 * Degree: the audit) under one top bar, and wires the plan store, catalog
 * search, server audits, advisor chat, and keyboard shortcuts together for
 * that term. Both own only view state; user-authored data lives in
 * `state/store`.
 */

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { flushSync } from 'react-dom';
import {
  auditGe,
  auditProgram,
  getApExams,
  getCourse,
  getProgram,
  getPrograms,
  getTerms,
} from './api/client';
import { applyActionChip } from './components/Chat/applyActionChip';
import { useAdvisorChat } from './hooks/useAdvisorChat';
import { useCatalogSearch } from './hooks/useCatalogSearch';
import { DegreeView } from './degree/DegreeView';
import { courseKey, displayCode } from './lib/degree';
import { totalUnits } from './lib/schedule';
import { Assistant } from './semester/Assistant';
import type { AssistantView } from './semester/Assistant';
import { Week } from './semester/Week';
import { TopBar } from './shell/TopBar';
import {
  addSection,
  createConfig,
  cycleConfig,
  deleteConfig,
  dropSection,
  duplicateActiveConfig,
  overwriteConfig,
  renameConfig,
  selectConfig,
  selectProgram,
  selectTerm,
  recordCompleted,
  toggleApCredit,
  toggleCompleted,
  toggleSection,
  toggleWatch,
} from './state/actions';
import { hasExpanded, setExpanded, setProposal } from './state/preview';
import type { Proposal } from './state/preview';
import { reset, useStore, useTermPlan } from './state/store';
import { showToast, undoLast } from './state/toast';
import { usePlanCourses } from './state/usePlanCourses';
import { ToastHost } from './ui/Toast';
import type {
  ApExam,
  Chip,
  Course,
  GeProgress,
  Program,
  ProgramAudit,
  ProgramSummary,
  ScheduleConfiguration,
  Section,
  Term,
} from './types';
import styles from './App.module.css';

const MAX_SUGGESTIONS = 8;

type Space = 'semester' | 'degree';

const PANE_KEY = 'usched:pane';
const PANE_DEFAULT = 420;

/** Keeps the assistant pane between usable and overbearing widths. */
function clampPaneWidth(px: number): number {
  return Math.round(Math.min(600, Math.max(340, px)));
}

function readPaneWidth(): number {
  try {
    const saved = Number(localStorage.getItem(PANE_KEY));
    return saved > 0 ? clampPaneWidth(saved) : PANE_DEFAULT;
  } catch {
    return PANE_DEFAULT;
  }
}

function savePaneWidth(px: number): void {
  try {
    localStorage.setItem(PANE_KEY, String(px));
  } catch (err) {
    console.error('Failed to save pane width', err);
  }
}

function isTyping(target: EventTarget | null): boolean {
  return (
    target instanceof HTMLElement &&
    (target.isContentEditable ||
      target.tagName === 'INPUT' ||
      target.tagName === 'TEXTAREA' ||
      target.tagName === 'SELECT')
  );
}

/**
 * Loads the plannable terms and renders the planner for the chosen one.
 */
export function App(): React.JSX.Element {
  const [terms, setTerms] = useState<readonly Term[] | null>(null);
  const [failed, setFailed] = useState(false);
  const stored = useStore((s) => s.term);

  useEffect(() => {
    getTerms()
      .then((all) => setTerms(all.filter((t) => t.has_courses)))
      .catch(() => setFailed(true));
  }, []);

  // A stored term the catalog no longer has falls back to the newest one.
  const term = (terms?.find((t) => t.code === stored) ?? terms?.[0])?.code;
  useEffect(() => {
    if (term !== undefined && term !== stored) {
      selectTerm(term);
    }
  }, [term, stored]);

  if (failed || terms?.length === 0) {
    return (
      <p className={styles.notice}>
        No course catalog yet. Build it with <code>npm run catalog</code>, then
        reload.
      </p>
    );
  }
  if (!terms || term === undefined) {
    return <div className={styles.app} />;
  }
  return <Planner term={term} terms={terms} />;
}

/**
 * Main application shell for one planning term.
 */
function Planner({
  term,
  terms,
}: {
  readonly term: number;
  readonly terms: readonly Term[];
}): React.JSX.Element {
  const [space, setSpace] = useState<Space>('semester');
  const [view, setView] = useState<AssistantView>('chat');
  const searchInput = useRef<HTMLInputElement>(null);
  const semester = useRef<HTMLElement>(null);
  const [paneWidth, setPaneWidth] = useState(readPaneWidth);

  const configurations = useTermPlan((p) => p.configurations);
  const activeConfigId = useTermPlan((p) => p.activeConfigId);
  const watchedCourseIds = useTermPlan((p) => p.watchedCourseIds);
  const completedCourseIds = useStore((s) => s.completedCourseIds);
  const apCredits = useStore((s) => s.apCredits);
  const programId = useStore((s) => s.programId);

  const [programs, setPrograms] = useState<readonly ProgramSummary[]>([]);
  const [apExams, setApExams] = useState<readonly ApExam[]>([]);
  // Fetched results remember what they answer, so a stale one is never
  // shown for a newly chosen program or term.
  const [loadedProgram, setLoadedProgram] = useState<Program | null>(null);
  const [loadedAudit, setLoadedAudit] = useState<{
    readonly key: string;
    readonly audit: ProgramAudit;
  } | null>(null);
  const auditKey = `${term}|${programId}`;
  const program = loadedProgram?.id === programId ? loadedProgram : null;
  const audit = loadedAudit?.key === auditKey ? loadedAudit.audit : null;
  const [geProgress, setGeProgress] = useState<readonly GeProgress[] | null>(
    null,
  );

  const completed = useMemo(
    () => new Set(completedCourseIds.map(courseKey)),
    [completedCourseIds],
  );
  // Program courses the student can take next: untaken and not locked. A
  // few spares cover ones already planned or not offered this term, which
  // drop out once the week and the catalog resolve.
  const suggestionIds = useMemo(() => {
    if (!program) {
      return [];
    }
    const locked = new Set(Object.keys(audit?.locked ?? {}).map(courseKey));
    const codes = program.requirements.flatMap((r) =>
      r.slots.flat().flatMap((c) => (c.title ? [c.course.resolved ?? ''] : [])),
    );
    return [...new Set(codes)]
      .filter((c) => c && !completed.has(courseKey(c)) && !locked.has(courseKey(c)))
      .slice(0, MAX_SUGGESTIONS + 4);
  }, [program, audit, completed]);

  const search = useCatalogSearch(term);
  const setSearchText = search.setText;
  const { coursesByCode, sectionsById, remember } = usePlanCourses(
    term,
    search.courses,
    suggestionIds,
  );
  const chat = useAdvisorChat();

  useEffect(() => {
    getApExams().then(setApExams).catch(console.error);
    getPrograms()
      .then((all) =>
        setPrograms(all.filter((p) => p.kind === 'degree' || p.kind === 'minor')),
      )
      .catch(console.error);
  }, []);

  useEffect(() => {
    if (programId) {
      getProgram(programId).then(setLoadedProgram).catch(console.error);
    }
  }, [programId]);

  useEffect(() => {
    if (!programId) {
      return;
    }
    let stale = false;
    auditProgram(term, programId, completedCourseIds)
      .then((a) => !stale && setLoadedAudit({ key: auditKey, audit: a }))
      .catch(console.error);
    return () => {
      stale = true;
    };
  }, [auditKey, term, programId, completedCourseIds]);

  useEffect(() => {
    let stale = false;
    auditGe(completedCourseIds, apCredits)
      .then((g) => !stale && setGeProgress(g))
      .catch(console.error);
    return () => {
      stale = true;
    };
  }, [completedCourseIds, apCredits]);

  const activeConfig =
    configurations.find((c) => c.id === activeConfigId) ?? configurations[0];
  const activeSectionIds = activeConfig.section_ids;

  const activeSections = useMemo(
    () =>
      activeSectionIds
        .map((id) => sectionsById.get(id))
        .filter((s): s is Section => s !== undefined),
    [activeSectionIds, sectionsById],
  );
  const scheduledCourseIds = useMemo(
    () => [...new Set(activeSections.map((s) => s.course_code))],
    [activeSections],
  );
  const otherVariants = useMemo(
    () =>
      configurations
        .filter((c) => c.id !== activeConfig.id)
        .map((c) => ({ id: c.id, name: c.name })),
    [configurations, activeConfig.id],
  );
  const planned = useMemo(
    () => new Set(scheduledCourseIds.map(courseKey)),
    [scheduledCourseIds],
  );
  const watched = useMemo(() => new Set(watchedCourseIds), [watchedCourseIds]);
  const savedCourses = useMemo(
    () =>
      watchedCourseIds
        .map((code) => coursesByCode.get(code))
        .filter((c): c is Course => c !== undefined),
    [watchedCourseIds, coursesByCode],
  );
  const suggestions = useMemo(
    () =>
      suggestionIds
        .filter((id) => !planned.has(courseKey(id)))
        .map((code) => coursesByCode.get(code))
        .filter((c): c is Course => c !== undefined)
        .slice(0, MAX_SUGGESTIONS),
    [suggestionIds, planned, coursesByCode],
  );

  const plannedUnits = totalUnits(activeSections, coursesByCode);
  const degreeUnits =
    audit && program?.total_units
      ? { completed: audit.units, planned: plannedUnits, total: program.total_units }
      : null;

  // Morph between spaces where the browser supports view transitions.
  // Staying put skips it: a transition defers rendering, which would delay
  // the search focus that usually follows.
  const currentSpace = useRef(space);
  useEffect(() => {
    currentSpace.current = space;
  }, [space]);
  const go = useCallback((next: Space): void => {
    if (next === currentSpace.current) {
      return;
    }
    if ('startViewTransition' in document) {
      // A skipped animation (hidden tab, rapid toggling) rejects `ready`;
      // the state update itself still applies, so the rejection is noise.
      document
        .startViewTransition(() => flushSync(() => setSpace(next)))
        .ready.catch(() => {});
    } else {
      setSpace(next);
    }
  }, []);

  const focusComposer = useCallback((): void => {
    go('semester');
    requestAnimationFrame(() => searchInput.current?.focus());
  }, [go]);

  const showResults = useCallback(
    (text: string): void => {
      go('semester');
      setView('results');
      setSearchText(text);
    },
    [go, setSearchText],
  );

  // Opening a course expands it (ghosting its sections) and lists it first
  // in the results, where its sections can be picked.
  const handleOpenCourse = (course: Course): void => {
    remember(course);
    setExpanded(course);
    showResults(displayCode(course.code));
  };

  const handleOpenCourseId = (code: string): void => {
    // The advisor can name courses this term's catalog lacks; say so rather
    // than leave an unexplained empty list.
    getCourse(term, code)
      .then(handleOpenCourse)
      .catch(() => {
        showToast(`${displayCode(code)} isn't offered this term`);
        showResults(displayCode(code));
      });
  };

  const handleSelectTerm = (next: number): void => {
    setProposal(null);
    setExpanded(null);
    selectTerm(next);
  };

  const handleToggleSave = (course: Course): void => {
    remember(course);
    toggleWatch(course.code);
  };

  const handleToggleSection = (section: Section, course: Course): void => {
    remember(course);
    toggleSection(section, course.sections);
  };

  const handleAddToVariant = (
    section: Section,
    course: Course,
    configId: string | null,
  ): void => {
    remember(course);
    const target = configId && configurations.find((c) => c.id === configId);
    if (target) {
      addSection(section, course.sections, target.id);
      // Adding may swap out a sibling, so undo restores the whole variant.
      showToast(`Added ${displayCode(course.code)} to ${target.name}`, () =>
        overwriteConfig(target.section_ids, target.id),
      );
    } else {
      const id = createConfig(undefined, [section.id]);
      showToast(`Added ${displayCode(course.code)} to a new variant`, () => {
        deleteConfig(id);
      });
    }
  };

  const handleKeepProposal = (proposal: Proposal): void => {
    setProposal(null);
    const id = createConfig(proposal.name, proposal.sectionIds);
    showToast(`Kept as ${proposal.name}`, () => {
      deleteConfig(id);
    });
  };

  const handleSelectVariant = (configId: string): void => {
    setProposal(null);
    selectConfig(configId);
  };

  const handleRemove = (section: Section): void => {
    const undo = dropSection(section.id);
    showToast(
      `Removed ${displayCode(section.course_code)} ${section.type.toLowerCase()}`,
      undo,
    );
  };

  const handleDeleteVariant = (config: ScheduleConfiguration): void => {
    showToast(`Deleted ${config.name}`, deleteConfig(config.id));
  };

  const handleToggleCompleted = (courseId: string): void => {
    const wasDone = completed.has(courseKey(courseId));
    showToast(
      `${wasDone ? 'Unmarked' : 'Marked'} ${displayCode(courseId)}${wasDone ? '' : ' done'}`,
      toggleCompleted(courseId),
    );
  };

  const handleRecordCompleted = (courseIds: readonly string[]): void => {
    showToast(
      `Marked ${courseIds.length} course${courseIds.length === 1 ? '' : 's'} done`,
      recordCompleted(courseIds),
    );
  };

  const handleAsk = (text: string): void => {
    setExpanded(null);
    setView('chat');
    setSearchText('');
    chat.send(text, {
      term,
      plannedCodes: scheduledCourseIds,
      shortlistedCodes: watchedCourseIds,
      completedCodes: completedCourseIds,
      programId,
    });
  };

  const handleChip = (chip: Chip): void => {
    applyActionChip(chip, {
      showWeek: () => go('semester'),
      showDegree: () => go('degree'),
      search: showResults,
    });
  };

  const handleCopySections = (): void => {
    const ids = activeConfig.section_ids;
    navigator.clipboard
      .writeText(ids.join(', '))
      .then(() =>
        showToast(
          ids.length > 0
            ? `Copied ${ids.length} section number${ids.length === 1 ? '' : 's'}`
            : 'This week has no sections yet',
        ),
      )
      .catch(console.error);
  };

  const handleReset = (): void => {
    reset();
    chat.clear();
    setProposal(null);
    setExpanded(null);
    search.setText('');
    showToast('All data erased');
  };

  useEffect(() => {
    const onKey = (e: KeyboardEvent): void => {
      const mod = e.metaKey || e.ctrlKey;
      const key = e.key.toLowerCase();
      if (mod && key === 'j') {
        e.preventDefault();
        focusComposer();
        return;
      }
      if (mod && key === 'z' && !isTyping(e.target)) {
        if (undoLast()) {
          e.preventDefault();
        }
        return;
      }
      if (mod || e.altKey || isTyping(e.target)) {
        return;
      }
      switch (e.key) {
        case '/':
          e.preventDefault();
          focusComposer();
          return;
        case 'd':
        case 'D':
          go(space === 'degree' ? 'semester' : 'degree');
          return;
        case '[':
          cycleConfig(-1);
          return;
        case ']':
          cycleConfig(1);
          return;
        case 'Escape':
          // Peel one layer: an open course, then the results, then the text.
          if (hasExpanded()) {
            setExpanded(null);
          } else if (view === 'results') {
            setView('chat');
          } else {
            setSearchText('');
          }
          return;
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [go, focusComposer, space, view, setSearchText]);

  // Drag the pane edge to resize. Moves write the CSS variable directly so
  // the app does not re-render per pointer event; the width is committed
  // and remembered on release.
  const startResize = (e: React.PointerEvent<HTMLDivElement>): void => {
    const grid = semester.current;
    if (!grid) {
      return;
    }
    e.preventDefault();
    const left = grid.getBoundingClientRect().left;
    let width = paneWidth;
    const move = (ev: PointerEvent): void => {
      width = clampPaneWidth(ev.clientX - left);
      grid.style.setProperty('--pane', `${width}px`);
    };
    const up = (): void => {
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', up);
      setPaneWidth(width);
      savePaneWidth(width);
    };
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', up);
  };

  return (
    <div className={styles.app}>
      <TopBar
        units={degreeUnits}
        terms={terms}
        term={term}
        onSelectTerm={handleSelectTerm}
        isDegreeOpen={space === 'degree'}
        onToggleDegree={() => go(space === 'degree' ? 'semester' : 'degree')}
        onHome={() => go('semester')}
        onCopySections={handleCopySections}
        onReset={handleReset}
      />

      {space === 'semester' ? (
        <main
          ref={semester}
          className={styles.semester}
          style={{ '--pane': `${paneWidth}px` } as React.CSSProperties}
        >
          <aside className={styles.left}>
            <Assistant
              view={view}
              onView={setView}
              search={search}
              inputRef={searchInput}
              messages={chat.messages}
              busy={chat.isLoading}
              onAsk={handleAsk}
              onChip={handleChip}
              onNewChat={chat.clear}
              onOpenCourse={handleOpenCourse}
              onOpenCourseId={handleOpenCourseId}
              savedCourses={savedCourses}
              suggestions={suggestions}
              activeSections={activeSections}
              scheduledCourseIds={scheduledCourseIds}
              completed={completed}
              watched={watched}
              onToggleSave={handleToggleSave}
              onToggleTaken={(course) => handleToggleCompleted(course.code)}
              onToggleSection={handleToggleSection}
              otherVariants={otherVariants}
              onAddToVariant={handleAddToVariant}
            />
            <div
              className={styles.resize}
              onPointerDown={startResize}
              role="separator"
              aria-orientation="vertical"
              aria-label="Resize the assistant pane"
            />
          </aside>
          <section className={styles.right}>
            <Week
              configurations={configurations}
              activeConfigId={activeConfig.id}
              sections={activeSections}
              sectionsById={sectionsById}
              coursesByCode={coursesByCode}
              scheduledCourseIds={scheduledCourseIds}
              onSelectVariant={handleSelectVariant}
              onRenameVariant={renameConfig}
              onDeleteVariant={handleDeleteVariant}
              onDuplicateVariant={duplicateActiveConfig}
              onToggleSection={handleToggleSection}
              onRemove={handleRemove}
              onFocusCourse={handleOpenCourse}
              onKeepProposal={handleKeepProposal}
              onDiscardProposal={() => setProposal(null)}
            />
          </section>
        </main>
      ) : (
        <main className={styles.degree}>
          <DegreeView
            term={term}
            programs={programs}
            programId={programId}
            onSelectProgram={selectProgram}
            program={program}
            audit={audit}
            geProgress={geProgress}
            apExams={apExams}
            apCredits={apCredits}
            onToggleAp={toggleApCredit}
            completed={completed}
            planned={planned}
            plannedUnits={plannedUnits}
            onToggleCompleted={handleToggleCompleted}
            onRecordCompleted={handleRecordCompleted}
            onFindSections={handleOpenCourseId}
            onBrowseGe={(letter) => showResults(`ge ${letter.toLowerCase()} `)}
          />
        </main>
      )}

      <ToastHost />
    </div>
  );
}
