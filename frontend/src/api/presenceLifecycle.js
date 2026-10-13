const sessions = new Set();

/** Capture credentials for the whole lease, including cleanup after logout. */
export function startPresence({ token, heartbeat, offline, sessionId = crypto.randomUUID(),
  schedule = setInterval, cancel = clearInterval }) {
  let active = true;
  const beat = () => {
    if (active) heartbeat(token, sessionId).catch(() => {});
  };
  const timer = schedule(beat, 30_000);
  const session = {
    token,
    stop() {
      if (!active) return;
      active = false;
      cancel(timer);
      sessions.delete(session);
      // Dispatch immediately; the server ignores any delayed beat for this lease.
      offline(token, sessionId).catch(() => {});
    },
  };
  sessions.add(session);
  beat();
  return session.stop;
}

export function stopPresence(token) {
  let stopped = 0;
  for (const session of sessions) {
    if (session.token === token) {
      session.stop();
      stopped += 1;
    }
  }
  return stopped;
}
