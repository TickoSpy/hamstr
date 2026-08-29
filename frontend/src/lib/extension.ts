// Page half of the bridge to the Firefox extension.
//
// The extension is the only thing that can perform a site login: this page can
// never read youtube.com's cookies, and there is no OAuth flow that yields the
// tokens yt-dlp needs. So we ask, and it does the work.
//
// Firefox has no `externally_connectable`, so the transport is window.postMessage
// to a content script the extension registers on this origin.

interface Reply {
  ok: boolean;
  error?: string;
  [key: string]: unknown;
}

type Request = "ping" | "status" | "login" | "finish" | "refresh" | "pending";

let counter = 0;

function ask(type: Request, domain?: string, timeoutMs = 15_000): Promise<Reply> {
  return new Promise((resolve) => {
    const id = `yt-${Date.now()}-${counter++}`;
    let done = false;

    const finish = (reply: Reply) => {
      if (done) return;
      done = true;
      window.removeEventListener("message", onMessage);
      clearTimeout(timer);
      resolve(reply);
    };

    const onMessage = (event: MessageEvent) => {
      if (event.source !== window || event.origin !== location.origin) return;
      const data = event.data as Reply & { source?: string; id?: string };
      if (data?.source !== "hamstr-ext" || data.id !== id) return;
      finish(data);
    };

    const timer = setTimeout(
      () => finish({ ok: false, error: "The extension did not respond." }),
      timeoutMs,
    );
    window.addEventListener("message", onMessage);
    window.postMessage({ source: "hamstr-app", id, type, domain }, location.origin);
  });
}

export const extension = {
  /** Answered by the content script itself, so this never waits on the
   *  extension's event page waking up. Absence is a real answer here. */
  detect: () => ask("ping", undefined, 1_500),
  /** Reaches the background, which may have to start first — hence the slack. */
  status: () => ask("status", undefined, 8_000),
  /** Opens the site's login in a container tab. Resolves once the tab is open. */
  login: (domain: string) => ask("login", domain),
  /** "I'm signed in" — read the container's jar and store it. */
  finish: (domain: string) => ask("finish", domain, 30_000),
  /** Re-read an existing container without a new login. */
  refresh: (domain: string) => ask("refresh", domain, 30_000),
  pending: () => ask("pending", undefined, 1_000),
};
