/**
 * Pointer-anchored menu for secondary actions (right-click).
 *
 * Positions itself at the pointer, clamped to the viewport, and closes on
 * any outside press, Escape, scroll, or resize. Knows nothing about what its
 * items do.
 */

import React, { useEffect, useLayoutEffect, useRef, useState } from 'react';
import styles from './ContextMenu.module.css';

/**
 * One menu row.
 */
export interface MenuItem {
  readonly label: string;
  readonly onSelect: () => void;
}

/** Keeps the menu this far from the viewport edge. */
const EDGE_PX = 8;

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
      setPosition({
        left: Math.min(x, window.innerWidth - rect.width - EDGE_PX),
        top: Math.min(y, window.innerHeight - rect.height - EDGE_PX),
      });
    }
  }, [x, y]);

  useEffect(() => {
    const onPointer = (e: PointerEvent): void => {
      if (!menu.current?.contains(e.target as Node)) {
        onClose();
      }
    };
    const onKey = (e: KeyboardEvent): void => {
      if (e.key === 'Escape') {
        e.stopPropagation();
        onClose();
      }
    };
    document.addEventListener('pointerdown', onPointer);
    document.addEventListener('keydown', onKey);
    window.addEventListener('scroll', onClose, true);
    window.addEventListener('resize', onClose);
    menu.current?.querySelector('button')?.focus();
    return () => {
      document.removeEventListener('pointerdown', onPointer);
      document.removeEventListener('keydown', onKey);
      window.removeEventListener('scroll', onClose, true);
      window.removeEventListener('resize', onClose);
    };
  }, [onClose]);

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
