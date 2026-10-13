import assert from "node:assert/strict";
import test from "node:test";
import { startPresence, stopPresence } from "../src/api/presenceLifecycle.js";

function environment(token = "original-token", sessionId = "lease-a") {
  const beats = [], offline = [], cancelled = [];
  let tick;
  const stop = startPresence({ token, sessionId,
    heartbeat: (...args) => { beats.push(args); return Promise.resolve(); },
    offline: (...args) => { offline.push(args); return Promise.resolve(); },
    schedule: (callback, milliseconds) => { tick = callback; assert.equal(milliseconds, 30_000); return 42; },
    cancel: (timer) => cancelled.push(timer),
  });
  return { beats, offline, cancelled, stop, tick: () => tick() };
}

test("cleanup uses the original token and lease after credentials have been cleared", () => {
  const s = environment();
  assert.deepEqual(s.beats, [["original-token", "lease-a"]]);
  s.stop();
  assert.deepEqual(s.offline, [["original-token", "lease-a"]]);
  assert.deepEqual(s.cancelled, [42]);
  s.tick();
  assert.equal(s.beats.length, 1);
});

test("logout dispatches offline synchronously and subsequent effect cleanup is harmless", () => {
  const s = environment();
  assert.equal(stopPresence("original-token"), 1);
  assert.equal(s.offline.length, 1);
  s.stop();
  assert.equal(s.offline.length, 1);
  assert.equal(stopPresence("original-token"), 0);
});

test("an earlier login's cleanup leaves the current login's heartbeat running", () => {
  const previous = environment("old-token");
  const current = environment("new-token", "lease-b");
  assert.equal(stopPresence("old-token"), 1);
  current.tick();
  assert.equal(current.beats.length, 2);
  assert.equal(current.offline.length, 0);
  previous.stop();
  current.stop();
});

test("effect restarts close only their own lease, including when the token is unchanged", () => {
  const previous = environment("token", "lease-a");
  previous.stop();
  const current = environment("token", "lease-b");
  assert.deepEqual(previous.offline, [["token", "lease-a"]]);
  assert.deepEqual(current.beats, [["token", "lease-b"]]);
  previous.tick();
  assert.equal(previous.beats.length, 1);
  current.stop();
});

test("offline is sent while a heartbeat is still in flight", async () => {
  let finish;
  const heartbeat = new Promise((resolve) => { finish = resolve; });
  const offline = [];
  const stop = startPresence({ token: "token", sessionId: "lease-a",
    heartbeat: () => heartbeat,
    offline: (...args) => { offline.push(args); return Promise.resolve(); },
    schedule: () => 1, cancel: () => {},
  });
  stop();
  assert.deepEqual(offline, [["token", "lease-a"]]);
  finish();
  await heartbeat;
  assert.equal(offline.length, 1);
});

test("network failures do not prevent heartbeat cleanup or local logout", async () => {
  const cancelled = [];
  const stop = startPresence({ token: "token", sessionId: "lease-a",
    heartbeat: () => Promise.reject(new Error("network unavailable")),
    offline: () => Promise.reject(new Error("network unavailable")),
    schedule: () => 1, cancel: (id) => cancelled.push(id),
  });
  stop();
  await new Promise((resolve) => setImmediate(resolve));
  assert.deepEqual(cancelled, [1]);
  assert.equal(stopPresence("token"), 0);
});
