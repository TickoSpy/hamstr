import axios from "axios";
import { loadAdminToken } from "@/lib/adminToken";

export const http = axios.create({ baseURL: "/api" });

// Only the site-login routes are gated. Everything else stays open, so the PWA,
// the iOS share sheet and the extension's capture keep working untouched.
http.interceptors.request.use((config) => {
  if ((config.url ?? "").startsWith("/cookies")) {
    const token = loadAdminToken();
    if (token) config.headers.set("X-Admin-Token", token);
  }
  return config;
});
