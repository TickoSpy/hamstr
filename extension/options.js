const input = document.getElementById("serverUrl");
const status = document.getElementById("status");

let clearStatus;
function show(message, ok = true) {
  status.textContent = message;
  status.className = ok ? "ok" : "bad";
  clearTimeout(clearStatus);
  // Failures explain what to do about them, so they stay until the next action.
  if (ok) clearStatus = setTimeout(() => (status.textContent = ""), 3000);
}

function normalise(value) {
  return value.trim().replace(/\/+$/, "");
}

const fallback = document.getElementById("archiveFallback");
const token = document.getElementById("adminToken");

/** What the background actually reads. The options page used to test the typed
 *  fields instead, so Test could pass while the extension saw nothing. */
async function saved() {
  const [synced, local] = await Promise.all([
    browser.storage.sync.get({ serverUrl: "", archiveFallback: true }).catch(() => ({})),
    browser.storage.local
      .get({ serverUrl: "", adminToken: "" })
      .catch(() => ({ serverUrl: "", adminToken: "" })),
  ]);
  return {
    serverUrl: synced.serverUrl || local.serverUrl || "",
    archiveFallback: synced.archiveFallback ?? true,
    adminToken: local.adminToken ?? "",
  };
}

saved().then((config) => {
  input.value = config.serverUrl;
  fallback.checked = config.archiveFallback;
  token.value = config.adminToken;
});

// The token is a credential for the archive, so it stays on this machine
// rather than riding Firefox Sync like the address does — see saved() above.

document.getElementById("save").addEventListener("click", async () => {
  const serverUrl = normalise(input.value);
  if (serverUrl && !/^https?:\/\//.test(serverUrl)) {
    show("Must start with http:// or https://", false);
    return;
  }
  await browser.storage.sync
    .set({ serverUrl, archiveFallback: fallback.checked })
    .catch(() => {});
  // Mirrored locally so the background never disagrees about the address.
  await browser.storage.local.set({ serverUrl, adminToken: token.value.trim() });
  input.value = serverUrl;
  await browser.runtime.sendMessage({ type: "registerBridge" }).catch(() => {});
  if (serverUrl) await reportBridge(serverUrl, "Saved");
  else show("Saved");
});

document.getElementById("test").addEventListener("click", async () => {
  // Test what is stored, not what is typed. The two diverging is the whole
  // reason this button could report success while nothing worked.
  const config = await saved();
  const serverUrl = config.serverUrl;
  const value = config.adminToken;

  if (normalise(input.value) !== serverUrl || token.value.trim() !== value) {
    show("Unsaved changes — press Save first", false);
    return;
  }
  if (!serverUrl) {
    show("Enter an address and press Save first", false);
    return;
  }
  try {
    const response = await fetch(`${serverUrl}/api/health`);
    const body = await response.json();
    if (body.status !== "ok") {
      show("Unexpected reply", false);
      return;
    }
  } catch (err) {
    show(`Unreachable: ${err.message}`, false);
    return;
  }

  // Reachable. If a token is set, check it actually opens the login routes —
  // finding that out here beats finding it out after a sign-in.
  if (!value) {
    show("Reachable (no admin token set — site logins are off)", false);
    return;
  }
  try {
    const probe = await fetch(`${serverUrl}/api/cookies`, {
      headers: { "X-Admin-Token": value },
    });
    if (probe.status === 401) {
      show("Reachable, but the token was rejected", false);
      return;
    }
    if (probe.status === 503) {
      show("Reachable, but ADMIN_TOKEN is unset on the backend", false);
      return;
    }
    if (!probe.ok) {
      show(`Reachable, token check returned ${probe.status}`, false);
      return;
    }
  } catch (err) {
    show(`Token check failed: ${err.message}`, false);
    return;
  }

  await reportBridge(serverUrl, "Reachable, token accepted");
});

/** The bridge is what the archive's own settings page talks to. Without it that
 *  page reports no extension at all, which reads as "not installed". */
async function reportBridge(serverUrl, prefix) {
  let state;
  try {
    state = await browser.runtime.sendMessage({ type: "bridgeState" });
  } catch (err) {
    show(`${prefix}, bridge unknown: ${err.message}`, false);
    return;
  }
  const want = `${new URL(serverUrl).origin}/*`;
  if ((state?.matches ?? []).includes(want)) {
    show(`${prefix}, bridge live`);
    return;
  }
  const why =
    state?.error ??
    `registered for ${(state?.matches ?? []).join(", ") || "nothing"}`;
  show(`${prefix} — bridge NOT registered: ${why}`, false);
  grant.hidden = false;
}

// Only a user gesture may request permissions, so this lives on a button.
const grant = document.getElementById("grant");
grant.addEventListener("click", async () => {
  let granted = false;
  try {
    granted = await browser.permissions.request({ origins: ["<all_urls>"] });
  } catch (err) {
    show(`Could not request access: ${err.message}`, false);
    return;
  }
  if (!granted) {
    show("Access not granted", false);
    return;
  }
  const { serverUrl } = await saved();
  await browser.runtime.sendMessage({ type: "registerBridge" });
  grant.hidden = true;
  if (serverUrl) await reportBridge(serverUrl, "Access granted");
  else show("Access granted — now set an address and press Save");
});
