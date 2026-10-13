import assert from "node:assert/strict";
import test from "node:test";
import { rejectSession, SESSION_EXPIRED_EVENT } from "../src/api/session.js";

function environment(token) {
  const values = new Map(token ? [["synth_token", token]] : []);
  return {
    storage: { getItem: (key) => values.get(key) ?? null, removeItem: (key) => values.delete(key) },
    events: new EventTarget(),
  };
}

test("a rejected current session clears credentials and notifies the UI", () => {
  const env = environment("current-token");
  const received = [];
  env.events.addEventListener(SESSION_EXPIRED_EVENT, (event) => received.push(event));
  assert.equal(rejectSession("current-token", env), true);
  assert.equal(env.storage.getItem("synth_token"), null);
  assert.equal(received.length, 1);
  assert.equal(received[0].detail, undefined);
  assert.equal(rejectSession("current-token", env), false);
  assert.equal(received.length, 1);
});

test("a late rejection from an old request preserves a newer login", () => {
  const env = environment("new-token");
  let notified = false;
  env.events.addEventListener(SESSION_EXPIRED_EVENT, () => { notified = true; });
  assert.equal(rejectSession("old-token", env), false);
  assert.equal(env.storage.getItem("synth_token"), "new-token");
  assert.equal(notified, false);
});

test("unauthenticated requests cannot clear a subsequently stored session", () => {
  const env = environment("new-token");
  assert.equal(rejectSession(null, env), false);
  assert.equal(env.storage.getItem("synth_token"), "new-token");
});
