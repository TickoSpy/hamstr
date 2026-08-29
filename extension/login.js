// Sign the archive in to a site.
//
// The archive can never do this itself: a page cannot read another origin's
// cookies, and there is no OAuth flow that yields the session tokens yt-dlp
// needs. The browser is the only party holding a real jar, so the login runs
// here and only the resulting cookies are handed to the server.
//
// The login happens inside a dedicated Firefox container, and we never log out
// of it. That matters more than it sounds: cookies scraped from a session you
// keep using are rotated constantly and the exported copy dies within hours.
// An untouched container keeps them alive for weeks.

const CONTAINER_NAME = "Archive login";
// Set while a jar is in flight, so a burst of cookie writes sends it once.
let sendingFor = null;
const LOGIN_STATE_KEY = "pendingLogin";

const SITE_PRESETS = {
  "youtube.com": {
    loginUrl:
      "https://accounts.google.com/ServiceLogin?service=youtube&continue=https%3A%2F%2Fwww.youtube.com%2F",
    // The Google sign-in writes the session on google.com; yt-dlp needs both.
    cookieDomains: ["youtube.com", "google.com"],
    ready: ["__Secure-3PSID", "LOGIN_INFO"],
  },
};

function presetFor(domain) {
  return (
    SITE_PRESETS[domain] ?? {
      loginUrl: `https://${domain}/`,
      cookieDomains: [domain],
      // Unknown site: we have no marker to watch for, so the user tells us
      // when they're done from the archive's settings page.
      ready: null,
    }
  );
}

/** Session tokens must not cross the network in the clear. */
function transportOk(serverUrl) {
  try {
    const url = new URL(serverUrl);
    return (
      url.protocol === "https:" ||
      ["localhost", "127.0.0.1", "[::1]", "::1"].includes(url.hostname)
    );
  } catch {
    return false;
  }
}

/** Firefox MV3 lets the user withhold host permissions; without them
 *  cookies.getAll() returns nothing at all rather than failing. Check up front
 *  so the failure reads as "grant access", not "the login didn't work". */
async function ensureHostAccess(origins) {
  if (!browser.permissions?.contains) return;
  const granted = await browser.permissions.contains({ origins });
  if (granted) return;
  throw new Error(
    "This add-on is missing access to that site. Open about:addons → YT Archiver " +
      "→ Permissions and allow access to all sites, then try again.",
  );
}

async function getToken() {
  const { adminToken } = await browser.storage.local.get({ adminToken: "" });
  return adminToken;
}

/** One reusable container, so a second login doesn't mean a second sign-in. */
async function ensureContainer() {
  if (!browser.contextualIdentities) return null;
  try {
    const [existing] = await browser.contextualIdentities.query({
      name: CONTAINER_NAME,
    });
    if (existing) return existing.cookieStoreId;
    const created = await browser.contextualIdentities.create({
      name: CONTAINER_NAME,
      color: "red",
      icon: "briefcase",
    });
    return created.cookieStoreId;
  } catch {
    return null;
  }
}

async function readJar(storeId, cookieDomains) {
  const seen = new Map();
  for (const domain of cookieDomains) {
    const query = { domain, firstPartyDomain: null };
    if (storeId) query.storeId = storeId;
    let found = [];
    try {
      found = await browser.cookies.getAll(query);
    } catch {
      // firstPartyDomain is rejected when first-party isolation is off in some
      // builds; retry without it rather than losing the login.
      delete query.firstPartyDomain;
      found = await browser.cookies.getAll(query);
    }
    for (const c of found) {
      seen.set(`${c.domain}|${c.path}|${c.name}`, {
        name: c.name,
        value: c.value,
        domain: c.domain,
        path: c.path,
        secure: Boolean(c.secure),
        httpOnly: Boolean(c.httpOnly),
        hostOnly: Boolean(c.hostOnly),
        session: Boolean(c.session),
        expirationDate: c.expirationDate ?? null,
      });
    }
  }
  return [...seen.values()];
}

/** Everything that must be true before the jar can be stored.
 *
 *  Checked before the login tab opens, not after: discovering a missing token
 *  once the user has already typed a password is the worst possible moment. */
async function preflight() {
  const { serverUrl } = await getSettings();
  if (!serverUrl) {
    throw new Error("Set your archive's address in the extension options first.");
  }
  if (!transportOk(serverUrl)) {
    throw new Error(
      "Refusing to send a login over plain HTTP. Use https:// (page captures still work either way).",
    );
  }
  const token = await getToken();
  if (!token) {
    throw new Error(
      "Set the admin token in the extension options — about:addons → YT Archiver " +
        "→ Preferences, then press Save.",
    );
  }
  return { base: serverUrl.replace(/\/+$/, ""), token };
}

