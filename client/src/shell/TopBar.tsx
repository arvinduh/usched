/**
 * The app's only chrome: wordmark, degree meter, term, and settings.
 *
 * The meter shows completed, planned-this-term, and remaining units, and
 * clicking it drops the Degree page down from it; the wordmark
 * returns to the planner at rest. The term picker switches which semester
 * is planned. The bar holds no state of its
 * own beyond whether the menu is open.
 */

import React, { useEffect, useRef, useState } from 'react';
import { Settings } from 'lucide-react';
import { ResetButton } from '../components/ResetButton/ResetButton';
import { setTheme, useTheme } from '../state/theme';
import type { Theme } from '../state/theme';
import type { Term } from '../types';
import { Select } from '../ui/Select';
import styles from './TopBar.module.css';

/**
 * Unit totals for the degree meter.
 */
export interface DegreeUnits {
  readonly completed: number;
  readonly planned: number;
  readonly total: number;
}

/**
 * Properties for the top bar.
 */
export interface TopBarProps {
  readonly units: DegreeUnits | null;
  /** Terms that can be planned (fetched ones), newest first. */
  readonly terms: readonly Term[];
  readonly term: number;
  readonly onSelectTerm: (term: number) => void;
  readonly isDegreeOpen: boolean;
  readonly onToggleDegree: () => void;
  readonly onHome: () => void;
  readonly onCopySections: () => void;
  readonly onReset: () => void;
}

/**
 * Renders the bar and its menu.
 */
export function TopBar(props: TopBarProps): React.JSX.Element {
  const {
    units,
    terms,
    term,
    onSelectTerm,
    isDegreeOpen,
    onToggleDegree,
    onHome,
    onCopySections,
    onReset,
  } = props;
  const [menuOpen, setMenuOpen] = useState(false);
  const theme = useTheme();
  const menu = useRef<HTMLDivElement>(null);

  // Close on any press outside the menu, or on Escape.
  useEffect(() => {
    if (!menuOpen) {
      return;
    }
    const onPointer = (e: PointerEvent): void => {
      if (!menu.current?.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    };
    // Escape closes only this layer, so the app-level handler never sees it.
    const onKey = (e: KeyboardEvent): void => {
      if (e.key === 'Escape') {
        e.stopPropagation();
        setMenuOpen(false);
      }
    };
    document.addEventListener('pointerdown', onPointer);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('pointerdown', onPointer);
      document.removeEventListener('keydown', onKey);
    };
  }, [menuOpen]);

  const share = (n: number): string =>
    units && units.total > 0 ? `${Math.min(100, (n / units.total) * 100)}%` : '0%';

  return (
    <header className={styles.bar}>
      <button type="button" className={styles.wordmark} onClick={onHome}>
        usched
      </button>

      <button
        type="button"
        className={`${styles.meter} ${isDegreeOpen ? styles.meterOn : ''}`}
        onClick={onToggleDegree}
        aria-pressed={isDegreeOpen}
        title={isDegreeOpen ? 'Back to planning' : 'Your degree'}
      >
        <span className={styles.label}>Degree</span>
        <span className={`${styles.track} ${isDegreeOpen ? '' : styles.morph}`}>
          <span className={styles.done} style={{ width: share(units?.completed ?? 0) }} />
          <span className={styles.planned} style={{ width: share(units?.planned ?? 0) }} />
        </span>
        {units && (
          <span className={styles.figures}>
            {units.completed}
            {units.planned > 0 && <span className={styles.plus}> +{units.planned}</span>}
            <span className={styles.total}> / {units.total}</span>
          </span>
        )}
      </button>

      <Select
        value={term}
        options={terms.map((t) => ({ value: t.code, label: `${t.season} ${t.year}` }))}
        onChange={onSelectTerm}
        label="Term to plan"
        align="end"
      />

      <div className={styles.menuWrap} ref={menu}>
        <button
          type="button"
          className={styles.menuButton}
          onClick={() => setMenuOpen((v) => !v)}
          aria-expanded={menuOpen}
          aria-label="Settings"
          title="Settings"
        >
          <Settings size={15} />
        </button>
        {menuOpen && (
          <div className={styles.menu} role="menu">
            <div className={styles.themeRow}>
              <span className={styles.themeLabel}>Theme</span>
              <span className={styles.segmented} role="radiogroup" aria-label="Theme">
                {(['system', 'light', 'dark'] as const satisfies readonly Theme[]).map(
                  (option) => (
                    <button
                      key={option}
                      type="button"
                      role="radio"
                      aria-checked={theme === option}
                      className={`${styles.segment} ${theme === option ? styles.segmentOn : ''}`}
                      onClick={() => setTheme(option)}
                    >
                      {option[0].toUpperCase() + option.slice(1)}
                    </button>
                  ),
                )}
              </span>
            </div>
            <div className={styles.divider} />
            <button
              type="button"
              role="menuitem"
              className={styles.item}
              onClick={() => {
                onCopySections();
                setMenuOpen(false);
              }}
            >
              Copy section numbers
            </button>
            <div className={styles.item}>
              <ResetButton
                onReset={() => {
                  onReset();
                  setMenuOpen(false);
                }}
              />
            </div>
          </div>
        )}
      </div>
    </header>
  );
}
