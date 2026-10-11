/**
 * Root application component for the usched academic planner.
 *
 * Composes the two spaces (Semester: Library or Ask beside the week; Degree:
 * the audit) under one top bar, and wires the plan store, catalog search,
 * server audits, advisor chat, and keyboard shortcuts together. It owns only
 * view state; user-authored data lives in `state/store`.
 */

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { flushSync } from 'react-dom';
import {
  getApExams,
  getDegreeAudit,
  getDegrees,
  getGeAudit,
} from './api/client';
import { applyActionChip } from './components/Chat/applyActionChip';
import { useAdvisorChat } from './hooks/useAdvisorChat';
import { useCatalogSearch } from './hooks/useCatalogSearch';
import { DegreeView } from './degree/DegreeView';
import { courseKey, displayCode } from './lib/degree';
import { totalUnits } from './lib/schedule';
import { AskPane } from './semester/AskPane';
import { Library } from './semester/Library';
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
  selectDegree,
  recordCompleted,
  toggleApCredit,
  toggleCompleted,
  toggleSection,
  toggleWatch,
} from './state/actions';
import { hasExpanded, setExpanded, setProposal } from './state/preview';
import type { Proposal } from './state/preview';
import { reset, useStore } from './state/store';
import { showToast, undoLast } from './state/toast';
import { usePlanCourses } from './state/usePlanCourses';
import { ToastHost } from './ui/Toast';
import type {
  ActionChip,
  ApExamDefinition,
  Course,
  DegreeAuditResponse,
  DegreeProgram,
  GeAuditSummary,
  ScheduleConfiguration,
  Section,
} from './types';
import styles from './App.module.css';

const DEFAULT_DEGREE_ID = 'csci-bs';
const MAX_SUGGESTIONS = 8;

type Space = 'semester' | 'degree';

/**
 * Picks the degree shown before the user chooses one.
 */
