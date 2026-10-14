/**
 * Reusable floating overlay dismiss and boundary clamping helpers.
 *
 * Provides shared viewport clamping math and document event listener
 * management for floating UI primitives (ContextMenu, Select, TopBar menus).
 */

import type React from "react";
import { useEffect } from "react";

/** Keeps overlays this far from viewport edges by default. */
export const DEFAULT_VIEWPORT_PADDING = 8;

/** Clamped 2D screen coordinates. */
export interface ClampedPosition {
  readonly left: number;
  readonly top: number;
}

/**
 * Clamps coordinates to keep an element with given dimensions fully within the viewport.
 */
export function clampToViewport(
  x: number,
  y: number,
  rect: { readonly width: number; readonly height: number },
  padding: number = DEFAULT_VIEWPORT_PADDING,
): ClampedPosition {
  const maxLeft = Math.max(padding, window.innerWidth - rect.width - padding);
  const maxTop = Math.max(padding, window.innerHeight - rect.height - padding);
  const left = Math.min(Math.max(padding, x), maxLeft);
  const top = Math.min(Math.max(padding, y), maxTop);
  return { left, top };
}

/**
 * Options for floating overlay lifecycle and outside-click/escape dismissal.
 */
export interface FloatingOverlayOptions {
  readonly open: boolean;
  readonly onClose: () => void;
  readonly overlayRef: React.RefObject<HTMLElement | null>;
  readonly triggerRef?: React.RefObject<HTMLElement | null>;
  readonly closeOnScroll?: boolean;
  readonly closeOnResize?: boolean;
}

/**
 * Manages document listeners for outside pointer dismiss and Escape key dismiss.
 * Safely stops propagation on Escape so outer handlers don't catch the event.
 */
export function useFloatingOverlay(options: FloatingOverlayOptions): void {
  const {
    open,
    onClose,
    overlayRef,
    triggerRef,
    closeOnScroll = false,
    closeOnResize = false,
  } = options;

  useEffect(() => {
    if (!open) {
      return;
    }

    const onPointer = (e: PointerEvent): void => {
      const target = e.target as Node | null;
      if (!target) {
        return;
      }
      if (overlayRef.current?.contains(target)) {
        return;
      }
      if (triggerRef?.current?.contains(target)) {
        return;
      }
      onClose();
    };

    const onKey = (e: KeyboardEvent): void => {
      if (e.key === "Escape") {
        e.stopPropagation();
        onClose();
      }
    };

    document.addEventListener("pointerdown", onPointer);
    document.addEventListener("keydown", onKey);

    if (closeOnScroll) {
      window.addEventListener("scroll", onClose, true);
    }
    if (closeOnResize) {
      window.addEventListener("resize", onClose);
    }

    return () => {
      document.removeEventListener("pointerdown", onPointer);
      document.removeEventListener("keydown", onKey);
      if (closeOnScroll) {
        window.removeEventListener("scroll", onClose, true);
      }
      if (closeOnResize) {
        window.removeEventListener("resize", onClose);
      }
    };
  }, [open, onClose, overlayRef, triggerRef, closeOnScroll, closeOnResize]);
}
