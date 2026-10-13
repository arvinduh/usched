/**
 * The first-run screen: asks what the student is studying.
 *
 * The program drives the degree audit, the "Next up" suggestions, and the
 * advisor's brief, so the app asks for it before anything else instead of
 * waiting for the student to find the Degree space. Skipping is allowed;
 * the caller records either answer so the screen never returns.
 */

import React from 'react';
import { ProgramSearch } from '../degree/DegreePicker';
import type { ProgramSummary } from '../types';
import styles from './Welcome.module.css';

/**
 * Properties for the welcome screen.
 */
export interface WelcomeProps {
  readonly programs: readonly ProgramSummary[];
  readonly onChoose: (programId: string) => void;
  readonly onSkip: () => void;
}

/**
 * Renders the question, the program search, and a way to skip.
 */
export function Welcome({ programs, onChoose, onSkip }: WelcomeProps): React.JSX.Element {
  return (
    <main className={styles.welcome}>
      <header className={styles.top}>
        <span className={styles.wordmark}>usched</span>
        <button type="button" className={styles.skip} onClick={onSkip}>
          Skip for now
        </button>
      </header>
      <h1 className={styles.question}>What are you studying?</h1>
      <p className={styles.why}>
        Your major shapes your degree progress, the courses suggested to you, and
        the advisor's answers. Then type the classes you've taken, like “/took
        CSCI 103L, MATH 125”.
      </p>
      <ProgramSearch programs={programs} onChoose={onChoose} />
    </main>
  );
}
