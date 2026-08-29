import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  Check,
  KeyRound,
  Loader2,
  LogIn,
  RefreshCw,
  Trash2,
} from "lucide-react";
import { cookieApi, type SiteLogin } from "@/lib/api";
import { loadAdminToken, saveAdminToken } from "@/lib/adminToken";
import { extension } from "@/lib/extension";
import { cn } from "@/lib/utils";

const PRESETS = ["youtube.com", "nebula.tv", "patreon.com"];

function relative(unixSeconds: number): string {
  const seconds = Math.max(0, Math.round(Date.now() / 1000 - unixSeconds));
  if (seconds < 90) return "just now";
  const minutes = Math.round(seconds / 60);
  if (minutes < 90) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 36) return `${hours} h ago`;
  return `${Math.round(hours / 24)} d ago`;
}

function expiry(unixSeconds: number | null): string {
  if (!unixSeconds) return "session only";
  const days = Math.round((unixSeconds - Date.now() / 1000) / 86400);
  if (days < 0) return "expired";
  if (days === 0) return "expires today";
  return `expires in ${days} d`;
}

export function SiteLogins() {
  const qc = useQueryClient();
  const [token, setToken] = useState(loadAdminToken);
  const [savedToken, setSavedToken] = useState(loadAdminToken);
  const [domain, setDomain] = useState("youtube.com");
  const [busy, setBusy] = useState<string | null>(null);
  const [note, setNote] = useState<{ text: string; bad?: boolean } | null>(null);
  const [hasExtension, setHasExtension] = useState<boolean | null>(null);
  // What the extension still needs before a sign-in can succeed — reported by
  // its own preflight, so we can say it before the user types a password.
  const [blocker, setBlocker] = useState<string | null>(null);
  const [pending, setPending] = useState<string | null>(null);

  const probeExtension = async () => {
    const present = await extension.detect();
    setHasExtension(present.ok);
    if (!present.ok) {
      setBlocker(null);
      return;
    }
    // Separate round trip: this one wakes the background script, which is slow
    // enough that folding it into detection made the extension look absent.
    const state = await extension.status();
    setBlocker(state.ok && !state.ready ? ((state.blocker as string) ?? null) : null);
    extension.pending().then((p) => setPending((p.pending as string) ?? null));
  };

  useEffect(() => {
    probeExtension();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const logins = useQuery({
    queryKey: ["site-logins"],
    queryFn: cookieApi.list,
    enabled: Boolean(savedToken),
    retry: false,
  });

  const remove = useMutation({
    mutationFn: cookieApi.remove,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["site-logins"] }),
  });

  const run = async (
    label: string,
    action: () => Promise<{ ok: boolean; error?: string }>,
  ) => {
    setBusy(label);
    setNote(null);
    const reply = await action();
    setBusy(null);
    if (!reply.ok) {
      setNote({ text: reply.error ?? "The extension reported a failure.", bad: true });
    }
    qc.invalidateQueries({ queryKey: ["site-logins"] });
    return reply.ok;
  };

  const startLogin = async () => {
    const target = domain.trim().toLowerCase().replace(/^www\./, "");
    if (!target.includes(".")) {
      setNote({ text: "Enter a site domain, e.g. youtube.com", bad: true });
      return;
    }
    const ok = await run("login", () => extension.login(target));
    if (ok) {
      setPending(target);
      setNote({
        text:
          `A container tab is open. Sign in there, then come back — ${target} is ` +
          `stored automatically once the session appears, or press "I'm signed in".`,
      });
    }
  };

  const status = logins.error
    ? (logins.error as { response?: { status?: number } }).response?.status
    : undefined;

  return (
    <section className="space-y-4">
      <header>
        <h2 className="text-sm font-semibold text-gray-200 flex items-center gap-2">
          <KeyRound size={15} /> Site logins
        </h2>
        <p className="text-xs text-gray-500 mt-1">
          Signs the archive in to a site so it can fetch age-restricted, members-only
          or subscriber content. The login happens in your own browser — the server
          never sees a password.
        </p>
      </header>

      <div className="space-y-2">
        <label className="block text-xs font-medium text-gray-400" htmlFor="admin-token">
          Admin token
        </label>
        <div className="flex gap-2">
          <input
            id="admin-token"
            type="password"
            autoComplete="off"
            value={token}
            onChange={(e) => setToken(e.target.value)}
            placeholder="ADMIN_TOKEN from the backend"
            className="flex-1 bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-100 placeholder-gray-500 focus:outline-none focus:border-red-500"
          />
          <button
            onClick={() => {
              saveAdminToken(token.trim());
              setSavedToken(token.trim());
              qc.invalidateQueries({ queryKey: ["site-logins"] });
            }}
            className="px-4 py-2 rounded-lg bg-red-600 hover:bg-red-700 text-sm font-medium text-white"
          >
            Save
          </button>
        </div>
        <p className="text-xs text-gray-500">
          Stored in this browser only. Set the same value in the extension's options.
        </p>
      </div>

      {status === 503 && (
        <p className="text-xs text-amber-500 flex gap-2">
          <AlertTriangle size={14} className="shrink-0 mt-0.5" />
          Site logins are disabled on the backend. Set <code>ADMIN_TOKEN</code> and
          restart it.
        </p>
      )}
      {status === 401 && (
        <p className="text-xs text-amber-500 flex gap-2">
          <AlertTriangle size={14} className="shrink-0 mt-0.5" />
          That token was rejected.
        </p>
      )}

      {/* An empty list rendering nothing left no way to tell "not signed in"
          from "the page didn't load" — which is exactly the confusion to avoid. */}
      {logins.data?.length === 0 && (
        <p className="text-xs text-gray-500 bg-gray-900 border border-gray-800 rounded-lg px-3 py-2.5">
          No sites signed in. Downloads that need an account will fail until you add
          one below — saving the admin token on its own does not sign the archive in
          to anything.
        </p>
      )}

      {logins.data && logins.data.length > 0 && (
        <ul className="space-y-2">
          {logins.data.map((site: SiteLogin) => (
            <li
              key={site.domain}
              className="flex items-center gap-3 bg-gray-900 border border-gray-800 rounded-lg px-3 py-2.5"
            >
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2 text-sm text-gray-100">
                  {site.domain}
                  {site.signed_in === false && (
                    <span className="text-xs text-amber-500">no session cookie</span>
                  )}
                  {site.signed_in === true && (
                    <Check size={13} className="text-green-500" />
                  )}
                </div>
                <div className="text-xs text-gray-500">
                  {site.cookie_count} cookies · {relative(site.updated_at)} ·{" "}
                  {expiry(site.expires_at)}
                </div>
              </div>
              <button
                title="Re-read the container without signing in again"
                disabled={!hasExtension || busy !== null}
                onClick={() => run(site.domain, () => extension.refresh(site.domain))}
                className="p-2 rounded-lg text-gray-400 hover:text-white hover:bg-gray-800 disabled:opacity-40"
              >
                <RefreshCw
                  size={15}
                  className={cn(busy === site.domain && "animate-spin")}
                />
              </button>
              <button
                title="Forget this login"
                onClick={() => remove.mutate(site.domain)}
                className="p-2 rounded-lg text-gray-400 hover:text-red-400 hover:bg-gray-800"
              >
                <Trash2 size={15} />
              </button>
            </li>
          ))}
        </ul>
      )}

      {hasExtension === false ? (
        <p className="text-xs text-gray-500 bg-gray-900 border border-gray-800 rounded-lg px-3 py-2.5">
          <strong className="text-gray-300">No extension detected.</strong> Adding a
          login needs it — a web page cannot read another site's cookies, so nothing
          here can do it alone. If it is installed, check that its options point at{" "}
          <code>{location.origin}</code>, and that it has access to this site in
          about:addons → Permissions. A temporarily-loaded add-on also needs a{" "}
          <strong className="text-gray-300">Reload</strong> in about:debugging after
          the code changes.{" "}
          <button
            onClick={probeExtension}
            className="underline underline-offset-2 hover:text-gray-300"
          >
            Re-check
          </button>
        </p>
      ) : (
        <div className="space-y-2">
          <div className="flex gap-2">
            <input
              list="login-presets"
              value={domain}
              onChange={(e) => setDomain(e.target.value)}
              placeholder="youtube.com"
              className="flex-1 bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-100 placeholder-gray-500 focus:outline-none focus:border-red-500"
            />
            <datalist id="login-presets">
              {PRESETS.map((p) => (
                <option key={p} value={p} />
              ))}
            </datalist>
            <button
              disabled={busy !== null || hasExtension === null || blocker !== null}
              onClick={startLogin}
              className="flex items-center gap-2 px-4 py-2 rounded-lg bg-red-600 hover:bg-red-700 disabled:opacity-40 text-sm font-medium text-white"
            >
              {busy === "login" ? (
                <Loader2 size={15} className="animate-spin" />
              ) : (
                <LogIn size={15} />
              )}
              Log in
            </button>
          </div>
          {blocker && (
            <p className="text-xs text-amber-500 flex gap-2">
              <AlertTriangle size={14} className="shrink-0 mt-0.5" />
              <span>
                {blocker}{" "}
                <button
                  onClick={probeExtension}
                  className="underline underline-offset-2 hover:text-amber-300"
                >
                  Re-check
                </button>
              </span>
            </p>
          )}
          {pending && (
            <button
              disabled={busy !== null}
              onClick={async () => {
                if (await run("finish", () => extension.finish(pending))) {
                  setPending(null);
                  setNote({ text: `Stored the ${pending} login.` });
                }
              }}
              className="text-xs text-gray-300 underline underline-offset-2 hover:text-white"
            >
              {busy === "finish" ? "Reading the session…" : `I'm signed in to ${pending}`}
            </button>
          )}
        </div>
      )}

      {note && (
        <p className={cn("text-xs", note.bad ? "text-red-400" : "text-gray-400")}>
          {note.text}
        </p>
      )}

      <p className="text-xs text-gray-600 leading-relaxed">
        Use a throwaway account. The login runs in a dedicated Firefox container and
        is never logged out of — that is what keeps the cookies alive for weeks
        instead of hours, but it also means an account used here can be flagged for
        automated access. Don't browse in that container.
      </p>
    </section>
  );
}
