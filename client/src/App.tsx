/**
 * Root application component for the usched academic planner.
 *
 * `App` resolves which term is being planned (the stored one, else the
 * newest with courses) and explains a missing catalog. `Planner` then
 * composes two places under one top bar: the planner (the column with
 * search, the advisor, and course cards, beside the week) and the Degree
 * page, which drops down from the top bar's meter. It wires the plan
 * store, catalog search, server audits, advisor chat, and keyboard
 * shortcuts together, and owns which course is open: every place opens
 * courses into the same card, and the card stays open across them.
 * User-authored data lives in `state/store`.
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
  lookupCourses,
} from './api/client';
import { applyActionChip, proposalsOf } from './components/Chat/applyActionChip';
import { useAdvisorChat } from './hooks/useAdvisorChat';
import { useCatalogSearch } from './hooks/useCatalogSearch';
import { DegreeView } from './degree/DegreeView';
import { courseKey, displayCode } from './lib/degree';
import { isTimed, totalUnits } from './lib/schedule';
import { Assistant } from './semester/Assistant';
import { CourseCard } from './semester/Course';
import type { CoursePlan } from './semester/Course';
import { Week } from './semester/Week';
import { TopBar } from './shell/TopBar';
import { Welcome } from './shell/Welcome';
import {
  addSection,
  countGeSeat,
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
  skipWelcome,
  recordCompleted,
  toggleApCredit,
  toggleCompleted,
  toggleSection,
  toggleWatch,
} from './state/actions';
import { setExpanded, setProposals, shownProposal, usePreview } from './state/preview';
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

/** Text that names a course rather than a topic, e.g. "CSCI-104L". */
const COURSE_CODE = /^[A-Za-z]{2,5}[- ]?\d{3}[A-Za-z]{0,4}$/;

/** How long the degree page takes to lift away; matches App.module.css. */
const LIFT_MS = 160;

/** Courses the column suggests as next up. */
const NEXT_UP = 5;

type Space = 'planner' | 'degree';

