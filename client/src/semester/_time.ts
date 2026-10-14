/**
 * Compact clock formatting for minutes since midnight.
 *
 * Produces the terse forms the UI uses ("10–11:50a", "2p") instead of
 * zero-padded 24-hour strings. Pure deterministic math, cleanly handling
 * TBA and async sections without fixed meeting times.
 */

function clock(minutes: number): { readonly text: string; readonly pm: boolean } {
  const h24 = Math.floor(minutes / 60);
  const m = minutes % 60;
  const h12 = h24 % 12 === 0 ? 12 : h24 % 12;
  return {
    text: m === 0 ? `${h12}` : `${h12}:${m.toString().padStart(2, '0')}`,
    pm: h24 >= 12,
  };
}

/**
 * Formats a time range, writing the meridiem once when both ends share it:
 * 600–710 becomes "10–11:50a"; 690–770 becomes "11:30a–12:50p".
 * Returns "TBA" for null, undefined, NaN, or invalid intervals.
 */
export function formatRange(
  start: number | null | undefined,
  end: number | null | undefined,
): string {
  if (
    start === null ||
    start === undefined ||
    end === null ||
    end === undefined ||
    Number.isNaN(start) ||
    Number.isNaN(end) ||
    start < 0 ||
    end <= start
  ) {
    return 'TBA';
  }
  const a = clock(start);
  const b = clock(end);
  const suffix = (pm: boolean): string => (pm ? 'p' : 'a');
  return a.pm === b.pm
    ? `${a.text}–${b.text}${suffix(b.pm)}`
    : `${a.text}${suffix(a.pm)}–${b.text}${suffix(b.pm)}`;
}

/**
 * Formats a whole hour for axis labels: 9 becomes "9a", 13 becomes "1p".
 */
export function formatHour(hour: number | null | undefined): string {
  if (hour === null || hour === undefined || Number.isNaN(hour) || hour < 0) {
    return 'TBA';
  }
  const { text, pm } = clock(hour * 60);
  return `${text}${pm ? 'p' : 'a'}`;
}

/**
 * Formats a single minute timestamp (e.g. 600 -> "10a", 630 -> "10:30a").
 */
export function formatMinutes(minutes: number | null | undefined): string {
  if (minutes === null || minutes === undefined || Number.isNaN(minutes) || minutes < 0) {
    return 'TBA';
  }
  const { text, pm } = clock(minutes);
  return `${text}${pm ? 'p' : 'a'}`;
}
