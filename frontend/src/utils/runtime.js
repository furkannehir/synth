export function isTauriRuntime() {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

export function isBrowserRuntime() {
  return !isTauriRuntime();
}

const DEFAULT_INVITE_CACHE_TTL_HOURS = 24;

export function getInviteCacheTtlHours() {
  const configuredHours = Number(import.meta.env.VITE_INVITE_CACHE_TTL_HOURS);
  if (Number.isFinite(configuredHours) && configuredHours > 0) {
    return Math.ceil(configuredHours);
  }

  return DEFAULT_INVITE_CACHE_TTL_HOURS;
}

export function getInviteCacheTtlMs() {
  const ttlHours = getInviteCacheTtlHours();

  return Math.floor(ttlHours * 60 * 60 * 1000);
}