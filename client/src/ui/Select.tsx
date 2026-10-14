/**
 * A dropdown: a quiet text trigger that opens a themed list of choices.
 *
 * Replaces native selects, whose menus the operating system draws (white
 * on white in dark mode, and unstyled). The list follows the listbox
 * pattern: arrows and Home/End move, Enter or Space choose, Escape or a
 * press outside closes, and focus returns to the trigger. The caller owns
 * the value.
 */

import { Check, ChevronDown } from "lucide-react";
import type React from "react";
import { useEffect, useRef, useState } from "react";
import { useFloatingOverlay } from "./_overlay";
import styles from "./Select.module.css";

/**
 * One choice: what the caller stores, and what the list shows.
 */
export interface SelectOption<T> {
  readonly value: T;
  readonly label: string;
}

/**
 * Properties for a dropdown.
 */
export interface SelectProps<T> {
  readonly value: T;
  readonly options: readonly SelectOption<T>[];
  readonly onChange: (value: T) => void;
  /** Names the control for assistive technology. */
  readonly label: string;
  /** Which edge the list aligns to; `end` for triggers near the right. */
  readonly align?: "start" | "end";
}

let nextId = 0;

/**
 * Renders the trigger and, while open, the list.
 */
export function Select<T extends string | number>(
  props: SelectProps<T>,
): React.JSX.Element {
  const { value, options, onChange, label, align = "start" } = props;
  const [open, setOpen] = useState(false);
  const [cursor, setCursor] = useState(0);
  const [id] = useState(() => `select-${(nextId += 1)}`);
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const list = useRef<HTMLUListElement>(null);
  const selected = options.findIndex((o) => o.value === value);

  const show = (): void => {
    setCursor(Math.max(0, selected));
    setOpen(true);
  };
  const close = (): void => {
    setOpen(false);
    trigger.current?.focus();
  };
  const choose = (index: number): void => {
    onChange(options[index].value);
    close();
  };

  useFloatingOverlay({
    open,
    onClose: close,
    overlayRef: root,
  });

  useEffect(() => {
    if (open) {
      list.current?.focus();
    }
  }, [open]);

  const onListKey = (e: React.KeyboardEvent<HTMLUListElement>): void => {
    const last = options.length - 1;
    const moves: Record<string, number> = {
      ArrowDown: Math.min(cursor + 1, last),
      ArrowUp: Math.max(cursor - 1, 0),
      Home: 0,
      End: last,
    };
    if (e.key in moves) {
      e.preventDefault();
      setCursor(moves[e.key]);
    } else if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      choose(cursor);
    } else if (e.key === "Escape") {
      // This layer only: the app's own Escape handling never sees it.
      e.preventDefault();
      e.stopPropagation();
      close();
    } else if (e.key === "Tab") {
      setOpen(false);
    }
  };

  return (
    <div className={styles.select} ref={root}>
      <button
        ref={trigger}
        type="button"
        className={styles.trigger}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={label}
        onClick={() => (open ? close() : show())}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown" || e.key === "ArrowUp") {
            e.preventDefault();
            show();
          }
        }}
      >
        {options[selected]?.label}
        <ChevronDown size={12} className={styles.caret} aria-hidden />
      </button>
      {open && (
        <ul
          ref={list}
          role="listbox"
          tabIndex={-1}
          aria-label={label}
          aria-activedescendant={`${id}-${cursor}`}
          className={`${styles.list} ${align === "end" ? styles.end : ""}`}
          onKeyDown={onListKey}
        >
          {options.map((o, i) => (
            <li
              key={String(o.value)}
              id={`${id}-${i}`}
              role="option"
              aria-selected={i === selected}
              className={`${styles.option} ${i === cursor ? styles.optionOn : ""}`}
              onMouseEnter={() => setCursor(i)}
              onClick={() => choose(i)}
            >
              {o.label}
              {i === selected && (
                <Check size={12} className={styles.check} aria-hidden />
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
