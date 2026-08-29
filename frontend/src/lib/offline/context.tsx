import {
  createContext, useContext, useState, useEffect, useCallback,
  type ReactNode,
} from "react";
import type { Video } from "@/lib/api";
import {
  pinVideo, unpinVideo, getCachedVideoIds,
  getStorageInfo, isOfflineSupported,
} from "./cache";

interface StorageInfo { used: number; quota: number; }

interface OfflineCtx {
  supported:   boolean;
  cachedIds:   Set<string>;   // video IDs with a local offline copy
  pinning:     Set<string>;   // video IDs currently being downloaded
  storageInfo: StorageInfo | null;
  pin:         (video: Video) => Promise<void>;
  unpin:       (videoId: string) => Promise<void>;
}

const OfflineContext = createContext<OfflineCtx | null>(null);

export function useOffline(): OfflineCtx {
  const ctx = useContext(OfflineContext);
  if (!ctx) throw new Error("useOffline must be used inside OfflineProvider");
  return ctx;
}

export function OfflineProvider({ children }: { children: ReactNode }) {
  const supported = isOfflineSupported();
  const [cachedIds,   setCachedIds]   = useState<Set<string>>(new Set());
  const [pinning,     setPinning]     = useState<Set<string>>(new Set());
  const [storageInfo, setStorageInfo] = useState<StorageInfo | null>(null);

  const refreshStorage = useCallback(async () => {
    setStorageInfo(await getStorageInfo());
  }, []);

  useEffect(() => {
    if (!supported) return;
    getCachedVideoIds().then(setCachedIds);
    refreshStorage();
  }, [supported, refreshStorage]);

  const pin = useCallback(async (video: Video) => {
    if (pinning.has(video.id) || cachedIds.has(video.id)) return;
    setPinning(prev => new Set([...prev, video.id]));
    try {
      await pinVideo(video);
      setCachedIds(prev => new Set([...prev, video.id]));
    } finally {
      setPinning(prev => { const s = new Set(prev); s.delete(video.id); return s; });
      refreshStorage();
    }
  }, [pinning, cachedIds, refreshStorage]);

  const unpin = useCallback(async (videoId: string) => {
    await unpinVideo(videoId);
    setCachedIds(prev => { const s = new Set(prev); s.delete(videoId); return s; });
    refreshStorage();
  }, [refreshStorage]);

  return (
    <OfflineContext.Provider value={{ supported, cachedIds, pinning, storageInfo, pin, unpin }}>
      {children}
    </OfflineContext.Provider>
  );
}
