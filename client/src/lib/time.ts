/**
 * Compact clock formatting for minutes since midnight.
 *
 * Produces the terse forms the UI uses ("10–11:50a", "2p") instead of
 * zero-padded 24-hour strings.
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
 */
export function formatRange(start: number, end: number): string {
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
export function formatHour(hour: number): string {
  const { text, pm } = clock(hour * 60);
  return `${text}${pm ? 'p' : 'a'}`;
}
