/**
 * Small, label-free glyphs that make up the shared visual language.
 *
 * Each glyph encodes one fact by position, texture, or fill and carries an
 * accessible label with the same fact in words. Glyphs know nothing about
 * plan state; callers pass plain values.
 */

import { Dumbbell, Star } from "lucide-react";
import type React from "react";
import { WEEKDAYS } from "../semester/_schedule";
import { textureBackground } from "./encoding";
import styles from "./Glyphs.module.css";

/**
 * Renders Mon–Fri as five dots, filling meeting days. A Saturday dot is
 * appended only when the section meets on Saturday.
 */
export function DayStrip({
  days,
}: {
  readonly days: readonly string[];
}): React.JSX.Element {
  const shown = days.includes("Sat") ? [...WEEKDAYS, "Sat"] : WEEKDAYS;
  return (
    <span className={styles.days} aria-label={days.join(" ")} role="img">
      {shown.map((d) => (
        <span
          key={d}
          className={`${styles.dot} ${days.includes(d) ? styles.dotOn : ""}`}
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
      className={`${styles.rating} ${muted ? styles.ratingMuted : ""}`}
      title={`${count} rating${count === 1 ? "" : "s"} on RateMyProfessors`}
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

/** At or under this many open seats, a section says how many are left. */
const FEW_SEATS = 5;

/**
 * Says when seats are scarce: "Full" (with any waitlist) or "3 left".
 * Sections with room say nothing, so the word stands out where it matters.
 */
export function SeatNote({
  enrolled,
  capacity,
  waitlist,
}: {
  readonly enrolled: number;
  readonly capacity: number;
  readonly waitlist: number;
}): React.JSX.Element | null {
  const open = capacity - enrolled;
  if (capacity <= 0 || open > FEW_SEATS) {
    return null;
  }
  const label =
    `${enrolled} of ${capacity} seats taken` +
    (waitlist > 0 ? `, ${waitlist} waitlisted` : "");
  return (
    <span className={open <= 0 ? styles.full : styles.few} title={label}>
      {open <= 0
        ? `Full${waitlist > 0 ? ` · ${waitlist} waitlisted` : ""}`
        : `${open} left`}
    </span>
  );
}
