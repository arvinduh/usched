/**
 * Small, label-free glyphs that make up the shared visual language.
 *
 * Each glyph encodes one fact by position, texture, or fill and carries an
 * accessible label with the same fact in words. Glyphs know nothing about
 * plan state; callers pass plain values.
 */

import React from 'react';
import { Dumbbell, Star } from 'lucide-react';
import { WEEKDAYS } from '../lib/schedule';
import { textureBackground } from './encoding';
import styles from './Glyphs.module.css';

/**
 * Renders Mon–Fri as five dots, filling meeting days. A Saturday dot is
 * appended only when the section meets on Saturday.
 */
export function DayStrip({
  days,
}: {
  readonly days: readonly string[];
}): React.JSX.Element {
  const shown = days.includes('Sat') ? [...WEEKDAYS, 'Sat'] : WEEKDAYS;
  return (
    <span className={styles.days} aria-label={days.join(' ')} role="img">
      {shown.map((d) => (
        <span
          key={d}
          className={`${styles.dot} ${days.includes(d) ? styles.dotOn : ''}`}
        />
      ))}
    </span>
  );
}

/**
 * Renders a section type as a small textured square in the course's ink.
 */
export function TypeSwatch({
  sectionType,
  ink,
}: {
  readonly sectionType: string;
  readonly ink: string;
}): React.JSX.Element {
  return (
    <span
      className={styles.swatch}
      style={{ background: textureBackground(sectionType, ink), color: ink }}
      aria-label={sectionType}
      role="img"
      title={sectionType}
    />
  );
}

/** Below this many reviews a rating is shown muted as low confidence. */
const MIN_CONFIDENT_RATINGS = 5;

/**
 * Renders RateMyProfessors quality and difficulty as a symmetric icon pair,
 * or nothing when the instructor has no rating.
 */
export function RatingPair({
  rating,
  difficulty,
  count,
}: {
  readonly rating: number | null;
  readonly difficulty: number | null;
  readonly count: number;
}): React.JSX.Element | null {
  if (rating === null) {
    return null;
  }
  const muted = count < MIN_CONFIDENT_RATINGS;
  return (
    <span
      className={`${styles.rating} ${muted ? styles.ratingMuted : ''}`}
      title={`${count} rating${count === 1 ? '' : 's'} on RateMyProfessors`}
    >
      <span aria-label={`Quality ${rating.toFixed(1)}`}>
        <Star size={11} className={styles.star} fill="currentColor" />
        {rating.toFixed(1)}
      </span>
      {difficulty !== null && (
        <span aria-label={`Difficulty ${difficulty.toFixed(1)}`}>
          <Dumbbell size={11} className={styles.effort} />
          {difficulty.toFixed(1)}
        </span>
      )}
    </span>
  );
}

/**
 * Renders seat fill as a hairline along the bottom edge of its parent,
 * turning red when the section is full. The parent must be positioned.
 */
export function SeatMeter({
  enrolled,
  capacity,
  waitlist,
}: {
  readonly enrolled: number;
  readonly capacity: number;
  readonly waitlist: number;
}): React.JSX.Element | null {
  if (capacity <= 0) {
    return null;
  }
  const ratio = Math.min(1, enrolled / capacity);
  const full = enrolled >= capacity;
  const label =
    `${enrolled} of ${capacity} seats taken` +
    (waitlist > 0 ? `, ${waitlist} waitlisted` : '');
  return (
    <span className={styles.seats} title={label} aria-label={label}>
      <span
        className={`${styles.seatsFill} ${full ? styles.seatsFull : ''}`}
        style={{ width: `${ratio * 100}%` }}
      />
    </span>
  );
}
