// Service worker for offline playback.
// Scope: intercepts /stream/* fetch requests and serves from cache when available.
// Caching itself is managed by the main thread via the Cache API (lib/offline/cache.ts).

const STREAMS_CACHE = "yt-streams-v1";

// Take effect immediately when a new SW version is deployed.
self.addEventListener("install", () => self.skipWaiting());

// Clean up caches from any previous SW version, then claim all open tabs.
self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(
        keys.filter(k => k !== STREAMS_CACHE).map(k => caches.delete(k))
      ))
      .then(() => self.clients.claim())
  );
});

// Only intercept stream requests; everything else (API, static assets) passes through.
self.addEventListener("fetch", (event) => {
  const { pathname } = new URL(event.request.url);
  if (pathname.startsWith("/stream/")) {
    event.respondWith(serveStream(event.request));
  }
});

async function serveStream(request) {
  const cache  = await caches.open(STREAMS_CACHE);
  const cached = await cache.match(request.url);
  if (!cached) return fetch(request);   // not pinned — hit the network normally

  // Reconstruct a 206 Partial Content response so video/audio seeking works offline.
  const rangeHeader = request.headers.get("Range");
  if (!rangeHeader) return cached;

  const buffer = await cached.arrayBuffer();
  const total  = buffer.byteLength;
  const [, startStr, endStr] = rangeHeader.match(/bytes=(\d+)-(\d*)/) ?? [];
  const start  = parseInt(startStr ?? "0", 10);
  const end    = endStr ? parseInt(endStr, 10) : total - 1;

  return new Response(buffer.slice(start, end + 1), {
    status: 206,
    headers: {
      "Content-Type":  cached.headers.get("Content-Type") ?? "application/octet-stream",
      "Content-Range": `bytes ${start}-${end}/${total}`,
      "Content-Length": String(end - start + 1),
      "Accept-Ranges": "bytes",
    },
  });
}
