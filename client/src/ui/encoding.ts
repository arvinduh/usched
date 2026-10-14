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
 * The pattern that marks a section type, drawn in `color`: Lab hatched,
 * Quiz dotted, Discussion ruled. Null for types drawn solid: Lecture, and
 * combined types (Lecture/Lab, Lecture/Discussion), which are lectures
 * first; their label names the rest.
 */
function pattern(sectionType: string, color: string): string | null {
  switch (sectionType) {
    case "Lab":
      return `repeating-linear-gradient(45deg, ${color} 0 1.5px, transparent 1.5px 4px)`;
    case "Quiz":
      return `radial-gradient(${color} 0.9px, transparent 1.2px) 0 0 / 4px 4px`;
    case "Discussion":
      return `repeating-linear-gradient(0deg, ${color} 0 1px, transparent 1px 4px)`;
    default:
      return null;
  }
}

/**
 * Draws a section type's texture in `color` over nothing, so what lies
 * beneath shows through: the swatches, and ghosts of sections not taken.
 */
export function textureBackground(sectionType: string, color: string): string {
  return pattern(sectionType, color) ?? color;
}

/**
 * Draws a chosen section's block: solid course fill, with the type's
 * texture faintly in the course's ink on top. Opaque, so a chosen block
 * never reads as a ghost.
 */
export function blockBackground(sectionType: string, hue: Hue): string {
  const texture = pattern(
    sectionType,
    `color-mix(in srgb, ${hue.ink} 22%, transparent)`,
  );
  return texture ? `${texture}, ${hue.fill}` : hue.fill;
}
