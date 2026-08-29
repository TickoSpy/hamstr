<img src="resources/Hamstr-Logo.jpg" alt="hamstr" width="160" align="right" />

# hamstr

Self-hosted archiver and media server. Paste any link — a video, a podcast, a PDF, an image, or a web page — and it is downloaded, tagged, and kept locally. Videos come from [any site yt-dlp supports](https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md); web pages are stored as clean, ad-free reader copies you can read offline. Watch progress in real time, then browse, tag, read and stream your library from any browser or mobile device — no account required.

For a full walkthrough of the app's features, see **[README-APP.md](README-APP.md)**.

## Features

- Paste one or many URLs — YouTube, TikTok, Vimeo, SoundCloud, and hundreds more
- Playlists and channels (YouTube)
- **Archive web pages in a reader view** — ads, navigation and scripts stripped, images stored locally, so an archived page reads offline and makes zero outbound requests
- **Paywall fallback** — a gated article is automatically retried against archive.today and the Wayback Machine
- **Any file type** — PDFs, images, loose media files, text and archives are downloaded as-is
- **Automatic tagging** by category and format (mp3 → `audio` `mp3`, pdf → `text` `pdf`, gif → `images` `gif`, …)
- **iOS-Reader-style reading view** with adjustable text size, light/sepia/dark themes and saved reading position
- **Firefox extension** to archive the page you're reading exactly as your browser sees it — covers subscriptions you pay for, bot walls, and client-rendered pages (see [extension/README.md](extension/README.md))
- Live download progress via WebSocket
- Non-H.264 video (HEVC, AV1) is automatically re-encoded to H.264 for browser compatibility
- Missing thumbnails are extracted automatically from the middle of the video
- Stream video and audio directly in the browser
- Background audio queue with shuffle, skip, and previous — continues on lock screen via Media Session API
- Playlists — create, add and remove items, delete
- **Save any item for offline use** — the app installs as a PWA and a pinned item plays or reads with the server unreachable
- Tag-based filtering and full-text search
- Audio-only downloads (MP3 + OGG)
- Download files locally as MP4, MP3, or OGG
- **Sign in to sites from the app** — age-restricted, members-only and subscriber content, with the login running in your own browser
- Retry failed downloads
- Resume playback position across sessions
- iOS share-sheet integration via a simple JSON API

---

## Quick Start (Docker)