function fallbackDegreeId(degrees: readonly DegreeProgram[]): string {
  return degrees.find((d) => d.id === 'buai-bs')?.id ?? degrees[0]?.id ?? '';
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
 * Main application shell.
 */
export function App(): React.JSX.Element {
  const [space, setSpace] = useState<Space>('semester');
  const [pane, setPane] = useState<'library' | 'ask'>('library');
  const searchInput = useRef<HTMLInputElement>(null);

  const configurations = useStore((s) => s.configurations);
  const activeConfigId = useStore((s) => s.activeConfigId);
  const watchedCourseIds = useStore((s) => s.watchedCourseIds);
  const completedCourseIds = useStore((s) => s.completedCourseIds);
  const apCredits = useStore((s) => s.apCredits);
  const storedDegreeId = useStore((s) => s.degreeId);

  const [degrees, setDegrees] = useState<readonly DegreeProgram[]>([]);
  const [apDefinitions, setApDefinitions] = useState<
    readonly ApExamDefinition[]
  >([]);
  const [degreeAudit, setDegreeAudit] = useState<DegreeAuditResponse | null>(
    null,
  );
  const [geAudit, setGeAudit] = useState<GeAuditSummary | null>(null);

  const completed = useMemo(
    () => new Set(completedCourseIds.map(courseKey)),
    [completedCourseIds],
  );
  // Eligible degree courses to suggest; a few spares cover ones already
  // planned this term, which are filtered out once the week resolves.
  const suggestionIds = useMemo(
    () =>
      (degreeAudit?.prereq_graph ?? [])
        .filter((n) => n.status === 'eligible' && !completed.has(courseKey(n.course_id)))
        .slice(0, MAX_SUGGESTIONS + 4)
        .map((n) => n.course_id),
    [degreeAudit, completed],
  );

  const search = useCatalogSearch();
  const setSearchText = search.setText;
  const { coursesById, sectionsById, remember } = usePlanCourses(
    search.courses,
    suggestionIds,
  );
  const chat = useAdvisorChat();

  const degreeId = storedDegreeId || fallbackDegreeId(degrees);

  useEffect(() => {
    getApExams().then(setApDefinitions).catch(console.error);
    getDegrees().then(setDegrees).catch(console.error);
  }, []);

  useEffect(() => {
    if (!degreeId) {
      return;
    }
    getDegreeAudit(degreeId, completedCourseIds)
      .then(setDegreeAudit)
      .catch(console.error);
  }, [degreeId, completedCourseIds]);

  useEffect(() => {
    getGeAudit(completedCourseIds, apCredits)
      .then(setGeAudit)
      .catch(console.error);
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
    () => [...new Set(activeSections.map((s) => s.course_id))],
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
        .map((id) => coursesById.get(id))
        .filter((c): c is Course => c !== undefined),
    [watchedCourseIds, coursesById],
  );
  const suggestions = useMemo(
    () =>
      suggestionIds
        .filter((id) => !planned.has(courseKey(id)))
        .map((id) => coursesById.get(id))
        .filter((c): c is Course => c !== undefined)
        .slice(0, MAX_SUGGESTIONS),
    [suggestionIds, planned, coursesById],
  );

  const plannedUnits = totalUnits(activeSections, coursesById);
  const degreeUnits = degreeAudit && {
    completed: degreeAudit.total_completed_units,
    planned: plannedUnits,
    total: degreeAudit.degree.total_units,
  };

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

  const showLibrary = useCallback(
    (text?: string): void => {
      go('semester');
      setPane('library');
      if (text !== undefined) {
        search.setText(text);
      }
      requestAnimationFrame(() => searchInput.current?.focus());
    },
    [go, search],
  );

  const openAsk = useCallback((): void => {
    go('semester');
    setPane('ask');
  }, [go]);

  const handleToggleSave = (course: Course): void => {
    remember(course);
    toggleWatch(course.id);
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
      showToast(`Added ${displayCode(course.id)} to ${target.name}`, () =>
        overwriteConfig(target.section_ids, target.id),
      );
    } else {
      const id = createConfig(undefined, [section.id]);
      showToast(`Added ${displayCode(course.id)} to a new variant`, () => {
        deleteConfig(id);
      });
    }
  };

  const handleKeepProposal = (proposal: Proposal): void => {
    const target = proposal.targetConfigId;
    const previous = configurations.find((c) => c.id === target)?.section_ids;
    setProposal(null);
    if (target && previous) {
      overwriteConfig(proposal.sectionIds, target);
      selectConfig(target);
      showToast('Replaced with the suggestion', () =>
        overwriteConfig(previous, target),
      );
    } else {
      const id = createConfig(proposal.name, proposal.sectionIds);
      showToast(`Kept as ${proposal.name}`, () => {
        deleteConfig(id);
      });
    }
  };

  const handleSelectVariant = (configId: string): void => {
    setProposal(null);
    selectConfig(configId);
  };

  const handleRemove = (section: Section): void => {
    const undo = dropSection(section.id);
    showToast(
      `Removed ${displayCode(section.course_id)} ${section.section_type.toLowerCase()}`,
      undo,
    );
  };

  const handleDeleteVariant = (config: ScheduleConfiguration): void => {
    showToast(`Deleted ${config.name}`, deleteConfig(config.id));
  };

  const handleFocusCourse = (course: Course): void => {
    showLibrary(displayCode(course.id));
    setExpanded(course);
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
    setPane('ask');
    void chat.send(text, {
      enrolledCourseIds: scheduledCourseIds,
      watchedCourseIds,
      completedCourseIds,
      degreeId: degreeId || DEFAULT_DEGREE_ID,
    });
  };

  const handleChip = (chip: ActionChip): void => {
    applyActionChip(chip, {
      showWeek: () => go('semester'),
      showDegree: () => go('degree'),
      search: (q) => showLibrary(q),
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
        openAsk();
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
          showLibrary();
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
          // Peel one layer: an open course, then Ask, then the search text.
          if (hasExpanded()) {
            setExpanded(null);
          } else if (pane === 'ask') {
            setPane('library');
          } else {
            setSearchText('');
          }
          return;
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [go, openAsk, showLibrary, space, pane, setSearchText]);

  return (
    <div className={styles.app}>
      <TopBar
        units={degreeUnits}
        isDegreeOpen={space === 'degree'}
        onToggleDegree={() => go(space === 'degree' ? 'semester' : 'degree')}
        onHome={() => go('semester')}
        onCopySections={handleCopySections}
        onReset={handleReset}
      />

      {space === 'semester' ? (
        <main className={styles.semester}>
          <aside className={styles.left}>
            {pane === 'ask' ? (
              <AskPane
                messages={chat.messages}
                isLoading={chat.isLoading}
                onSend={handleAsk}
                onChip={handleChip}
                onBack={() => showLibrary()}
              />
            ) : (
              <Library
                search={search}
                inputRef={searchInput}
                savedCourses={savedCourses}
                suggestions={suggestions}
                activeSections={activeSections}
                scheduledCourseIds={scheduledCourseIds}
                completed={completed}
                watched={watched}
                onToggleSave={handleToggleSave}
                onToggleTaken={(course) => handleToggleCompleted(course.id)}
                onToggleSection={handleToggleSection}
                otherVariants={otherVariants}
                onAddToVariant={handleAddToVariant}
                onAsk={handleAsk}
              />
            )}
          </aside>
          <section className={styles.right}>
            <Week
              configurations={configurations}
              activeConfigId={activeConfig.id}
              sections={activeSections}
              sectionsById={sectionsById}
              coursesById={coursesById}
              scheduledCourseIds={scheduledCourseIds}
              onSelectVariant={handleSelectVariant}
              onRenameVariant={renameConfig}
              onDeleteVariant={handleDeleteVariant}
              onDuplicateVariant={duplicateActiveConfig}
              onToggleSection={handleToggleSection}
              onRemove={handleRemove}
              onFocusCourse={handleFocusCourse}
              onKeepProposal={handleKeepProposal}
              onDiscardProposal={() => setProposal(null)}
            />
          </section>
        </main>
      ) : (
        <main className={styles.degree}>
          <DegreeView
            degrees={degrees}
            degreeId={degreeId}
            onSelectDegree={selectDegree}
            audit={degreeAudit}
            geAudit={geAudit}
            apDefinitions={apDefinitions}
            apCredits={apCredits}
            onToggleAp={toggleApCredit}
            completed={completed}
            planned={planned}
            plannedUnits={plannedUnits}
            onToggleCompleted={handleToggleCompleted}
            onRecordCompleted={handleRecordCompleted}
            onFindSections={(courseId) => showLibrary(displayCode(courseId))}
            onBrowseGe={(letter) => showLibrary(`ge ${letter.toLowerCase()} `)}
          />
        </main>
      )}

      <ToastHost />
    </div>
  );
}
