import { useCallback, useState } from "react";
import { saveFile } from "@/lib/download";

/**
 * Wraps saveFile with the bit of state the buttons need: which href is being
 * fetched (the share sheet only appears once the whole file is in memory, so
 * without this the button looks dead for several seconds) and the last error.
 */
export function useSaveFile() {
  const [savingHref, setSavingHref] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const save = useCallback(async (href: string, fallbackName: string) => {
    setError(null);
    setSavingHref(href);
    try {
      await saveFile(href, fallbackName);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save the file");
    } finally {
      setSavingHref(null);
    }
  }, []);

  return { save, savingHref, error };
}
