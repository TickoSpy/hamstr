// Relay between the archive's own pages and the extension.
//
// Firefox does not support `externally_connectable`, so a page cannot message
// an add-on directly. This script is registered only on the configured archive
// origin and forwards a fixed set of requests — it never reads the page.

const FORWARDED = ["login", "finish", "refresh", "pending", "status"];

window.addEventListener("message", async (event) => {
  if (event.source !== window || event.origin !== location.origin) return;
  const message = event.data;
  if (!message || message.source !== "hamstr-app") return;
  if (typeof message.id !== "string") return;

  const answer = (reply) =>
    window.postMessage(
      { source: "hamstr-ext", id: message.id, ...(reply ?? { ok: false }) },
      location.origin,
    );

  // Answered here rather than forwarded: this script existing *is* the proof
  // that the extension is installed and bridged to this origin. Waking a
  // suspended event page can take longer than the page is willing to wait, and
  // timing that out made an installed extension look absent.
  if (message.type === "ping") {
    answer({ ok: true, bridge: true });
    return;
  }

  if (!FORWARDED.includes(message.type)) return;

  let reply;
  try {
    reply = await browser.runtime.sendMessage({
      type: message.type,
      domain: typeof message.domain === "string" ? message.domain : undefined,
    });
  } catch (err) {
    reply = { ok: false, error: err.message };
  }
  answer(reply);
});
