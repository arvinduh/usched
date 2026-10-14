/**
 * A number that counts to its new value instead of jumping.
 *
 * The span's text is written straight to the DOM each frame, so counting
 * re-renders nothing, and no frame is requested once the count lands.
 * Reduced motion shows the new value at once.
 */

import type React from "react";
import { useLayoutEffect, useRef } from "react";

const COUNT_MS = 420;

function format(n: number): string {
  return String(Math.round(n * 10) / 10);
}

/**
 * Renders `value`, counting from the previous one when it changes.
 */
export function CountUp({
  value,
}: {
  readonly value: number;
}): React.JSX.Element {
  const ref = useRef<HTMLSpanElement>(null);
  // What the span shows now, which mid-count is neither old nor new value.
  const shown = useRef(value);

  // Layout effect: the old number must be back before the browser paints.
  useLayoutEffect(() => {
    const el = ref.current;
    const from = shown.current;
    if (!el) {
      return;
    }
    if (
      from === value ||
      window.matchMedia("(prefers-reduced-motion: reduce)").matches
    ) {
      shown.current = value;
      el.textContent = format(value);
      return;
    }
    const start = performance.now();
    let frame = 0;
    const tick = (now: number): void => {
      const t = Math.min(1, (now - start) / COUNT_MS);
      // Ease out: quick at first, settling onto the value.
      shown.current =
        t === 1 ? value : from + (value - from) * (1 - (1 - t) ** 3);
      el.textContent = format(shown.current);
      if (t < 1) {
        frame = requestAnimationFrame(tick);
      }
    };
    el.textContent = format(from);
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [value]);

  return <span ref={ref} />;
}
