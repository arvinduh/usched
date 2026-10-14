/**
 * The first-run screen: asks what the student is studying.
 *
 * The program drives the degree audit, the "Next up" suggestions, and the
 * advisor's brief, so the app asks for it before anything else instead of
 * waiting for the student to find the Degree space. Skipping is allowed;
 * the caller records either answer so the screen never returns. Leaving,
 * the screen lifts away, then its wordmark glides into the top bar's as
 * the next place enters.
 */

import React, { useRef, useState } from 'react';
import { flushSync } from 'react-dom';
import { APP_NAME } from '../config';
import { ProgramSearch } from '../degree/DegreePicker';
import { morph } from '../ui/_morph';
import type { components } from '../api/schema';
import styles from './Welcome.module.css';

/** How long the screen takes to lift away; matches `.leaving`. */
const LEAVE_MS = 180;

/**
 * Properties for the welcome screen.
 */
export interface WelcomeProps {
  readonly programs: readonly components['schemas']['ProgramSummary'][];
  readonly onChoose: (programId: string) => void;
  readonly onSkip: () => void;
}

/**
 * Renders the question, the program search, and a way to skip.
 */
export function Welcome({ programs, onChoose, onSkip }: WelcomeProps): React.JSX.Element {
  const [leaving, setLeaving] = useState(false);
  const left = useRef(false);
  const leave = (update: () => void): void => {
    if (left.current) {
      return;
    }
    left.current = true;
    const go = (): void => morph(() => flushSync(update));
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      go();
      return;
    }
    setLeaving(true);
    setTimeout(go, LEAVE_MS);
  };
  return (
    <main className={`${styles.welcome} ${leaving ? styles.leaving : ''}`}>
      <header className={styles.top}>
        <span className={styles.wordmark}>{APP_NAME}</span>
        <button type="button" className={styles.skip} onClick={() => leave(onSkip)}>
          Skip for now
        </button>
      </header>
      <h1 className={styles.question}>What are you studying?</h1>
      <p className={styles.why}>
        Your major shapes your degree progress, the courses suggested to you, and
        the advisor's answers. Then type the classes you've taken, like “/took
        CSCI 103L, MATH 125”.
      </p>
      <ProgramSearch
        programs={programs}
        onChoose={(id) => leave(() => onChoose(id))}
      />
    </main>
  );
}