**Prerequisites:** Docker and Docker Compose, on an **x86_64** host with outbound internet access. (The backend image pulls a Deno binary that ships for x86_64 only, and the container installs yt-dlp on every start — see [Limitations](#limitations).)

```bash
git clone https://github.com/TickoSpy/hamstr.git
cd hamstr
cp .env.example .env
mkdir -p storage && sudo chown -R 1000:1000 storage   # the backend runs as uid 1000
docker compose up --build
```

Open **http://localhost** in your browser.

The first build takes a few minutes — the image downloads a statically-linked ffmpeg with full codec support and installs yt-dlp.

> **Tip:** To run in the background, use `docker compose up --build -d`. Logs: `docker compose logs -f`.

> **Skip the build:** `docker compose -f docker-compose.ghcr.yml up -d` pulls prebuilt images from GHCR instead. Use the normal file whenever you have local changes to compile.

---

## Security

**Read this before putting hamstr anywhere but a trusted network.**

The API is deliberately unauthenticated. Every route — browsing, streaming, queuing downloads, deleting items — is open to anyone who can reach the frontend port. The only exception is `/api/cookies/*` (the site-login routes), which requires the `ADMIN_TOKEN` header and is disabled entirely when no token is set; it fails closed, never open. On top of that, `CORS_ORIGIN_REGEX` defaults to `.*`, so any web page can talk to the API from your browser — that default exists because the browser extension posts from arbitrary origins.

That design is fine for what it was built for: a box on your own LAN holding media you already had. It is **not** fine on the open internet. Anyone who finds the port can wipe the library or use your server as a download proxy.

If you want it reachable from outside, put an authentication layer in front of it — mTLS, HTTP basic auth, an identity-aware proxy, or a VPN such as WireGuard or Tailscale. The `X-Api-Key` in the [Shortcuts section](#3-caddy-config-for-shortcuts) is checked by **Caddy**, not by hamstr; do not mistake it for application-level auth.

Set `ADMIN_TOKEN` (`openssl rand -hex 32`) in `.env` on each host if you use site logins. It is read from the environment by `docker-compose.yml`, so it never travels with a `git pull`. The cookie jars it protects live in `storage/cookies/` at mode 0600 and are your real session credentials for those sites — treat that directory like a password store, and note that any rsync of `storage/` copies them along.

## Limitations

- **x86_64 only.** `docker/backend.Dockerfile` downloads a Deno release built for x86_64; the build fails on ARM (Raspberry Pi, Apple Silicon).
- **Network required at container start.** `docker/entrypoint.sh` runs `pip install --pre "yt-dlp[default]"` on every boot, deliberately: stable yt-dlp releases trail YouTube's changes far enough to break downloads outright. The container starts anyway if that fails, using whatever version is baked into the image, so an air-gapped instance still runs — it just ages.
- **Storage must be owned by uid 1000.** The backend drops to `appuser`; a `storage/` owned by anyone else fails with permission errors that read like corruption.

---

## Updating

### Docker

Pull the latest code and rebuild:

```bash
git pull
docker compose up --build
```

The `--build` flag is required whenever `docker/backend.Dockerfile` changes (e.g. to pick up the static-ffmpeg update or a base image bump). Running without it reuses the cached image and will not pick up Dockerfile changes.

No data migration is needed — the SQLite database and `./storage` volume are preserved across rebuilds.

### Local development

```bash
git pull
make setup   # re-installs/updates Python and Node dependencies
```

---

## Deploying to a Server

### Requirements

- A Linux server with Docker and Docker Compose installed
- A domain name (or local hostname) pointing at the server
- Optional but recommended: a reverse proxy (Caddy or nginx) for HTTPS

### 1. Clone and start

```bash
git clone https://github.com/TickoSpy/hamstr.git /opt/hamstr
mkdir -p /opt/hamstr/storage
chown -R 1000:1000 /opt/hamstr/storage   # app runs as uid 1000
cd /opt/hamstr && docker compose up --build -d
```

The frontend is now reachable on **port 80** of the server. The backend API is internal-only.

### 2. Reverse proxy (recommended)

Put the app behind Caddy or nginx to get automatic HTTPS:

**Caddy** (`/etc/caddy/Caddyfile`):

```
hamstr.example.com {
    reverse_proxy localhost:80
}
```

**nginx** (`/etc/nginx/sites-available/hamstr`):

```nginx
server {
    listen 80;
    server_name hamstr.example.com;
    location / { proxy_pass http://localhost:80; }
}
```

Then run `certbot --nginx -d hamstr.example.com` for a free Let's Encrypt certificate.

### 3. Caddy config for Shortcuts

Skip this section if your instance is reachable without a client certificate — the Shortcut can then post straight to your normal hostname.

If you put the app behind mTLS (client-certificate auth), the share-sheet shortcut will fail: iOS Shortcuts cannot present a client certificate. The way around it is a second subdomain that exposes **only** the submit endpoint without mTLS, protected instead by a static API key.

**Generate a key:**

```bash
openssl rand -hex 32
```

**Add to your Caddyfile:**

```
links.example.com {
    @queue {
        method POST
        path /api/videos
        header X-Api-Key "REPLACE_WITH_YOUR_KEY"
    }

    handle @queue {
        reverse_proxy http://YOUR_SERVER_IP:80
    }

    handle {
        respond "Not found" 404
    }
}
```

Replace `YOUR_SERVER_IP` with your Docker server's IP and `REPLACE_WITH_YOUR_KEY` with the key you generated. Caddy reloads automatically (`caddy reload`). All other paths return 404; only authenticated POST requests to `/api/videos` are forwarded.

Note that **Caddy** is what checks `X-Api-Key` here — the app itself never sees the header and has no idea whether it was present. The key is worth exactly as much as the proxy rule in front of it.

Put the same key in the `X-Api-Key` header of your iOS Shortcut (see [Apple Shortcut API](README-APP.md#apple-shortcut-api)).

### 4. Deploying updates

```bash
ssh root@your-server "cd /opt/hamstr && git pull && docker compose up --build -d"
```

`--build` is required so Docker picks up any Dockerfile changes. Running without it reuses the cached image.

### 5. Migrating storage to a new server

```bash
# Stop the app on the old server to avoid mid-transfer DB writes
ssh root@old-server "cd /opt/hamstr && docker compose stop"

# Rsync everything across
rsync -av --progress root@old-server:/opt/hamstr/storage/ /opt/hamstr/storage/

# Fix permissions and start
chown -R 1000:1000 /opt/hamstr/storage
cd /opt/hamstr && docker compose up -d
```

### 6. Useful server commands

```bash
# Container status
docker compose ps

# Follow all logs
docker compose logs -f

# Backend logs only (last 50 lines)
docker compose logs backend --tail=50

# Restart backend without rebuild (e.g. after editing .env)
docker compose restart backend
```

### 7. Notes

- `storage/` (SQLite DB, downloads, cookie jars) is bind-mounted from the host, so it survives rebuilds and `docker compose down`.
- It must stay owned by uid 1000. After recreating it: `chown -R 1000:1000 /opt/hamstr/storage`.
- Site logins need their own `ADMIN_TOKEN` per host in `/opt/hamstr/.env` — see [Security](#security).
- Only the frontend is published, on port 80. The backend API is reachable only from inside the compose network.

---

## Configuration

All settings live in `.env` (copy `.env.example` to get started):

| Variable | Default | Description |
|---|---|---|
| `STORAGE_ROOT` | `storage` | Directory for videos, audio, thumbnails, and the database |
| `DATABASE_URL` | `sqlite+aiosqlite:///storage/hamstr.db` | Database connection string |
| `DOWNLOAD_WORKERS` | `1` | Concurrent download workers |
| `MAX_CONCURRENT_FFMPEG` | `2` | Concurrent ffmpeg transcoding processes |
| `ADMIN_TOKEN` | _(unset)_ | Unlocks the site-login routes (`/api/cookies/*`). Unset disables them; it never leaves them open |
| `YT_COOKIES_FILE` | _(unset)_ | Manual override for the cookie jar handed to yt-dlp. Normally unset — the app maintains its own |
| `LOG_LEVEL` | `info` | Uvicorn log level (`debug`, `info`, `warning`, `error`) |
| `ARCHIVE_ENABLED` | `true` | Try archive.today / the Wayback Machine when a page turns out to be paywalled |
| `INGEST_TRY_YTDLP_ON_HTML` | `false` | Hand ordinary HTML pages to yt-dlp's generic extractor before archiving them. Slow |
| `MAX_ARTICLE_BYTES` | `10485760` | Largest page body accepted for archiving |
| `MAX_ARTICLE_IMAGES` | `40` | Images stored per archived page |
| `MAX_FILE_BYTES` | `2147483648` | Largest plain file download |
| `CORS_ORIGIN_REGEX` | `.*` | Origins allowed to call the API. Wide open so the browser extension can post a capture from any page; set to a pattern (or unset, leaving `CORS_ORIGINS`) to restrict it |

These are the settings worth changing. The full list, including the remaining
archive-ingest limits and timeouts, is `backend/app/config.py` — every field there
is settable as an environment variable of the same name in upper case.

After editing `.env`, restart the stack: `docker compose restart backend`.

### Storage layout

All downloaded files go into `./storage/` (bind-mounted into the container):

```
storage/
├── videos/{item_id}/video.mp4
│                    video.jpg      ← thumbnail, when yt-dlp supplied one
├── audio/{item_id}/audio.mp3
│                   audio.ogg
│                   audio.jpg
├── thumbnails/{item_id}/…          ← yt-dlp's download target, and the
│                                     thumb.jpg ffmpeg extracts as a fallback
├── articles/{item_id}/article.html ← reader copy
│                      raw.html     ← the page as fetched
│                      captured.html← extension capture, before processing
│                      assets/      ← images, stored locally
├── files/{item_id}/{original filename}
├── cookies/{domain}.txt ← one jar per signed-in site, mode 0600
│           merged.txt   ← all of them, the file yt-dlp is handed
└── hamstr.db                ← SQLite database
```

`{item_id}` is the site-native identifier returned by yt-dlp for anything yt-dlp
handles (e.g. `dQw4w9WgXcQ` for YouTube, `7558818573813075255` for TikTok).
Archived pages and plain file downloads have no such id, so they get a
deterministic hash of the canonical URL instead: `web_…` for a page, `dl_…` for a
file (`backend/app/services/ingest/ids.py`). Re-submitting the same URL therefore
lands on the same item rather than duplicating it.

---

## Signing In to Sites

Some content needs an account: age-restricted YouTube videos, members-only
uploads, anything behind a subscription. The archive signs in from **Settings →
Site logins**, and the login itself happens in your own browser.

### Why it works this way

A web page cannot read another origin's cookies, and there is no OAuth flow that
yields the session tokens yt-dlp needs — Google removed the one yt-dlp had. The
only component holding a real cookie jar is the [Firefox
extension](extension/README.md), so it performs the login and hands the result to
the backend. The server never sees a password, and adding a login is impossible
without the extension. There is no upload or paste fallback, by design.

### Setup

1. Set a token on the backend — this is the one part of the API that is gated,
   because a stored jar is a live session:

   ```bash
   echo "ADMIN_TOKEN=$(openssl rand -hex 32)" >> .env
   docker compose up -d
   ```

   Leaving it unset disables the login routes entirely. They never fall back to
   being open.

2. Install the extension (see [extension/README.md](extension/README.md)), put
   the same token in its options next to the archive address, and **press Save**.
   **Test** verifies both the address and the token. Grant the add-on host
   permissions too — Firefox withholds them from a temporarily-loaded MV3 add-on,
   and cookie reads then return nothing rather than failing.

3. Paste the token into **Settings → Site logins** in the app as well, so the
   page can read back which sites are signed in.

### Signing in

Pick a site (`youtube.com` is the default) and press **Log in**. The extension
opens that site's login in a dedicated Firefox container called *Archive login*.
Sign in there; the session is picked up and stored automatically, and the tab
closes itself.

> **Use a throwaway account.** Automated access can get an account flagged, and
> the archive holds a live session for whatever account you use.

**Why a container, and why it is never logged out of:** cookies taken from a
session you keep using are rotated constantly, and the exported copy dies within
hours. An untouched container keeps them valid for weeks. This is also why the
extension closes the tab instead of signing out — signing out is what kills the
stored jar.

### What is stored

`storage/cookies/{domain}.txt`, one Netscape jar per site at mode `0600`, merged
into `cookies/merged.txt` — the single `cookiefile` yt-dlp is given. It only
sends the cookies matching each request's domain, exactly as a browser would.

No route ever returns a cookie name or value. The app can tell you a jar has 24
cookies and expires in 41 days; it cannot show you the jar. Nothing is logged
either.

### Refreshing and removing

Each site card has **Refresh** — re-reads the container without a new login, for
when a jar goes stale — and a bin icon that deletes it. Deleting only removes the
server's copy; the container keeps its session, so Refresh brings it straight
back.

### Manual override

`YT_COOKIES_FILE` still works and takes precedence, for a cookies file you export
and manage yourself:

```bash
yt-dlp --cookies-from-browser firefox --cookies storage/cookies.txt <any-url>
```

Under Docker the file must live inside the `./storage/` bind-mount.

---

## Local Development

**Prerequisites:** Python 3.12+, Node 22+, ffmpeg with H.264 and HEVC support.

```bash
make setup   # create venv + npm install
make dev     # backend on :8000, frontend on :5173
```

Open **http://localhost:5173**.

The Vite dev server proxies `/api`, `/stream`, and `/ws` to the FastAPI backend.

### ffmpeg requirement

The app uses ffmpeg for three things: audio extraction (MP3/OGG), post-download H.264 re-encoding, and fallback thumbnail extraction. All three require a full-featured ffmpeg build.

**Linux distributions that ship a codec-restricted ffmpeg** (e.g. Fedora's `ffmpeg-free`) will silently skip the H.264 re-encoding step, leaving HEVC videos unplayable in Firefox. Install the full build:

```bash
# Fedora — requires RPM Fusion Non-Free
sudo dnf install https://mirrors.rpmfusion.org/nonfree/fedora/rpmfusion-nonfree-release-$(rpm -E %fedora).noarch.rpm
sudo dnf swap ffmpeg-free ffmpeg --allowerasing

# Ubuntu/Debian
sudo apt install ffmpeg   # the standard package includes H.264 support
```

To manually re-encode a video that was downloaded before the full ffmpeg was in place:

```bash
id=<video_id>
ffmpeg -i storage/videos/$id/video.mp4 \
  -c:v libx264 -preset fast -crf 23 -pix_fmt yuv420p \
  -c:a aac -movflags +faststart /tmp/v.mp4 \
  && mv /tmp/v.mp4 storage/videos/$id/video.mp4
```

### Useful commands

| Command | Description |
|---|---|
| `make dev` | Start backend + frontend |
| `make dev-backend` | Backend only |
| `make dev-frontend` | Frontend only |
| `make test` | Run backend tests |
| `make lint` | Ruff + ESLint |
| `make build` | Build frontend for production |
| `make docker-up` | Build and start Docker stack |
| `make docker-down` | Stop Docker stack |
| `make clean` | Remove venv, node_modules, dist |

---

## Architecture

```
Browser
  │
  ├── GET /          → nginx (or Vite dev server) serves React SPA
  ├── /api/*         → FastAPI (CRUD, submit, tags, playlists)
  ├── /stream/*      → FastAPI FileResponse (video, audio, thumbnails)
  └── /ws            → FastAPI WebSocket (real-time progress)

Backend
  ├── SQLite (aiosqlite)  — video metadata, tags, playlists
  ├── asyncio.Queue       — download job queue
  ├── yt-dlp              — info extraction and video download
  └── ffmpeg              — H.264 re-encoding, audio extraction, thumbnails

Storage (bind-mounted volume)
  └── ./storage/          — videos, audio, thumbnails, database
```

### Processing pipeline

For each submitted URL:

1. **Extract** — yt-dlp resolves the URL and returns one or more `(id, url, title, channel, duration)` tuples. YouTube single-video URLs use a fast path; playlists and all other sites go through the full yt-dlp extractor.
2. **Download** — yt-dlp downloads the best available quality. Format preference: H.264 MP4 first, then any MP4, then best available.
3. **Re-encode** — if the video codec is not H.264 (e.g. HEVC from TikTok, AV1 from YouTube), ffmpeg re-encodes to H.264/AAC with `yuv420p` pixel format for universal browser compatibility.
4. **Thumbnail** — yt-dlp writes a thumbnail when available. If none was downloaded, ffmpeg extracts a frame from the midpoint of the video.
5. **Audio** — ffmpeg extracts audio tracks as MP3 and OGG for background playback.

### WebSocket events

```json
{"type": "progress",        "video_id": "...", "progress": 45.2, "status": "downloading"}
{"type": "status_change",   "video_id": "...", "status": "processing"}
{"type": "completed",       "video_id": "...", "title": "...",    "status": "completed"}
{"type": "error",           "video_id": "...", "error": "...",    "status": "error"}
{"type": "transcoding",     "video_id": "...", "codec": "transcoding"}
{"type": "transcoded",      "video_id": "...", "codec": "h264",   "file_size_bytes": 12345678}
{"type": "transcode_error", "video_id": "..."}
{"type": "transcode_queued",   "video_id": "..."}
{"type": "transcode_dequeued", "video_id": "..."}
```

The last two come from the bulk **Fix All Codecs** run: a video whose stored codec
is already known to be wrong is announced as queued straight away, and dequeued
again if codec detection then finds the file was fine after all.

---

## Troubleshooting

### "Could not load video" in the browser

The video was downloaded in a codec the browser cannot play (typically HEVC/H.265 from TikTok).

**Docker:** Rebuild the image — the current Dockerfile uses a statically-linked ffmpeg with full codec support that re-encodes HEVC to H.264 automatically:
```bash
docker compose up --build
```
Then delete the affected video from the library and re-submit its URL.

**Local dev:** Make sure you have a full-featured ffmpeg (see [ffmpeg requirement](#ffmpeg-requirement) above). Then re-encode the existing file manually or delete and re-download.

### "Could not load video" after deleting a video

If a video was playing in the background player when you deleted it, the player now stops automatically. If you see this on a video that still exists in the library, see the codec issue above.

### Download fails with "Sign in to confirm your age"

The archive is not signed in to YouTube. See [Signing In to Sites](#signing-in-to-sites).

### A login works in the browser but the download still fails

If the same account plays the video in your own browser, the login is not the
problem. YouTube pushes age-restricted videos onto its web clients, whose
formats are locked behind a signature challenge that yt-dlp can only solve with
a JavaScript runtime — the backend image ships Deno for exactly this. Without
one, the cookies get past the age gate and every real format is then missing,
which surfaces as "Sorry, this content is age-restricted". Ordinary videos use
a different client and never needed it, so the gap only appears once a login is
in play.

Those clients' high-quality formats also want a PO token the app does not
supply, so an age-restricted video tops out at the 480p HLS ladder from
`web_safari` rather than the 4K an unrestricted one reaches.

### A login stopped working

Sessions do expire. Press **Refresh** on the site's card in Settings — it re-reads
the container without a new sign-in. If that doesn't help, the container's session
is gone too: **Log in** again. Nothing needs a restart.

Logins go stale fastest when the container has been used for ordinary browsing, or
when the account was signed out elsewhere.

### "Site logins are disabled on the backend"

`ADMIN_TOKEN` is unset. Set it and restart — the routes fail closed rather than
running unguarded.

### Video plays but shows "file is corrupt" at the end

Known Firefox quirk — Firefox issues a range request past EOF after a video ends and treats the 416 response as corruption. The app handles this silently and advances to the next track.

### Port 80 is already in use

Change the port in `docker-compose.yml`:

```yaml
ports:
  - "8080:80"
```

Then open **http://localhost:8080**.

### Backend port 8000 is not accessible from the host

Intentional. In the Docker stack the backend only listens on the internal Docker network — all requests go through nginx. For direct API access during development use `make dev-backend`.

### Storage directory permission errors

The backend runs as UID 1000 inside the container. If you see permission errors on `./storage`:

```bash
sudo chown -R 1000:1000 ./storage
```

### yt-dlp is out of date

The container upgrades yt-dlp on every start (`docker/entrypoint.sh`), from the
**nightly** channel — `pip install --pre "yt-dlp[default]"`. Stable releases lag
YouTube's changes by weeks: in August 2026 the newest stable, 2026.07.04, fell
back to a client whose media URLs YouTube answers with **HTTP 403**, so every
YouTube download failed while the nightly worked. If a download fails because of
a site change and you cannot wait, force a restart to pull today's build:

```bash
docker compose restart backend
```

### Cancel a runaway download queue (edit the DB while the backend is down)

Submitting a search term (or a huge playlist) can queue hundreds of downloads. **You cannot fix this by just stopping and starting the backend** — on startup `lifespan` re-queues every row whose status is `pending`, `downloading`, or `processing` (`backend/app/main.py`), and `restart: unless-stopped` means the backend comes back on its own whenever the host boots. The queue must be emptied *while the backend is stopped*.

The queue lives in the `videos` table of the SQLite DB at `storage/hamstr.db`. The "queue" is every row with status `pending` / `downloading` / `processing`; `completed` rows are the Library and must be kept.

```bash
cd /opt/hamstr                                   # deploy dir on the server

# 1. Stop ONLY the backend (leave the DB file quiescent). Do not `up -d` /
#    restart it until step 3, or it will re-queue everything.
docker compose stop backend

# 2. Back up, then delete the queued rows (keeps completed videos).
cp storage/hamstr.db storage/hamstr.db.bak-$(date +%Y%m%d-%H%M%S)
sqlite3 storage/hamstr.db \
  "PRAGMA foreign_keys=ON;
   DELETE FROM videos WHERE status IN ('pending','downloading','processing');"
# PRAGMA foreign_keys=ON is what makes the tags and playlist_items rows go with
# them — SQLite ignores ON DELETE CASCADE without it, per connection, and rows
# left pointing at a deleted item used to break the playlist they sat in.
# No sqlite3 on the host? python3 has it built in:
#   python3 -c "import sqlite3;c=sqlite3.connect('storage/hamstr.db');\
#   c.execute('PRAGMA foreign_keys=ON');\
#   c.execute(\"DELETE FROM videos WHERE status IN ('pending','downloading','processing')\");c.commit()"

# 3. Optional: remove the partial file left by the download that was in flight.
find storage/videos storage/audio -type f \
  \( -name '*.part' -o -name '*.ytdl' \) -print -delete

# 4. Bring the backend back — it now finds an empty queue.
docker compose start backend
```

Verify nothing was re-queued: the fresh boot log must **not** contain a `Re-queued N interrupted download(s)` line, and
`curl -s 'http://localhost/api/videos?status=pending,downloading,processing'` should return `{"items":[],"total":0}`.

**If the whole host is offline** (e.g. the app runs in an LXC/VM that was stopped to halt the downloads), start the guest first, then immediately `docker compose stop backend` before it finishes booting, do the DB edit, and only then `start backend` — otherwise the auto-started backend re-queues the batch during the window.

---

## Legal

hamstr is a personal archiving tool. It downloads with yt-dlp, stores site cookies you supply so it can fetch content your own accounts have access to, and falls back to archive.today and the Wayback Machine for gated articles. What it can technically fetch and what you are allowed to fetch are two different questions.

- Use it for content you have the right to keep — your own uploads, public-domain and openly licensed material, media you have paid for, and personal copies where your jurisdiction's private-copying rules allow it.
- Respect the terms of service of the sites you point it at. Many forbid automated downloading, and some forbid it in the same breath as your subscription.
- The cookie jars under `storage/cookies/` are your credentials. Sharing an instance means sharing the sessions it holds.
- Redistributing what you archive is a separate act from archiving it, and copyright applies to it in full.

The authors provide this software as-is under the [MIT License](LICENSE) and take no responsibility for how it is used.
