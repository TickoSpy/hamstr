// The token that unlocks the site-login routes. Kept only in this browser —
// it never leaves localStorage except as the X-Admin-Token header, and the
// backend never echoes it back.

const KEY = "yt-admin-token";

export function loadAdminToken(): string {
  try {
    return localStorage.getItem(KEY) ?? "";
  } catch {
    return "";
  }
}

export function saveAdminToken(token: string): void {
  try {
    if (token) localStorage.setItem(KEY, token);
    else localStorage.removeItem(KEY);
  } catch {
    /* private mode / quota — the token just doesn't persist */
  }
}
