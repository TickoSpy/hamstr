import { http } from "./client";

/** Status of one stored site login. Never carries cookie names or values. */
export interface SiteLogin {
  domain: string;
  cookie_count: number;
  /** Unix seconds, when the jar was last written. */
  updated_at: number;
  /** Unix seconds of the soonest-expiring cookie, or null if all are session. */
  expires_at: number | null;
  /** null when we have no session-cookie markers for that site to check. */
  signed_in: boolean | null;
}

export const cookieApi = {
  list: () => http.get<SiteLogin[]>("/cookies").then((r) => r.data),

  remove: (domain: string) => http.delete(`/cookies/${encodeURIComponent(domain)}`),
};
