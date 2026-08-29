import { useState, useEffect, useRef } from "react";

/**
 * Returns true when the NavBar should be visible.
 * Hides after scrolling down >5 px, reappears when scrolling up or near the top.
 */
export function useNavScroll(): boolean {
  const [visible, setVisible] = useState(true);
  const lastY = useRef(0);

  useEffect(() => {
    const NAV_H = 56; // h-14 = 3.5rem
    const onScroll = () => {
      const y = window.scrollY;
      const atBottom = y + window.innerHeight >= document.documentElement.scrollHeight - 10;
      if (y < NAV_H) {
        setVisible(true);
      } else if (!atBottom && y < lastY.current - 5) {
        setVisible(true);   // scrolling up (ignore iOS rubber-band bounce at page bottom)
      } else if (y > lastY.current + 5) {
        setVisible(false);  // scrolling down
      }
      lastY.current = y;
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return visible;
}
