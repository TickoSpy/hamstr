# YT Archiver — Firefox extension

Archives the page you are reading, exactly as your browser sees it — and signs
the archive in to sites on your behalf.

## Why capture in the browser

The server can only ask a site for a page and hope. Your browser has already run
the page's JavaScript, cleared whatever bot check it uses, and is viewing it
through your own logged-in session. That covers three cases the server cannot:

- **Subscriptions you pay for.** The page is legitimately yours to read; the
  server has no session and gets the teaser.
- **Bot walls.** Verified in testing that neither a full Chrome header set nor
  real Chrome/Safari TLS impersonation gets past e.g. `www.reddit.com` — the
  challenge has to actually execute.
- **Client-rendered pages** with no data payload to recover the text from.

There is no fingerprinting arms race here, because nothing is being faked.

## Install (temporary, for development)

1. Open `about:debugging#/runtime/this-firefox`
2. **Load Temporary Add-on…** → pick `extension/manifest.json`
3. Open the extension's options and set your archive's address, e.g.
   `https://hamstr.example.com`, plus the backend's `ADMIN_TOKEN` if you want to
   sign in to sites. **Press Save** — closing the panel without it keeps
   nothing. **Test** then confirms the archive is reachable *and* that the token
   is accepted.
4. Firefox MV3 withholds host permissions from a temporarily-loaded add-on, and
   without them cookie reads silently return nothing. Grant them once in
   **about:addons → YT Archiver → Permissions → Access your data for all
   websites**.

A temporary add-on is removed when Firefox restarts. To install it permanently,
sign it with `web-ext sign` (needs a free addons.mozilla.org API key) and install
the resulting `.xpi`.

## Use

Click the toolbar button, or press **Ctrl+Shift+S**, on any page you want to
keep. The button shows `…` while uploading, then `✓` or `✕`.

The page then goes through the normal archive pipeline — reader extraction, image
download, sanitising — so it lands in your library looking like any other
archived article, and reads offline. Captured items are marked
`capture_source: extension`.

Re-capturing the same URL replaces the stored copy, so this doubles as a refresh.

## Paywalled pages

A capture is checked for a paywall like any other page — capturing while logged
out yields the same teaser the server would have got, and storing that as a
success would be the worst outcome.

If the server reports a paywall it could not resolve, the extension fetches
`archive.today` **itself** and posts that copy back. This is the only way that
mirror ever works: it CAPTCHAs the server on every single request but answers a
real browser normally. Recovered pages are marked `via archive.today` in the
reader.

Turn it off with the checkbox in options if you'd rather keep captures instant —
the fallback adds a few seconds while the item is processed and the mirrors are
tried.

## Signing the archive in to a site

The archive cannot log in to YouTube by itself. A web page cannot read another
origin's cookies, and there is no OAuth flow that yields the session tokens
yt-dlp needs. The browser is the only party holding a real jar, so the login runs
here.

Set the backend's `ADMIN_TOKEN` in the options, then drive it from the archive's
**Settings → Site logins** page: pick a site, press **Log in**, and this extension
opens that site's real login page in a dedicated Firefox container named *Archive
login*. When the session cookies appear, they are sent to the archive and the tab
closes.

Two deliberate choices:

- **A container, not your normal window.** Cookies taken from a session you keep
  using are rotated constantly and the exported copy dies within hours. An
  untouched container keeps them valid for weeks. Use a throwaway account, and
  don't browse in that container.
- **It never logs out.** Signing out is what invalidates the stored jar, so the
  tab is closed instead. The container keeps its session, which is also why
  **Refresh** on the archive's settings page can re-send it without a new login.

If containers are unavailable, the login falls back to your normal session and
the extension says so — it will work, it will just go stale sooner.

Everything that must be true to store a jar — address, HTTPS, token, host
permissions — is checked **before** the login tab opens, so a misconfiguration
costs you a click rather than a sign-in. And if storing the jar fails anyway,
the container tab and the pending login are kept: fix the cause and press *I'm
signed in* on the archive's settings page. The session is already there; you
never sign in twice.

## What gets sent

For a capture: only `{url, title, html}` — plus `archive_url` when a copy came
from a mirror — and only when you click. The HTML is the current DOM
(`document.documentElement.outerHTML`) — post-JavaScript, as rendered.

For a site login: the cookies of that one site, from the *Archive login*
container, and only for a login you started yourself. Never your normal browsing
profile's cookies, and never a site you did not name.

There is no background collection, no history access, and no telemetry. The
`cookies` permission is used only by the login flow described above.

Because a login is a live session, the extension **refuses to send one over plain
HTTP** unless the archive is on `localhost`. Page captures are unaffected.

Images are fetched server-side afterwards. If a page's images are themselves
behind the session, they'll be dropped rather than saved — the text is what
survives.

## Configuration

`serverUrl` is stored in `browser.storage.sync`, so it follows a Firefox Sync
profile across machines, and mirrored into `browser.storage.local` so the
background never disagrees with the options page about whether an address is
set. The admin token is a credential, so it lives only in `storage.local` and
stays on this machine.

**Test checks what is saved, not what is typed** — and says so when the two
differ. Validating the fields while the extension read storage meant Test could
report everything healthy while the background had no address at all.

The archive's own pages talk to the extension through a content script registered
on the configured origin only (Firefox has no `externally_connectable`). It
forwards a fixed set of requests — log in, finish, refresh, status — and never
reads the page. Presence checks it answers itself, so an archive page never has
to wait for the background script to wake up.

That registration is redone every time the background script starts, which
includes a **Reload** in `about:debugging` — neither `onInstalled` nor
`onStartup` fires there, and relying on them left reloaded add-ons with no
bridge, so the archive reported the extension as absent. **Test** in the options
reports `bridge live` when it is registered for the configured address.

The backend accepts captures at `POST /api/videos/capture` with a 20 MB body cap
(nginx allows 25 MB). Pages larger than that are rejected rather than truncated.
