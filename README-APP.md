# Using the App

A walkthrough of every feature in the app.

---

## Pages

The nav bar at the top has three pages — **Queue**, **Library** and
**Playlists** — plus **Settings** on the right.

---

## Queue

Where you submit URLs to download.

### Adding links

Paste one or more URLs into the text box and press **Add to Archive**. The app works out what each link is and picks the right handler:

| You paste | What you get |
|---|---|
| A video URL (YouTube, TikTok, Vimeo, SoundCloud, …) | The video, via yt-dlp |
| A YouTube playlist or channel | Every video in the list, queued at once |
| A link to a `.pdf`, `.mp3`, `.gif`, `.png`, `.txt`, `.zip`, … | The file itself, downloaded as-is |
| Any other web page | A **reader-view copy** of the article — see below |

Links are classified from the URL alone where possible; only ambiguous ones cost a single `HEAD` request. Each queued item shows a live progress bar, then appears in the Library once complete.

### Archiving web pages

A pasted article URL is fetched, run through a readability extractor, and stored as a clean reader copy: no ads, no navigation, no scripts, no trackers. Its images are downloaded alongside it, so **reading an archived page makes zero outbound requests** — it works fully offline and nothing phones home.

Tap the item to open it in the reader (see [Reader](#reader) below).

If a page turns out to be paywalled, the downloader automatically looks for a readable copy elsewhere before giving up:

1. the origin itself
2. archive.today (`archive.ph` / `.is` / `.today` / `.md`)
3. the Wayback Machine

Whatever it finds is labelled in the reader ("via wayback") and flagged with a **paywalled** badge. In practice archive.today serves a CAPTCHA to most non-residential IPs — the app detects that and moves on quietly, so the Wayback Machine is usually the leg that succeeds. If nothing has a copy, the headline and teaser are kept rather than discarded.

Some sites hold a video inside an ordinary article page. Press **Archive Page** instead of **Add to Archive** to force the reader-view capture in that case.

### Capturing from your browser

Some pages can't be fetched by a server at all: subscriptions you pay for, sites
that demand JavaScript execution before serving anything, or anything behind a
login. The **Firefox extension** (`extension/`) archives the page your browser is
already showing — click its toolbar button or press Ctrl+Shift+S.

Captured pages go through the same reader pipeline as everything else and are
marked "via extension". Capturing the same URL again refreshes the stored copy.

If you capture a page while logged out, the paywall check still runs — and
because `archive.today` answers browsers while refusing servers, the extension
fetches the mirror itself and hands the result back.

### Automatic tags

Everything is tagged twice on completion: a broad **category** and a specific **format**.

| Example | Tags |
|---|---|
| `song.mp3` | `audio` `mp3` |
| `clip.mp4` | `video` `mp4` |
| `paper.pdf` | `text` `pdf` |
| an archived page | `text` `article` |
| `meme.gif` | `images` `gif` |

These are ordinary tags — edit or delete them like any other. They are hidden
from the Library's cards and its tag filter, though, because the type filter row
already says the same thing; you see them (and can remove them) on an item's
detail sheet. The 🏷 button on the Library page re-applies them to everything,
which is how you backfill items archived before this existed.

### Audio-only downloads

Press **Audio Only** instead of **Add to Archive** to skip the video and download only the audio as MP3 + OGG. Audio-only items appear in the Library with a headphones badge and go straight to the background audio player when tapped (no video modal).

### Other ways to add

- **Drop a link anywhere on the window** — dragging a link or selected text over
  the app raises a "Drop link to archive" overlay; release to queue it.
- **Ctrl/Cmd + Enter** submits the text box without reaching for the button.

### Clearing the queue

**Clear queue** next to the "Active" heading deletes every queued, downloading,
processing and failed item at once. Completed items in your Library are kept. It
asks for confirmation in place — the button turns into **Clear N** and
**Cancel** — because a mis-tap here is expensive.

### Transcodes

Below the queue, any video being converted to H.264 is listed as **queued** or
**transcoding**, whether the wrench button or a single card started it. The bar
is indeterminate — ffmpeg's progress isn't reported per file.

### Retrying failures

Failed items show an error message and a **Retry** button. Tap it to re-attempt the download.

---

## Library

Browse, search, and open everything you have archived.

Under the search box is a **type filter**: `All · Video · Audio · Text · Images · Files`. Tapping an item does whatever suits it — media opens the player, articles/PDFs/images open the reader, and anything else downloads. Press and hold an item to open its [detail sheet](#item-detail-sheet).

### Views

Toggle between **compact** (thumbnail grid, default) and **detailed** (full card with channel, duration, codec, controls) using the grid/list icon in the top-right of the Library header.

### Search and filter

- **Search** — filters by title as you type. Tap **×** to clear.
- **Sort** — Date added, Title, Duration, or Last updated. The arrow button toggles ascending/descending.
- **Tags** — the tag row appears when you tap the search box, and lists only the
  tags you typed yourself; the automatic category/format ones are left out
  because the type filter above already covers them. Tap a chip to filter to that
  tag, tap it again (or "All tags") to clear. The row stays while a search or a
  tag filter is active. If you have never added a tag of your own, no row
  appears. Tags are added and removed from the detailed card and from an item's
  detail sheet.

### Shuffle

The **shuffle** button (⇄) immediately starts playing all visible videos in a random order via the background audio player.

### Fix All Codecs (🔧 wrench)

The wrench button scans every video on disk, detects its actual codec, writes it to the database, and transcodes any non-H.264 video to H.264 in the background. Use this after first setup or if some videos show "cannot be played" in Firefox. Progress updates live via the codec badges on each card.

### Codec badges (detailed view)

Each video card shows a small badge:

| Badge | Meaning |
|---|---|
| Green **H.264** | Plays in all browsers |
| Orange **AV1** / **HEVC** | May not play in Firefox — tap **Transcode** next to it |
| Orange, no codec name yet | Codec not detected; the button reads **Check & fix** and works it out first |
| Spinning **…** | Transcode in progress |

### Item detail sheet

Press and hold any item — compact or detailed — to slide up its detail sheet.
(On a desktop, right-click does the same.) It holds everything you can do to a
single item:

| Row | What it does |
|---|---|
| **Open in reader** | For articles, PDFs, text and images |
| **Open original ↗** | The source URL, in a new tab |
| **Download …** | Saves the file. On an iPhone-installed app this opens the share sheet, so *Save to Files* works and you land back in the app |
| **Save offline** | Pins the item into the browser cache — see below |
| **Add to playlist** | Pick an existing playlist, or type a name to create one |
| **Delete item** | Asks first, in place: **Delete** / **Cancel** |

Tags are listed at the top of the sheet, automatic ones included, and each can be
removed there.

Tap anywhere outside the sheet to close it, or use the handle or **×** at its
top. The page behind it does not scroll and a swipe over the backdrop does
nothing, so the sheet stays put until you dismiss it.

### Save offline

**Save offline** stores an item's media, reader HTML and images in the browser's
cache, so it plays or reads with the server unreachable — on a plane, or off the
LAN. The row then reads **Saved offline** with the size it took; tap again to
unpin. It works in any browser with a service worker, and pairs with installing
the app to the home screen (see [iOS tips](#ios-tips)).

---

## Reader

Archived pages, PDFs, text files and images open in a full-screen reader modelled on iOS Safari's Reader view.

- **Serif body text** at a comfortable measure (68 characters by default, 58 or 80 if you prefer), with the title, source, author, date and estimated reading time in the header
- **Aa button** — five text sizes, three themes (light / sepia / dark, dark by default) and three line widths, all remembered between sessions
- **Reading progress** — a thin bar at the top, and your scroll position is restored when you come back to a long article
- **Tap any image** to open it full-screen
- **Open original ↗** always links back to the source URL
- PDFs render inline (on iOS, where Safari can't do that reliably, you get an **Open PDF** button instead)

The theme applies to the reader only — the rest of the app stays dark.

If a page couldn't be parsed into an article (a JavaScript-only app, say), the reader says so and shows the original saved copy in a sandboxed frame instead. Nothing is lost.

---

## Playlists

Create named playlists and add any video from the Library to them.

- **New playlist** — tap the **+** button and enter a name.
- **Add a video** — from the detailed Library card, tap the playlist icon and choose a playlist; or use **Add to playlist** on the item's detail sheet, which can also create the playlist as it adds.
- **Play** — **▶ Play** queues everything in the playlist in order; **⇄ Shuffle** does the same in random order. Only playable items are queued, so a PDF sitting in a playlist is skipped.
- **Remove an item** — tap **×** on the row (the item remains in the Library). Items stay in the order they were added; there is no drag-to-reorder.
- **Delete the playlist** — the trash icon in the playlist header, which asks to confirm in place. The items themselves are untouched. There is no rename in the UI.

---

## Player

### MiniPlayer

A persistent bar at the bottom of the screen. It shows the current track's thumbnail, title, and playback time.

Controls:

| Control | Action |
|---|---|
| Tap thumbnail or title | Open the video modal |
| ▶ / ⏸ | Play / pause |
| ⏮ / ⏭ | Previous / next (when in a queue) |
| ⇄ | Toggle shuffle |
| ↺ | Restart from beginning |
| ⤢ | Open video modal |
| ✕ | Stop and dismiss player |

The thin red bar at the very top of the MiniPlayer shows playback progress.

### Video modal

Tapping a video card (compact view) or the **▶** button (detailed view) opens the video modal — a full-screen player.

Its chrome fades out during playback and comes back on a tap:

- **⏮ Play from start** — restarts the video from the beginning.
- **⤡ Minimize** — closes the modal; audio keeps playing in the MiniPlayer.
- **Escape** does the same as Minimize.

If the video is in a codec the browser can't decode, the modal says so and offers
**Transcode to H.264** instead of playing.

Playback position is saved automatically every 4 seconds and restored when you reopen the same video.

### Background audio queue

Playing a video or pressing Shuffle starts a background audio queue. The audio continues even when:

- You navigate to a different page
- The video modal is closed
- The screen locks (iOS/Android, via the Media Session API)

On iOS/Android, the system media controls (lock screen, control centre, AirPods) show the current track and respond to play/pause/skip.

---

## Settings

### Site logins

Signs the archive in to a site, so it can fetch age-restricted, members-only or
subscriber content. Requires the [Firefox
extension](extension/README.md) — a web page cannot read another site's cookies,
so nothing in the app can do this on its own, and there is no paste or upload
fallback.

Paste the backend's `ADMIN_TOKEN` once (it is kept in this browser only), pick a
site, and press **Log in**. The extension opens that site's real login in a
dedicated Firefox container; sign in there and the session is stored
automatically, then the tab closes.

Each signed-in site shows its cookie count, age and expiry — never the cookies
themselves. **Refresh** re-reads the container when a session goes stale, without
a new sign-in; the bin icon forgets the server's copy.

Use a throwaway account, and don't browse in that container: the login is
deliberately never signed out of, which is what keeps it working for weeks, and
an account used for automated downloads can be flagged.

Full setup is in the [main README](README.md#signing-in-to-sites).

---

## iOS tips

### Install as a home-screen app

In Safari: **Share → Add to Home Screen**. The app runs full-screen without browser chrome.

Because there is no browser chrome, there is also no back button — so the app
never navigates itself away from a page you cannot return from. **Download** on
the detail sheet hands the file to the iOS share sheet (*Save to Files*, *Copy*,
AirDrop…) rather than opening it, and closing the sheet puts you back where you
were.

### Offline on the go

Pinned items (see [Save offline](#save-offline)) survive the app being
backgrounded and the network going away, which is the point of installing it —
an archived article and its images read fine in a tunnel.

### Submit links from the share sheet

You can queue any video directly from the iOS share sheet using an Apple Shortcut. See [Apple Shortcut API](#apple-shortcut-api) below.

---

## Apple Shortcut API

The app exposes a simple JSON API for submitting URLs programmatically — useful for queuing videos directly from the iOS/macOS share sheet.

### Endpoint

```
POST https://links.example.com/api/videos
Content-Type: application/json
X-Api-Key: <your-api-key>

{
  "urls": "https://www.youtube.com/watch?v=...",
  "audio_only": false
}
```

`audio_only` is optional and defaults to `false`. Set it to `true` to download only audio.

`mode` is optional too and decides how the link is handled:

| `mode` | Effect |
|---|---|
| `auto` (default) | Work out what the link is — the same as the **Add to Archive** button |
| `audio` | Audio only, the same as `audio_only: true` |
| `article` | Force a reader-view capture, even if the page holds a video |

The API accepts a single URL string as well as an array, so sending `{"urls": "https://..."}` from an iOS Shortcuts **Text** field works correctly. Up to 500 URLs may be sent in one request; the response lists what was `submitted` and what was `skipped` as already present.

> **Setup:** `links.example.com` stands in for a dedicated subdomain whose reverse proxy validates the `X-Api-Key` header before forwarding — needed only if the app itself sits behind client-certificate auth that Shortcuts cannot satisfy. Otherwise point the Shortcut at your normal hostname. See [Caddy config for Shortcuts](README.md#3-caddy-config-for-shortcuts) for the setup.

### Building the Shortcut

1. Open the **Shortcuts** app → **+** → **Add Action**

2. Add **Receive Input from Share Sheet**:
   - Accept: **URLs**
   - If there is no input: **Continue**

3. Add **Get URLs from Shortcut Input** — this converts the share-sheet value into a URL object.

4. Add **Get Contents of URL**, then tap the **›** expand arrow on the right to open its options:
   - The URL field is already in the action title — tap the blue `https://…` token and enter `https://links.example.com/api/videos`
   - **Method**: POST
   - **Headers**: tap **Add new field** → key: `X-Api-Key`, value: your API key
   - **Request Body**: JSON
   - Tap **Add new field** → key: `urls`, type: **Text** → tap the value field → insert the Magic Variable **URLs** (the result of step 3)
   - Optionally tap **Add new field** again → key: `audio_only`, type: **Boolean** → False

5. Save the shortcut as "Queue Video" (or any name you like).

Now share any URL from Safari, YouTube, or any other app → tap your shortcut → the video is queued immediately.