/** The course whose card is open, as this term offers it. */
interface Opened {
  readonly code: string;
  /** A title from whoever opened it, for courses this term lacks. */
  readonly title: string | null;
  /** Null when this term does not offer the course. */
  readonly course: Course | null;
}

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
  const searchInput = useRef<HTMLInputElement>(null);
  const semester = useRef<HTMLElement>(null);
  const [paneWidth, setPaneWidth] = useState(readPaneWidth);
  const [space, setSpace] = useState<Space>('planner');
  const [opened, setOpened] = useState<Opened | null>(null);
  const proposal = usePreview(shownProposal);
  // The latest open request, so a slow lookup never replaces a newer card.
  const opening = useRef('');

  const configurations = useTermPlan((p) => p.configurations);
  const activeConfigId = useTermPlan((p) => p.activeConfigId);
  const watchedCourseIds = useTermPlan((p) => p.watchedCourseIds);
  const completedCourseIds = useStore((s) => s.completedCourseIds);
  const apCredits = useStore((s) => s.apCredits);
  const geCounted = useStore((s) => s.geCounted);
  const programId = useStore((s) => s.programId);
  const welcomed = useStore((s) => s.welcomed);

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
  const nextUpIds = useMemo(() => {
    if (!program) {
      return [];
    }
    const locked = new Set(Object.keys(audit?.locked ?? {}).map(courseKey));
    const codes = program.requirements.flatMap((r) =>
      r.slots.flat().flatMap((c) => (c.title ? [c.course.resolved ?? ''] : [])),
    );
    return [...new Set(codes)]
      .filter((c) => c && !completed.has(courseKey(c)) && !locked.has(courseKey(c)))
      .slice(0, NEXT_UP + 4);
  }, [program, audit, completed]);

  const search = useCatalogSearch(term);
  const setSearchText = search.setText;
  const { coursesByCode, sectionsById, remember } = usePlanCourses(
    term,
    nextUpIds,
  );
  // Proposals land on the week, so the planner comes forward to show them.
  const goRef = useRef<(next: Space) => void>(() => {});
  // A finished reply acts at once: proposals land on the week, and courses
  // the student said they took are recorded, with undo.
  const projectProposals = useCallback((chips: readonly Chip[]): void => {
    const proposals = proposalsOf(chips);
    if (proposals.length > 0) {
      goRef.current('planner');
      setProposals(proposals);
    }
  }, []);
  const actOnReply = useCallback((chips: readonly Chip[]): void => {
    projectProposals(chips);
    for (const chip of chips) {
      if (chip.action === 'mark_taken') {
        showToast(chip.label, recordCompleted(chip.course_codes));
      }
    }
  }, [projectProposals]);
  const chat = useAdvisorChat(actOnReply);

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
    auditProgram(term, programId, completedCourseIds, apCredits, geCounted)
      .then((a) => !stale && setLoadedAudit({ key: auditKey, audit: a }))
      .catch(console.error);
    return () => {
      stale = true;
    };
  }, [auditKey, term, programId, completedCourseIds, apCredits, geCounted]);

  useEffect(() => {
    let stale = false;
    auditGe(completedCourseIds, apCredits, geCounted)
      .then((g) => !stale && setGeProgress(g))
      .catch(console.error);
    return () => {
      stale = true;
    };
  }, [completedCourseIds, apCredits, geCounted]);

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
  const activeIds = useMemo(() => new Set(activeSectionIds), [activeSectionIds]);
  const savedCourses = useMemo(
    () =>
      watchedCourseIds
        .map((code) => coursesByCode.get(code))
        .filter((c): c is Course => c !== undefined),
    [watchedCourseIds, coursesByCode],
  );

  const nextUp = useMemo(
    () =>
      nextUpIds
        .filter((id) => !planned.has(courseKey(id)))
        .map((code) => coursesByCode.get(code))
        .filter((c): c is Course => c !== undefined)
        .slice(0, NEXT_UP),
    [nextUpIds, planned, coursesByCode],
  );

  const plannedUnits = totalUnits(activeSections, coursesByCode);
  const degreeUnits =
    audit && program?.total_units
      ? { completed: audit.units, planned: plannedUnits, total: program.total_units }
      : null;
  const termInfo = terms.find((t) => t.code === term);
  const termName = termInfo ? `${termInfo.season} ${termInfo.year}` : String(term);

  // Morph between places where the browser supports view transitions; the
  // meter and the Degree page's bar share a name, so one becomes the other.
  // Staying put skips it: a transition defers rendering, which would delay
  // the focus that usually follows.
  const currentSpace = useRef(space);
  useEffect(() => {
    currentSpace.current = space;
  }, [space]);
  const switchTo = useCallback((next: Space): void => {
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
  // Leaving the degree, the page first lifts back toward the meter (it
  // dropped from there), then the bar morphs home and the planner rises.
  const [leavingDegree, setLeavingDegree] = useState(false);
  const leaving = useRef(false);
  const go = useCallback(
    (next: Space): void => {
      if (next === currentSpace.current || leaving.current) {
        return;
      }
      if (
        next === 'planner' &&
        !window.matchMedia('(prefers-reduced-motion: reduce)').matches
      ) {
        leaving.current = true;
        setLeavingDegree(true);
        setTimeout(() => {
          leaving.current = false;
          setLeavingDegree(false);
          switchTo(next);
        }, LIFT_MS);
        return;
      }
      switchTo(next);
    },
    [switchTo],
  );

  useEffect(() => {
    goRef.current = go;
  }, [go]);

  // Focus asked for while the planner is still on its way (the degree
  // page lifts out first) lands once the planner has rendered.
  const focusOnArrival = useRef(false);
  useEffect(() => {
    if (space === 'planner' && focusOnArrival.current) {
      focusOnArrival.current = false;
      searchInput.current?.focus();
    }
  }, [space]);
  const focusInput = useCallback((): void => {
    if (currentSpace.current === 'planner') {
      searchInput.current?.focus();
    } else {
      focusOnArrival.current = true;
      go('planner');
    }
  }, [go]);

  const openCourse = (course: Course): void => {
    opening.current = course.code;
    remember(course);
    setExpanded(course);
    setOpened({ code: course.code, title: course.title, course });
  };

  // Courses named by code (degree chips, advisor replies) may not be offered
  // this term; their card still opens, so they can be marked taken.
  const openCode = (code: string, title: string | null = null): void => {
    opening.current = code;
    getCourse(term, code)
      .then((course) => opening.current === code && openCourse(course))
      .catch(() => {
        if (opening.current === code) {
          setExpanded(null);
          setOpened({ code, title, course: null });
        }
      });
  };

  const closeCourse = useCallback((): void => {
    opening.current = '';
    setOpened(null);
    setExpanded(null);
  }, []);

  // A block clicked on the week shows its course's other sections there as
  // ghosts to swap in, leaving the column as it was. Without one picked,
  // the week shows the open card's sections, if any.
  const expanded = usePreview((p) => p.expanded);
  const resting = opened?.course ?? null;
  const pickBlock = (course: Course): void => {
    if (expanded?.code === course.code) {
      setExpanded(resting);
    } else if (course.sections.some((s) => isTimed(s) && !activeIds.has(s.id))) {
      setExpanded(course);
    } else {
      showToast(`${displayCode(course.code)} has no other sections this term`);
    }
  };
  const clearPick = (): void => {
    if (expanded !== resting) {
      setExpanded(resting);
    }
  };
  // A picked course that leaves the week takes its ghosts with it.
  useEffect(() => {
    if (expanded && expanded !== resting && !scheduledCourseIds.includes(expanded.code)) {
      setExpanded(resting);
    }
  }, [expanded, resting, scheduledCourseIds]);

  // From the Degree page, a course opens in the planner, where its
  // sections can land on the week.
  const openFromDegree = (code: string, title: string | null): void => {
    go('planner');
    openCode(code, title);
  };

  const handleHome = (): void => {
    go('planner');
    closeCourse();
    setSearchText('');
  };

  const handleSelectTerm = (next: number): void => {
    setProposals([]);
    closeCourse();
    selectTerm(next);
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

  // A proposal is a whole week (the advisor builds around the current
  // one), so keeping it replaces this schedule; undo restores it.
  const handleKeepProposal = (proposal: Proposal): void => {
    setProposals([]);
    const before = activeConfig.section_ids;
    overwriteConfig(proposal.sectionIds, activeConfig.id);
    showToast(`Kept ${proposal.name} on ${activeConfig.name}`, () =>
      overwriteConfig(before, activeConfig.id),
    );
  };

  const handleSelectVariant = (configId: string): void => {
    setProposals([]);
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
      `${wasDone ? 'Unmarked' : 'Marked'} ${displayCode(courseId)}${wasDone ? '' : ' taken'}`,
      toggleCompleted(courseId),
    );
  };

  // The catalog decides what is a course; anything else is named back.
  const handleTaken = (codes: readonly string[]): void => {
    setSearchText('');
    lookupCourses(codes)
      .then((known) => {
        const found = new Set(known.map((c) => courseKey(c.code)));
        const unknown = codes.filter((c) => !found.has(c)).map(displayCode);
        const missing = unknown.length > 0 ? `; not USC courses: ${unknown.join(', ')}` : '';
        if (known.length === 0) {
          showToast(`Not USC courses: ${unknown.join(', ')}`);
          return;
        }
        showToast(
          `Marked ${known.length} course${known.length === 1 ? '' : 's'} taken${missing}`,
          recordCompleted(known.map((c) => c.code)),
        );
      })
      .catch(console.error);
  };

  const handleAsk = (text: string): void => {
    // What the student was looking at, captured before the view resets.
    const screen = {
      page: space,
      open_course: opened?.code ?? null,
      proposal: proposal && {
        name: proposal.name,
        section_ids: [...proposal.sectionIds],
      },
    };
    go('planner');
    closeCourse();
    setSearchText('');
    chat.send(text, {
      term,
      sectionIds: activeSectionIds,
      shortlistedCodes: watchedCourseIds,
      completedCodes: completedCourseIds,
      apCredits,
      geCounted,
      programId,
      variants: configurations
        .filter((c) => c.id !== activeConfig.id)
        .map((c) => ({ name: c.name, section_ids: [...c.section_ids] })),
      screen,
    });
  };

  const handleChip = (chip: Chip): void => {
    applyActionChip(chip, {
      search: (query) =>
        COURSE_CODE.test(query.trim()) ? openCode(query.trim()) : setSearchText(`>${query}`),
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
    setProposals([]);
    closeCourse();
    search.setText('');
    showToast('All data erased');
  };

  const isCardOpen = opened !== null;
  // Escape peels one layer, from the input or anywhere: the Degree page,
  // a block's picked sections, the card, then the search text.
  const isPicking = expanded !== resting;
  const peel = useCallback((): void => {
    if (currentSpace.current === 'degree') {
      go('planner');
    } else if (isPicking) {
      setExpanded(resting);
    } else if (isCardOpen) {
      closeCourse();
    } else {
      setSearchText('');
    }
  }, [go, isPicking, resting, isCardOpen, closeCourse, setSearchText]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent): void => {
      const mod = e.metaKey || e.ctrlKey;
      const key = e.key.toLowerCase();
      const typing = isTyping(e.target) || e.isComposing;
      // Writes into the bar from anywhere and focuses it, so typing never
      // needs a click first.
      const typeIntoBar = (edit: (text: string) => string): void => {
        // In the planner without a bar, the first-run welcome is showing.
        if (!searchInput.current && currentSpace.current === 'planner') {
          return;
        }
        e.preventDefault();
        setSearchText(edit);
        focusInput();
      };
      // ">" (or Ctrl/Cmd+Shift+P) and "/" switch the bar's mode, keeping
      // whatever words it already holds.
      const withMode = (prefix: string) => (text: string) =>
        prefix + text.replace(/^[>/]/, '');
      if (mod && e.shiftKey && key === 'p') {
        typeIntoBar(withMode('>'));
        return;
      }
      if (mod && key === 'j') {
        e.preventDefault();
        focusInput();
        return;
      }
      if (!mod && !e.altKey && !typing) {
        if (e.key === '>' || e.key === '/') {
          typeIntoBar(withMode(e.key));
          return;
        }
        // A letter or digit typed outside a field starts or continues a
        // message in the bar.
        if (/^[\p{L}\p{N}]$/u.test(e.key)) {
          typeIntoBar((text) => text + e.key);
          return;
        }
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
        case '[':
          cycleConfig(-1);
          return;
        case ']':
          cycleConfig(1);
          return;
        case 'Escape':
          peel();
          return;
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [peel, focusInput, setSearchText]);

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

  if (!programId && !welcomed) {
    // A new program opens its degree, where taken courses get marked next.
    return (
      <Welcome
        programs={programs}
        onChoose={(id) => {
          selectProgram(id);
          setSpace('degree');
        }}
        onSkip={skipWelcome}
      />
    );
  }

  const plan: CoursePlan = {
    completed,
    watched,
    activeSectionIds: activeIds,
    scheduledCourseIds,
    onToggleSave: toggleWatch,
    onToggleTaken: handleToggleCompleted,
  };

  return (
    <div className={styles.app}>
      <TopBar
        units={degreeUnits}
        terms={terms}
        term={term}
        onSelectTerm={handleSelectTerm}
        isDegreeOpen={space === 'degree'}
        onToggleDegree={() => go(space === 'degree' ? 'planner' : 'degree')}
        onHome={handleHome}
        onCopySections={handleCopySections}
        onReset={handleReset}
      />

      {space === 'degree' ? (
        <main className={`${styles.degree} ${leavingDegree ? styles.lifting : ''}`}>
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
            onOpenCourse={openFromDegree}
            onToggleTaken={handleToggleCompleted}
            onBrowseGe={(letter) => {
              go('planner');
              setSearchText(`>ge ${letter.toLowerCase()} `);
            }}
            onCountGe={(code, isFull) =>
              showToast(
                isFull ? `Cleared your ${code} count` : `Counted one ${code} course`,
                countGeSeat(code, isFull),
              )
            }
          />
        </main>
      ) : (
        <main
          ref={semester}
          className={styles.semester}
          style={{ '--pane': `${paneWidth}px` } as React.CSSProperties}
        >
          <aside className={styles.left}>
            <Assistant
              search={search}
              inputRef={searchInput}
              messages={chat.messages}
              busy={chat.isLoading}
              onAsk={handleAsk}
              onTaken={handleTaken}
              onChip={handleChip}
              onProject={projectProposals}
              onNewChat={chat.clear}
              onOpenDegree={() => go('degree')}
              onEscape={peel}
              onOpenCourse={openCourse}
              onOpenCode={openCode}
              savedCourses={savedCourses}
              activeSections={activeSections}
              plan={plan}
              nextUp={nextUp}
              card={
                opened && (
                  <CourseCard
                    key={opened.code}
                    course={opened.course}
                    code={opened.code}
                    title={opened.title}
                    termName={termName}
                    plan={plan}
                    onToggleSection={handleToggleSection}
                    otherVariants={otherVariants}
                    onAddToVariant={handleAddToVariant}
                    onClose={closeCourse}
                  />
                )
              }
            />
            <div
              className={styles.resize}
              onPointerDown={startResize}
              role="separator"
              aria-orientation="vertical"
              aria-label="Resize the column"
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
              onFocusCourse={openCourse}
              onPickBlock={pickBlock}
              onClearPick={clearPick}
              onKeepProposal={handleKeepProposal}
              onDiscardProposal={() => setProposals([])}
            />
          </section>
        </main>
      )}

      <ToastHost />
    </div>
  );
}
