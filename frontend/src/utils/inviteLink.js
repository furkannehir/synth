import { isTauriRuntime } from "./runtime";

/** Share a web route, independent of the desktop application's local origin. */
export function buildInviteLink(code, {
  publicUrl = import.meta.env.VITE_WEB_URL,
  origin = typeof window !== "undefined" ? window.location.origin : "",
  desktop = isTauriRuntime(),
} = {}) {
  const configuredUrl = publicUrl?.trim();
  const base = configuredUrl || (desktop ? "" : origin);
  try {
    const url = new URL(base);
    if (!code || !["http:", "https:"].includes(url.protocol) || url.username || url.password) {
      throw new Error("Invalid invite URL");
    }
    url.pathname = `${url.pathname.replace(/\/+$/, "")}/invite/${encodeURIComponent(code)}`;
    url.search = "";
    url.hash = "";
    return url.href;
  } catch {
    throw new Error("Invite links are unavailable. Please try again later.");
  }
}
