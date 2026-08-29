// Capture the page the user is looking at and hand it to the archive.
//
// The point of doing this in the browser rather than server-side: this page has
// already run its JavaScript, already cleared whatever bot check the site uses,
// and is being viewed through the user's own logged-in session. None of that is
// reproducible from a server, and no amount of user-agent or TLS faking gets
// close to it.
//
// The browser is also the only client archive.today will talk to — it CAPTCHAs
// the server on every request — so when the server reports a paywall it could
// not resolve, we fetch the mirror here and hand that back.

const DEFAULTS = { serverUrl: "", archiveFallback: true };

// Same mirrors and preference order the backend uses.
const ARCHIVE_HOSTS = ["archive.ph", "archive.is", "archive.today", "archive.md"];

const CHALLENGE_MARKERS = [
  "please complete the security check",
  "one more step",
  "completing the captcha",
  "checking your browser before accessing",
  "just a moment",
  "cf-browser-verification",
  "attention required",
];
const MISS_MARKERS = [
  "no results",
  "the page you are looking for was not archived",
  "hasn't been archived",
];

const POLL_ATTEMPTS = 20;
const POLL_INTERVAL_MS = 1500;

async function getSettings() {
  // Mirrored into storage.local on every save. storage.sync is the nicer home
  // for the address — it follows a Sync profile — but it can be unavailable or
  // come back empty, and the background silently disagreeing with the options
  // page about whether an address exists is not a failure worth having.
  const [synced, local] = await Promise.all([
    browser.storage.sync.get(DEFAULTS).catch(() => ({})),
    browser.storage.local.get({ serverUrl: "" }).catch(() => ({})),
  ]);
  const merged = { ...DEFAULTS, ...synced };
  if (!merged.serverUrl && local.serverUrl) merged.serverUrl = local.serverUrl;
  return merged;
}

function badge(tabId, text, colour, sticky = false) {
  browser.action.setBadgeText({ tabId, text });
  browser.action.setBadgeBackgroundColor({ tabId, color: colour });
  if (text && !sticky) {
    setTimeout(() => browser.action.setBadgeText({ tabId, text: "" }), 4000);
  }
}

function notify(title, message) {
  browser.notifications.create({ type: "basic", title, message });
}

// Runs in the page. Returns the DOM as it currently stands, which is the whole
// reason for the extension — the tree after hydration, not the served source.
function grabPage() {
  return {
    url: location.href,
    title: document.title,
    html: "<!DOCTYPE html>\n" + document.documentElement.outerHTML,
  };
}

function looksBlocked(html) {
  const head = (html || "").slice(0, 4000).toLowerCase();
  return CHALLENGE_MARKERS.some((m) => head.includes(m));
}

function looksMissing(html) {
  const head = (html || "").slice(0, 4000).toLowerCase();
  return MISS_MARKERS.some((m) => head.includes(m));
}

async function post(serverUrl, payload) {
  const response = await fetch(`${serverUrl}/api/videos/capture`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(`${response.status} ${(await response.text()).slice(0, 140)}`);
  }
  return response.json();
}

/** Wait for the worker to finish, so we know whether it hit a paywall. */
async function waitForItem(serverUrl, itemId) {
  for (let i = 0; i < POLL_ATTEMPTS; i++) {
    await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS));
    try {
      const response = await fetch(`${serverUrl}/api/videos/${itemId}`);
      if (!response.ok) continue;
      const item = await response.json();
      if (!["pending", "downloading", "processing"].includes(item.status)) {
        return item;
      }
    } catch {
      // Server restarting or offline; keep waiting out the budget.
    }
  }
  return null;
}

/** True when the server archived a gated page it couldn't get a full copy of. */
function needsArchiveHelp(item) {
  if (!item) return false;
  const unresolved = !["archive.today", "wayback"].includes(item.capture_source);
  if (item.status === "error") {
    return /paywall/i.test(item.error_message || "");
  }
  return Boolean(item.paywalled) && unresolved;
}

/** Fetch a readable copy from archive.today, which only answers real browsers. */
async function fetchFromArchive(pageUrl) {
  for (const host of ARCHIVE_HOSTS) {
    const mirror = `https://${host}/newest/${pageUrl}`;
    try {
      const response = await fetch(mirror, { credentials: "omit", redirect: "follow" });
      if (response.status === 429 || !response.ok) continue;
      const html = await response.text();
      if (looksBlocked(html) || looksMissing(html) || html.length < 2000) continue;
      return { html, mirror: response.url || mirror };
    } catch {
      // Mirror down or blocked from this network; try the next.
    }
  }
  return null;
}

async function archiveTab(tab) {
  const { serverUrl, archiveFallback } = await getSettings();
  if (!serverUrl) {
    notify("YT Archiver", "Set your archive's address in the extension options first.");
    browser.runtime.openOptionsPage();
    return;
  }
  if (!/^https?:/.test(tab.url ?? "")) {
    notify("YT Archiver", "Only http(s) pages can be archived.");
    return;
  }

  const base = serverUrl.replace(/\/+$/, "");
  badge(tab.id, "…", "#6b7280", true);

  let captured;
  try {
    const [result] = await browser.scripting.executeScript({
      target: { tabId: tab.id },
      func: grabPage,
    });
    captured = result?.result;
  } catch (err) {
    badge(tab.id, "✕", "#dc2626");
    notify("YT Archiver", `Could not read the page: ${err.message}`);
    return;
  }

  if (!captured?.html) {
    badge(tab.id, "✕", "#dc2626");
    notify("YT Archiver", "The page returned no content.");
    return;
  }

  let itemId;
  try {
    itemId = (await post(base, captured)).id;
  } catch (err) {
    badge(tab.id, "✕", "#dc2626");
    notify("YT Archiver", `Upload failed: ${err.message}`);
    return;
  }

  if (!archiveFallback) {
    badge(tab.id, "✓", "#16a34a");
    return;
  }

  const item = await waitForItem(base, itemId);
  if (!needsArchiveHelp(item)) {
    badge(tab.id, item && item.status === "error" ? "✕" : "✓",
          item && item.status === "error" ? "#dc2626" : "#16a34a");
    return;
  }

  // The server saw a paywall and the mirrors refused it. Try them from here.
  badge(tab.id, "⇩", "#d97706", true);
  const found = await fetchFromArchive(captured.url);
  if (!found) {
    badge(tab.id, "✕", "#dc2626");
    notify(
      "YT Archiver",
      "This page is paywalled and no archive copy was available — the teaser was kept.",
    );
    return;
  }

  try {
    await post(base, {
      url: captured.url,
      title: captured.title,
      html: found.html,
      archive_url: found.mirror,
    });
    badge(tab.id, "✓", "#16a34a");
    notify("YT Archiver", "Paywalled page recovered from archive.today.");
  } catch (err) {
    badge(tab.id, "✕", "#dc2626");
    notify("YT Archiver", `Archive upload failed: ${err.message}`);
  }
}

browser.action.onClicked.addListener((tab) => {
  archiveTab(tab).catch((err) => notify("YT Archiver", err.message));
});
