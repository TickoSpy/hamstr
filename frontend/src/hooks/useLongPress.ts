import { useRef, useCallback, useEffect } from "react";
import type { PointerEvent as ReactPointerEvent, MouseEvent as ReactMouseEvent } from "react";

const MOVE_TOLERANCE = 10; // px of finger drift allowed before it's treated as a scroll

/**
 * Opens a context menu from either a touch long-press or a desktop right-click.
 *
 * Touch/pen: hold for `ms` without scrolling. Uses Pointer Events (not Touch
 * Events) so the same handlers cover mouse/pen, and pairs with onContextMenu so
 * desktop users right-click instead of awkwardly holding the mouse button.
 */
export function useLongPress(callback: () => void, ms = 500) {
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const start = useRef<{ x: number; y: number } | null>(null);
  const fired = useRef(false);
  const expire = useRef<ReturnType<typeof setTimeout> | null>(null);

  const disarm = useCallback(() => {
    if (expire.current !== null) {
      clearTimeout(expire.current);
      expire.current = null;
    }
    fired.current = false;
  }, []);

  const clear = useCallback(() => {
    if (timer.current !== null) {
      clearTimeout(timer.current);
      timer.current = null;
    }
  }, []);

  const onPointerDown = useCallback((e: ReactPointerEvent) => {
    fired.current = false;
    // Desktop uses right-click (onContextMenu); don't hijack a held left button.
    if (e.pointerType === "mouse") return;
    start.current = { x: e.clientX, y: e.clientY };
    timer.current = setTimeout(() => {
      fired.current = true;
      callback();
    }, ms);
  }, [callback, ms]);

  const onPointerMove = useCallback((e: ReactPointerEvent) => {
    const s = start.current;
    if (!s) return;
    if (Math.abs(e.clientX - s.x) > MOVE_TOLERANCE || Math.abs(e.clientY - s.y) > MOVE_TOLERANCE) {
      clear();
    }
  }, [clear]);

  const onPointerUp = useCallback(() => {
    clear();
    // The release after a long-press synthesizes a click that onClickCapture
    // below has to swallow — but iOS often withholds that click entirely,
    // because the menu that just opened is now under the finger. The guard
    // then stayed armed and ate the user's *next* real tap instead: every
    // button in the sheet, delete included, needed two taps, the first only
    // lighting the row up. Let it expire on its own.
    if (fired.current) {
      if (expire.current !== null) clearTimeout(expire.current);
      expire.current = setTimeout(disarm, 400);
    }
  }, [clear, disarm]);

  const onPointerCancel = useCallback(() => {
    clear();
    disarm();
  }, [clear, disarm]);

  // Right-click / trackpad secondary-click opens the same menu on desktop.
  const onContextMenu = useCallback((e: ReactMouseEvent) => {
    e.preventDefault();
    callback();
  }, [callback]);

  // A touch long-press synthesizes a click on release; swallow it so the card's
  // own onClick (play) doesn't fire the instant the menu opens.
  const onClickCapture = useCallback((e: ReactMouseEvent) => {
    if (fired.current) {
      e.preventDefault();
      e.stopPropagation();
      disarm();
    }
  }, [disarm]);

  // Don't leave either timer running past unmount.
  useEffect(() => () => { clear(); disarm(); }, [clear, disarm]);

  return { onPointerDown, onPointerMove, onPointerUp, onPointerCancel, onContextMenu, onClickCapture };
}
