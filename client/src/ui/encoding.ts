/**
 * The app's visual encoding: hue identifies a course, texture identifies a
 * section type.
 *
 * Both the Library swatches and the week's blocks draw from these functions,
 * so a hatched teal square in the list and a hatched teal block on the
 * calendar are guaranteed to mean the same thing.
 */

/**
 * A course color as CSS values: `ink` for text and edges, `fill` for block
 * backgrounds. Both are theme-aware custom properties.
 */
export interface Hue {
  readonly ink: string;
  readonly fill: string;
}

/** Number of `--hue-N-*` token pairs defined in index.css. */
const HUE_COUNT = 8;

const PALETTE: readonly Hue[] = Array.from({ length: HUE_COUNT }, (_, i) => ({
  ink: `var(--hue-${i}-ink)`,
  fill: `var(--hue-${i}-fill)`,
}));

/**
 * Assigns hues by position among the scheduled courses so courses on one
 * week never share a color; an unscheduled course takes the next free hue,
 * which is the color it will keep once added.
 */
export function hueFor(
  courseId: string,
  scheduledCourseIds: readonly string[],
): Hue {
  const index = scheduledCourseIds.indexOf(courseId);
  const slot = index === -1 ? scheduledCourseIds.length : index;
  return PALETTE[slot % PALETTE.length];
}

/**
 * Builds the CSS background that draws a section type's texture in `color`:
 * Lecture solid, Discussion empty (the outline carries it), Lab hatched,
 * Quiz dotted, and combined types split half solid.
 */
export function textureBackground(sectionType: string, color: string): string {
  const hatch = `repeating-linear-gradient(45deg, ${color} 0 1.5px, transparent 1.5px 4px)`;
  const dots = `radial-gradient(${color} 0.9px, transparent 1.2px) 0 0 / 4px 4px`;
  const half = `linear-gradient(90deg, ${color} 50%, transparent 50%)`;
  switch (sectionType) {
    case 'Lecture':
      return color;
    case 'Discussion':
      return 'transparent';
    case 'Lab':
      return hatch;
    case 'Quiz':
      return dots;
    case 'Lecture/Lab':
      return `${half}, ${hatch}`;
    case 'Lecture/Discussion':
      return half;
    default:
      return color;
  }
}