async function sendJar(domain, cookies) {
  const { base, token } = await preflight();
  const response = await fetch(`${base}/api/cookies/${encodeURIComponent(domain)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", "X-Admin-Token": token },
    body: JSON.stringify({ cookies }),
  });
  if (!response.ok) {
    const detail = (await response.text()).slice(0, 160);
    throw new Error(`${response.status} ${detail}`);
  }
  return response.json();
}

async function captureAndSend(domain, storeId) {
  const { cookieDomains } = presetFor(domain);
  await ensureHostAccess(cookieDomains.map((d) => `*://*.${d}/*`));
  const cookies = await readJar(storeId, cookieDomains);
  if (!cookies.length) throw new Error("No cookies found — is the login complete?");
  const result = await sendJar(domain, cookies);
  notify("Archive login", `Signed in to ${domain} (${result.cookie_count} cookies).`);
  return result;
}

async function pendingLogin() {
  const stored = await browser.storage.local.get({ [LOGIN_STATE_KEY]: null });
  return stored[LOGIN_STATE_KEY];
}

async function clearPending() {
  await browser.storage.local.remove(LOGIN_STATE_KEY);
}

async function startLogin(domain) {
  const preset = presetFor(domain);
  // Fail before the password, not after it.
  await preflight();
  await ensureHostAccess(preset.cookieDomains.map((d) => `*://*.${d}/*`));
  const storeId = await ensureContainer();
  const tab = await browser.tabs.create({
    url: preset.loginUrl,
    ...(storeId ? { cookieStoreId: storeId } : {}),
  });
  await browser.storage.local.set({
    [LOGIN_STATE_KEY]: { domain, storeId, tabId: tab.id },
  });
  if (!storeId) {
    notify(
      "Archive login",
      "Containers are unavailable, so this login shares your normal session — " +
        "expect it to need refreshing more often.",
    );
  }
  return { ok: true, contained: Boolean(storeId), autodetect: Boolean(preset.ready) };
}

/** Finish a login the user says is done (or that we detected). */
async function finishLogin(explicitDomain) {
  const pending = await pendingLogin();
  const domain = explicitDomain ?? pending?.domain;
  if (!domain) throw new Error("No login in progress.");
  const storeId = pending?.domain === domain ? pending.storeId : await ensureContainer();
  const result = await captureAndSend(domain, storeId);
  if (pending?.domain === domain) {
    // Close the tab but never log out — logging out is what kills the cookies.
    if (pending.tabId != null) {
      await browser.tabs.remove(pending.tabId).catch(() => {});
    }
    await clearPending();
  }
  return result;
}

/** Re-read a container we already signed in, without a new login. */
async function refreshLogin(domain) {
  const storeId = await ensureContainer();
  return captureAndSend(domain, storeId);
}

// The event page is non-persistent, so a polling timer is not guaranteed to
// survive the login. A cookie listener wakes it back up instead.
browser.cookies.onChanged.addListener(async ({ cookie, removed }) => {
  if (removed) return;
  const pending = await pendingLogin();
  if (!pending) return;
  if (pending.storeId && cookie.storeId !== pending.storeId) return;

  const preset = presetFor(pending.domain);
  if (!preset.ready || !preset.ready.includes(cookie.name)) return;

  const jar = await readJar(pending.storeId, preset.cookieDomains);
  const names = new Set(jar.map((c) => c.name));
  if (!preset.ready.every((n) => names.has(n))) return;

  // A sign-in writes a burst of cookies, so guard against sending twice. The
  // in-memory flag catches the burst; the stored one survives the event page
  // being suspended between events.
  if (sendingFor === pending.domain || pending.sending) return;
  sendingFor = pending.domain;
  await browser.storage.local.set({
    [LOGIN_STATE_KEY]: { ...pending, sending: true },
  });

  try {
    await ensureHostAccess(preset.cookieDomains.map((d) => `*://*.${d}/*`));
    const result = await sendJar(pending.domain, jar);
    // Only now is the login safe to forget. Close the tab but never log out —
    // logging out is what would kill the jar we just stored.
    if (pending.tabId != null) {
      await browser.tabs.remove(pending.tabId).catch(() => {});
    }
    await clearPending();
    notify(
      "Archive login",
      `Signed in to ${pending.domain} (${result.cookie_count} cookies).`,
    );
  } catch (err) {
    // Keep the tab and the pending record: the session is real and still in the
    // container, so fixing the cause and retrying costs no second sign-in.
    await browser.storage.local.set({
      [LOGIN_STATE_KEY]: { ...pending, sending: false },
    });
    notify(
      "Archive login",
      `${err.message}\n\nThe sign-in itself worked — fix that and press ` +
        `"I'm signed in" on the archive's settings page. No need to log in again.`,
    );
  } finally {
    sendingFor = null;
  }
});

// ---------------------------------------------------------- page bridge

const BRIDGE_ID = "hamstr-bridge";
// In-flight registration, and why the last attempt failed. Both exist so the
// options page can report the actual reason instead of a bare "not registered".
let bridgePromise = null;
let bridgeError = null;

/** Let the archive's own pages talk to us. Firefox has no externally_connectable. */
function registerBridge() {
  bridgePromise = doRegisterBridge();
  return bridgePromise;
}

async function doRegisterBridge() {
  bridgeError = null;
  if (!browser.scripting?.registerContentScripts) {
    bridgeError = "This Firefox has no scripting.registerContentScripts.";
    return;
  }
  try {
    await browser.scripting.unregisterContentScripts({ ids: [BRIDGE_ID] });
  } catch {
    // Not registered yet.
  }
  const { serverUrl } = await getSettings();
  if (!serverUrl) {
    bridgeError = "No archive address set in the options.";
    return;
  }
  let origin;
  try {
    origin = new URL(serverUrl).origin;
  } catch {
    bridgeError = `Archive address is not a valid URL: ${serverUrl}`;
    return;
  }

  // Registering for an origin the add-on may not touch fails; say so plainly.
  if (browser.permissions?.contains) {
    const allowed = await browser.permissions.contains({ origins: [`${origin}/*`] });
    if (!allowed) {
      bridgeError =
        `This add-on has no access to ${origin}. Open about:addons → YT Archiver ` +
        `→ Permissions and allow access to all sites.`;
      return;
    }
  }
  try {
    await browser.scripting.registerContentScripts([
      {
        id: BRIDGE_ID,
        js: ["bridge.js"],
        matches: [`${origin}/*`],
        runAt: "document_start",
        // Re-registered on every background start, so a persisted copy would
        // only be a stale duplicate to fight with.
        persistAcrossSessions: false,
      },
    ]);
  } catch (err) {
    bridgeError = err.message;
    console.warn("Could not register the archive page bridge:", err.message);
  }
}

/** What the browser actually has registered — not what we think we registered. */
async function bridgeState() {
  // The registration is kicked off at background start and is very likely still
  // in flight when this is asked: waking the event page is what asks it.
  await bridgePromise?.catch(() => {});
  let matches = [];
  try {
    const live = await browser.scripting.getRegisteredContentScripts({
      ids: [BRIDGE_ID],
    });
    matches = live[0]?.matches ?? [];
  } catch (err) {
    return { ok: true, matches: [], error: bridgeError ?? err.message };
  }
  return { ok: true, matches, error: matches.length ? null : bridgeError };
}

// Register on every background-script start, not only on install/startup.
// Reloading a temporary add-on from about:debugging fires neither event, which
// silently left the archive's pages with no bridge at all.
registerBridge();
browser.runtime.onStartup.addListener(registerBridge);
browser.runtime.onInstalled.addListener(registerBridge);
browser.storage.onChanged.addListener((changes, area) => {
  if (area === "sync" && changes.serverUrl) registerBridge();
});

browser.runtime.onMessage.addListener((message) => {
  const wrap = (promise) =>
    promise.then(
      (value) => ({ ok: true, ...value }),
      (err) => ({ ok: false, error: err.message }),
    );

  switch (message?.type) {
    case "bridgeState":
      return bridgeState();
    case "registerBridge":
      return registerBridge().then(bridgeState);
    case "ping":
    case "status":
      // Report what is configured, so the archive can say what is missing
      // before the user starts a sign-in rather than after it.
      return preflight().then(
        ({ base }) => ({
          ok: true,
          version: browser.runtime.getManifest().version,
          containers: Boolean(browser.contextualIdentities),
          ready: true,
          serverUrl: base,
        }),
        (err) => ({
          ok: true,
          version: browser.runtime.getManifest().version,
          containers: Boolean(browser.contextualIdentities),
          ready: false,
          blocker: err.message,
        }),
      );
    case "login":
      return wrap(startLogin(message.domain));
    case "finish":
      return wrap(finishLogin(message.domain));
    case "refresh":
      return wrap(refreshLogin(message.domain));
    case "pending":
      return pendingLogin().then((p) => ({ ok: true, pending: p?.domain ?? null }));
    default:
      return undefined;
  }
});
