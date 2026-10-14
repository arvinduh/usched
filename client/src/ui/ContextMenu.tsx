/**
 * Pointer-anchored menu for secondary actions (right-click).
 *
 * Positions itself at the pointer, clamped to the viewport, and closes on
 * any outside press, Escape, scroll, or resize. Knows nothing about what its
 * items do.
 */

import type React from "react";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { clampToViewport, useFloatingOverlay } from "./_overlay";
import styles from "./ContextMenu.module.css";

/**
 * One menu row.
 */
export interface MenuItem {
  readonly label: string;
  readonly onSelect: () => void;
}

/**
 * Renders the menu at viewport coordinates (`x`, `y`).
 */
export function ContextMenu({
  x,
  y,
  items,
  onClose,
}: {
  readonly x: number;
  readonly y: number;
  readonly items: readonly MenuItem[];
  readonly onClose: () => void;
}): React.JSX.Element {
  const menu = useRef<HTMLDivElement>(null);
  const [position, setPosition] = useState({ left: x, top: y });

  // Measure once mounted and pull the menu back inside the viewport.
  useLayoutEffect(() => {
    const rect = menu.current?.getBoundingClientRect();
    if (rect) {
      setPosition(clampToViewport(x, y, rect));
    }
  }, [x, y]);

  useFloatingOverlay({
    open: true,
    onClose,
    overlayRef: menu,
    closeOnScroll: true,
    closeOnResize: true,
  });

  useEffect(() => {
    menu.current?.querySelector("button")?.focus();
  }, []);

  return (
    <div ref={menu} className={styles.menu} style={position} role="menu">
      {items.map((item) => (
        <button
          key={item.label}
          type="button"
          role="menuitem"
          className={styles.item}
          onClick={() => {
            item.onSelect();
            onClose();
          }}
        >
          {item.label}
        </button>
      ))}
    </div>
  );
}
