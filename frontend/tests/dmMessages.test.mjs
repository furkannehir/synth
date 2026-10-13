import assert from "node:assert/strict";
import test from "node:test";
import { applyDMEvent, mergeDMMessages } from "../src/api/dmMessages.js";

function message(id, overrides = {}) {
  return {
    id, sender_id: "me", recipient_id: "friend", content: "original", is_read: false,
    created_at: "2026-01-01T12:00:00.000Z", edited_at: null, ...overrides,
  };
}

test("a delayed receipt leaves newer and incoming messages unread", () => {
  const messages = [message("old"), message("new"), message("incoming", { sender_id: "friend", recipient_id: "me" })];
  const updated = applyDMEvent(messages, {
    type: "dm_read", data: { by: "friend", message_ids: ["old"] },
  }, "me");
  assert.deepEqual(updated.map((m) => m.is_read), [true, false, false]);
  assert.deepEqual(messages.map((m) => m.is_read), [false, false, false]);
});

test("a receipt from another recipient cannot mark the message read", () => {
  const updated = applyDMEvent([message("own")], {
    type: "dm_read", data: { by: "someone-else", message_ids: ["own"] },
  }, "me");
  assert.equal(updated[0].is_read, false);
});

test("legacy receipts without message IDs never mark every message read", () => {
  const updated = applyDMEvent([message("own")], { type: "dm_read", data: { by: "friend" } }, "me");
  assert.equal(updated[0].is_read, false);
});

test("own read acknowledgement does not mark outgoing messages seen", () => {
  const updated = applyDMEvent([message("own")], {
    type: "dm_read", data: { by: "me", message_ids: ["own"] },
  }, "me");
  assert.equal(updated[0].is_read, false);
});

test("a late send response cannot undo an edit or a read receipt", () => {
  const current = message("own", { content: "latest", edited_at: "2026-01-01T12:01:00.000Z", is_read: true });
  const updated = mergeDMMessages([current], [message("own")]);
  assert.equal(updated.length, 1);
  assert.equal(updated[0].content, "latest");
  assert.equal(updated[0].is_read, true);
  assert.equal(updated[0].edited_at, current.edited_at);
});

test("stale edit responses keep the newer version and newer read state", () => {
  const latest = message("own", { content: "latest", edited_at: "2026-01-01T12:02:00.000Z", is_read: true });
  const stale = message("own", { content: "stale", edited_at: "2026-01-01T12:01:00.000Z" });
  const updated = applyDMEvent([latest], { type: "dm_edit", data: stale }, "me");
  assert.equal(updated[0].content, "latest");
  assert.equal(updated[0].is_read, true);
  const newest = message("own", { content: "newest", edited_at: "2026-01-01T12:03:00.000Z" });
  assert.equal(applyDMEvent(updated, { type: "dm_edit", data: newest }, "me")[0].content, "newest");
});

test("an unedited echo at the same millisecond cannot erase an edit", () => {
  const edited = message("own", { content: "edited", edited_at: "2026-01-01T12:00:00.000Z" });
  assert.equal(mergeDMMessages([edited], [message("own")])[0].content, "edited");
});

test("out-of-order sends and overlapping pages stay sorted without duplicates", () => {
  const first = message("0001");
  const second = message("0002");
  const third = message("0003", { created_at: "2026-01-01T12:00:01.000Z" });
  const updated = mergeDMMessages([third, second], [first, second]);
  assert.deepEqual(updated.map((m) => m.id), ["0001", "0002", "0003"]);
  assert.deepEqual(applyDMEvent(updated, { type: "dm", data: second }, "me").map((m) => m.id), ["0001", "0002", "0003"]);
});

test("a late edit cannot resurrect a message removed by a delete event", () => {
  const deleted = applyDMEvent([message("own")], { type: "dm_delete", data: { id: "own" } }, "me");
  assert.deepEqual(deleted, []);
  assert.deepEqual(applyDMEvent(deleted, { type: "dm_edit", data: message("own") }, "me"), []);
});
