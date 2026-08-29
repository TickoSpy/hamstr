import type { Video } from "@/lib/api";

const STREAMS_CACHE = "yt-streams-v1";

// Everything the app fetches to present an item offline — the player's sources
// for media, the reader's HTML for articles, the raw artifact for everything else.
function playbackUrls(video: Video): string[] {
  const urls: string[] = [];
  if (video.thumbnail_path) urls.push(`/stream/${video.id}/thumbnail`);
  if (video.audio_mp3_path)  urls.push(`/stream/${video.id}/audio/mp3`);
  else if (video.video_path) urls.push(`/stream/${video.id}/video`);

  if (video.article_html_path) urls.push(`/stream/${video.id}/article`);
  else if (video.raw_html_path) urls.push(`/stream/${video.id}/article?raw=1`);

  // Article assets are pinned individually below; file-backed kinds pin the file.
  if (video.file_path && !video.video_path && !video.audio_mp3_path && video.kind !== "article") {
    urls.push(`/stream/${video.id}/file`);
  }

  const assets = video.extra?.assets;
  if (Array.isArray(assets)) {
    for (const name of assets) {
      if (typeof name === "string") urls.push(`/stream/${video.id}/asset/${name}`);
    }
  }
  return urls;
}

export async function pinVideo(video: Video): Promise<void> {
  const cache = await caches.open(STREAMS_CACHE);
  await Promise.all(
    playbackUrls(video).map(async (url) => {
      try {
        const res = await fetch(url);
        if (res.ok) await cache.put(url, res);
      } catch {
        // One missing asset shouldn't fail the whole pin.
      }
    })
  );
}

export async function unpinVideo(videoId: string): Promise<void> {
  const cache = await caches.open(STREAMS_CACHE);
  const keys  = await cache.keys();
  await Promise.all(
    keys
      .filter(req => new URL(req.url).pathname.startsWith(`/stream/${videoId}/`))
      .map(req  => cache.delete(req))
  );
}

export async function getCachedVideoIds(): Promise<Set<string>> {
  const cache = await caches.open(STREAMS_CACHE);
  const keys  = await cache.keys();
  const ids   = new Set<string>();
  for (const req of keys) {
    const m = new URL(req.url).pathname.match(/^\/stream\/([^/]+)\//);
    if (m) ids.add(m[1]);
  }
  return ids;
}

export async function getStorageInfo(): Promise<{ used: number; quota: number } | null> {
  if (!navigator.storage?.estimate) return null;
  const { usage, quota } = await navigator.storage.estimate();
  return { used: usage ?? 0, quota: quota ?? 0 };
}

export function isOfflineSupported(): boolean {
  return "serviceWorker" in navigator && "caches" in window;
}
