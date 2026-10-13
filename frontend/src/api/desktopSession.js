import { isTauriRuntime } from "../utils/runtime.js";

export class SessionChangedError extends Error {
  constructor() { super("Session changed. Please try again."); }
}

function replacement(token) {
  const bytes = crypto.getRandomValues(new Uint8Array(32));
  const secret = btoa(String.fromCharCode(...bytes)).replaceAll("+", "-").replaceAll("/", "_").replace(/=+$/, "");
  return `${token.split(".")[0]}.${secret}`;
}

export function createDesktopSession({ storage, request, tokens, expired,
  desktop = isTauriRuntime, schedule = setTimeout, cancel = clearTimeout }) {
  let credentials = { session: null, pending_revocations: [] };
  let loaded = false;
  let loadPromise;
  let renewPromise;
  let writes = Promise.resolve();
  let generation = 0;
  let timer;

  function check(version) {
    if (version !== generation) throw new SessionChangedError();
  }
  function stopTimer() {
    if (timer) cancel(timer);
    timer = null;
  }
  function persist(version) {
    const snapshot = structuredClone(credentials);
    const write = writes.catch(() => {}).then(async () => {
      check(version);
      await storage.write(snapshot);
      check(version);
    });
    writes = write;
    return write;
  }
  async function load() {
    if (loaded) return;
    if (!loadPromise) {
      loadPromise = storage.read().then((saved) => {
        credentials = saved || { session: null, pending_revocations: [] };
        loaded = true;
      }).finally(() => { loadPromise = null; });
    }
    await loadPromise;
  }
  function queueRevocation(session) {
    if (!session) return;
    if (!credentials.pending_revocations.includes(session.revocation_token)) {
      if (credentials.pending_revocations.length >= 32) throw new Error("Connect to the internet to finish signing out of earlier sessions, then retry.");
      credentials.pending_revocations.push(session.revocation_token);
    }
  }
  async function flushRevocations(version = generation) {
    for (const credential of [...credentials.pending_revocations]) {
      try {
        await request("/auth/logout", { revocation_token: credential });
      } catch { return; }
      check(version);
      credentials.pending_revocations = credentials.pending_revocations.filter((value) => value !== credential);
      await persist(version);
    }
  }
  async function invalidate(expectedToken = tokens.get()) {
    if (expectedToken !== tokens.get()) return;
    const version = ++generation;
    stopTimer();
    tokens.clear();
    expired();
    await load();
    check(version);
    credentials.session = null;
    await persist(version);
  }
  function scheduleRenewal(seconds = 900) {
    stopTimer();
    timer = schedule(() => {
      renew().catch((error) => {
        if (!(error instanceof SessionChangedError) && credentials.session) scheduleRenewal(90);
      });
    }, Math.max(15, seconds - 60) * 1000);
  }
  function renew() {
    if (renewPromise) return renewPromise;
    const version = generation;
    const pending = (async () => {
      await load();
      check(version);
      if (!credentials.session) return null;
      if (!credentials.session.next_refresh_token) {
        credentials.session.next_refresh_token = replacement(credentials.session.refresh_token);
      }
      // A previous storage failure may have left the replacement only in
      // memory. Confirm it is saved before every exchange, including retries.
      await persist(version);
      check(version);
      const session = { ...credentials.session };
      let data;
      try {
        data = await request("/auth/refresh", { refresh_token: session.refresh_token,
          next_refresh_token: session.next_refresh_token });
      } catch (error) {
        check(version);
        if (error.status === 401) await invalidate();
        throw error;
      }
      check(version);
      if (!data.access_token || data.refresh_token !== session.next_refresh_token) throw new Error("Unable to renew your session. Please retry.");
      credentials.session = { ...session, refresh_token: data.refresh_token, next_refresh_token: null };
      await persist(version);
      tokens.set(data.access_token);
      scheduleRenewal(data.expires_in);
      return data.access_token;
    })();
    renewPromise = pending;
    pending.finally(() => { if (renewPromise === pending) renewPromise = null; }).catch(() => {});
    return pending;
  }
  return {
    hasSession: () => desktop() && Boolean(credentials.session),
    renew,
    invalidate,
    async restore() {
      if (!desktop()) return tokens.get();
      const version = generation;
      await load();
      check(version);
      await flushRevocations(version);
      return credentials.session ? renew() : tokens.get();
    },
    async login(sendLogin) {
      const version = ++generation;
      stopTimer();
      // A pending renewal can finish, but cannot publish credentials again.
      renewPromise = null;
      await load();
      check(version);
      await flushRevocations(version);
      const extraRevocation = credentials.session && !credentials.pending_revocations.includes(credentials.session.revocation_token) ? 1 : 0;
      if (credentials.pending_revocations.length + extraRevocation >= 32) {
        throw new Error("Connect to the internet to finish signing out of earlier sessions, then retry.");
      }
      const data = await sendLogin();
      if (version !== generation) {
        if (data.revocation_token) {
          queueRevocation(data);
          await persist(generation).catch(() => {});
          await flushRevocations().catch(() => {});
        }
      }
      check(version);
      if (!data.refresh_token || !data.revocation_token) throw new Error("This server needs an update before it can save desktop logins.");
      queueRevocation(credentials.session);
      credentials.session = { refresh_token: data.refresh_token,
        revocation_token: data.revocation_token, next_refresh_token: null };
      try {
        await persist(version);
      } catch (error) {
        await request("/auth/logout", { revocation_token: data.revocation_token }).catch(() => {});
        throw error;
      }
      check(version);
      tokens.set(data.access_token);
      scheduleRenewal(data.expires_in);
      flushRevocations(version).catch(() => {});
      return data;
    },
    async logout() {
      const version = ++generation;
      stopTimer();
      renewPromise = null;
      tokens.clear();
      await load();
      check(version);
      await flushRevocations(version);
      queueRevocation(credentials.session);
      credentials.session = null;
      try { await persist(version); }
      finally { await flushRevocations(version); }
    },
  };
}
