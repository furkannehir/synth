import assert from "node:assert/strict";
import test from "node:test";
import { createDesktopSession, SessionChangedError } from "../src/api/desktopSession.js";

const sid = "a".repeat(32);
const refresh = `${sid}.${"r".repeat(43)}`;
const revocation = `${sid}.${"v".repeat(43)}`;
const loginData = { access_token: "access-1", refresh_token: refresh, revocation_token: revocation, expires_in: 900 };
const flush = () => new Promise((resolve) => setTimeout(resolve, 0));

function setup(saved = { session: null, pending_revocations: [] }) {
  const s = { saved: structuredClone(saved), calls: [], writes: [], timers: [], token: null, expirations: 0 };
  s.storage = {
    read: async () => structuredClone(s.saved),
    write: async (data) => { s.saved = structuredClone(data); s.writes.push(structuredClone(data)); },
  };
  s.send = async (path, body) => {
    s.calls.push({ path, body, saved: structuredClone(s.saved) });
    if (path === "/auth/logout") return {};
    return { access_token: "renewed-access", refresh_token: body.next_refresh_token, expires_in: 900 };
  };
  s.manager = () => createDesktopSession({
    storage: s.storage, request: (...args) => s.send(...args), desktop: () => true,
    tokens: { get: () => s.token, set: (token) => { s.token = token; }, clear: () => { s.token = null; } },
    expired: () => { s.expirations++; },
    schedule: (callback, delay) => { const timer = { callback, delay }; s.timers.push(timer); return timer; },
    cancel: (timer) => { timer.cancelled = true; },
  });
  s.client = s.manager();
  return s;
}

test("desktop login persists renewable credentials without access tokens or passwords", async () => {
  const s = setup();
  await s.client.login(async () => loginData);
  assert.deepEqual(s.saved.session, { refresh_token: refresh, revocation_token: revocation, next_refresh_token: null });
  assert.equal(JSON.stringify(s.saved).includes("access-1"), false);
  assert.equal(s.token, "access-1");
  assert.equal(s.timers.at(-1).delay, 840000);
});

test("a fresh process restores saved login and persists the replacement before renewal", async () => {
  const s = setup();
  await s.client.login(async () => loginData);
  s.token = null;
  const restarted = s.manager();
  assert.equal(await restarted.restore(), "renewed-access");
  const call = s.calls.find(({ path }) => path === "/auth/refresh");
  assert.equal(call.saved.session.next_refresh_token, call.body.next_refresh_token);
  assert.equal(s.saved.session.refresh_token, call.body.next_refresh_token);
  assert.equal(s.saved.session.next_refresh_token, null);
});

test("an interrupted renewal retries the same saved token pair after restart", async () => {
  const s = setup();
  await s.client.login(async () => loginData);
  s.send = async (path, body) => { s.calls.push({ path, body }); throw new Error("offline"); };
  await assert.rejects(s.client.renew(), /offline/);
  const attempted = s.calls.at(-1).body;
  assert.equal(s.saved.session.refresh_token, refresh);
  assert.equal(s.saved.session.next_refresh_token, attempted.next_refresh_token);
  s.send = async (path, body) => {
    assert.deepEqual(body, attempted);
    return { access_token: "recovered", refresh_token: body.next_refresh_token, expires_in: 900 };
  };
  assert.equal(await s.manager().restore(), "recovered");
});

test("simultaneous requests share a single renewal", async () => {
  const s = setup();
  await s.client.login(async () => loginData);
  await Promise.all(Array.from({ length: 10 }, () => s.client.renew()));
  assert.equal(s.calls.filter(({ path }) => path === "/auth/refresh").length, 1);
});

test("logout during renewal cannot restore memory or native credentials", async () => {
  const s = setup();
  await s.client.login(async () => loginData);
  let complete;
  s.send = (path, body) => path === "/auth/refresh" ? new Promise((resolve) => {
    complete = () => resolve({ access_token: "too-late", refresh_token: body.next_refresh_token, expires_in: 900 });
  }) : Promise.resolve({});
  const renewing = s.client.renew();
  const rejected = assert.rejects(renewing, SessionChangedError);
  await flush();
  await s.client.logout();
  complete();
  await rejected;
  assert.equal(s.token, null);
  assert.equal(s.saved.session, null);
  assert.equal(s.expirations, 0);
});

test("offline logout removes the login and retries revocation on the next startup", async () => {
  const s = setup();
  await s.client.login(async () => loginData);
  s.send = async () => { throw new Error("offline"); };
  await s.client.logout();
  assert.equal(s.saved.session, null);
  assert.deepEqual(s.saved.pending_revocations, [revocation]);
  const revoked = [];
  s.send = async (path, body) => { revoked.push({ path, body }); return {}; };
  assert.equal(await s.manager().restore(), null);
  assert.deepEqual(revoked, [{ path: "/auth/logout", body: { revocation_token: revocation } }]);
  assert.deepEqual(s.saved.pending_revocations, []);
});

test("a late rejection from an old renewal leaves the new account signed in", async () => {
  const s = setup();
  await s.client.login(async () => loginData);
  let rejectOld;
  s.send = (path) => path === "/auth/refresh" ? new Promise((resolve, reject) => { rejectOld = reject; }) : Promise.resolve({});
  const renewed = assert.rejects(s.client.renew(), SessionChangedError);
  await flush();
  const next = { ...loginData, access_token: "new-account", refresh_token: refresh.replaceAll("a", "b") };
  await s.client.login(async () => next);
  rejectOld(Object.assign(new Error("revoked"), { status: 401 }));
  await renewed;
  assert.equal(s.token, "new-account");
  assert.equal(s.saved.session.refresh_token, next.refresh_token);
  assert.equal(s.expirations, 0);
});

test("secure-store failure prevents consuming a refresh credential", async () => {
  const s = setup();
  await s.client.login(async () => loginData);
  s.storage.write = async () => { throw new Error("keychain locked"); };
  await assert.rejects(s.client.renew(), /keychain locked/);
  await assert.rejects(s.client.renew(), /keychain locked/);
  assert.equal(s.calls.some(({ path }) => path === "/auth/refresh"), false);
});

test("revoked persistent sessions clear the saved login and notify authentication", async () => {
  const s = setup();
  await s.client.login(async () => loginData);
  s.send = async () => { throw Object.assign(new Error("revoked"), { status: 401 }); };
  await assert.rejects(s.client.renew(), /revoked/);
  assert.equal(s.saved.session, null);
  assert.equal(s.token, null);
  assert.equal(s.expirations, 1);
});

test("a login response arriving after logout is revoked and never saved as a login", async () => {
  const s = setup();
  let finishLogin;
  const pending = assert.rejects(s.client.login(() => new Promise((resolve) => { finishLogin = resolve; })), SessionChangedError);
  await flush();
  await s.client.logout();
  finishLogin(loginData);
  await pending;
  assert.equal(s.saved.session, null);
  assert.equal(s.token, null);
  assert.equal(s.calls.some(({ path, body }) => path === "/auth/logout" && body.revocation_token === revocation), true);
});
