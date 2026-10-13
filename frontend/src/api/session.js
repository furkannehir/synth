export const SESSION_EXPIRED_EVENT = "synth-session-expired";

// A delayed response from an old session must not sign out a newer login.
export function rejectSession(token, { storage = localStorage, events = window } = {}) {
  if (!token || storage.getItem("synth_token") !== token) return false;
  storage.removeItem("synth_token");
  events.dispatchEvent(new Event(SESSION_EXPIRED_EVENT));
  return true;
}
