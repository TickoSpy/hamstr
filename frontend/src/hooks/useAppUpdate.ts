import { useCallback, useEffect, useState } from "react";

/**
 * Detects that a newer build has been deployed while the app is open.
 *
 * Nothing else does: the service worker only intercepts /stream/*, so the app
 * shell is never revalidated on its own, and an installed PWA is suspended
 * rather than reloaded — which meant a deploy was only picked up by quitting and
 * relaunching. We compare the hashed bundle name in the freshly-fetched
 * index.html against the one this session actually loaded.
 */
const CHECK_INTERVAL_MS = 5 * 60_000;
const BUNDLE_RE = /<script[^>]+src="(\/assets\/[^"]+\.js)"/;

function currentBundle(): string | null {
  const el = document.querySelector<HTMLScriptElement>(
    'script[type="module"][src^="/assets/"]',
  );
  if (!el) return null;
  return new URL(el.src, location.origin).pathname;
}

async function deployedBundle(): Promise<string | null> {
  const res = await fetch("/index.html", { cache: "no-store" });
  if (!res.ok) return null;
  return BUNDLE_RE.exec(await res.text())?.[1] ?? null;
}

export function useAppUpdate() {
  const [updateReady, setUpdateReady] = useState(false);

  const check = useCallback(async () => {
    // In dev the entry is /src/main.tsx, so there is nothing to compare.
    const mine = currentBundle();
    if (!mine || updateReady) return;
    try {
      const latest = await deployedBundle();
      if (latest && latest !== mine) setUpdateReady(true);
    } catch {
      // Offline or the server is mid-restart; try again on the next tick.
    }
  }, [updateReady]);

  useEffect(() => {
    const onVisible = () => {
      if (document.visibilityState === "visible") void check();
    };
    // Returning to a suspended PWA is the moment that matters most.
    document.addEventListener("visibilitychange", onVisible);
    window.addEventListener("focus", onVisible);
    const timer = setInterval(() => void check(), CHECK_INTERVAL_MS);
    void check();
    return () => {
      document.removeEventListener("visibilitychange", onVisible);
      window.removeEventListener("focus", onVisible);
      clearInterval(timer);
    };
  }, [check]);

  const reload = useCallback(() => {
    location.reload();
  }, []);

  return { updateReady, reload };
}
