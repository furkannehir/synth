import assert from "node:assert/strict";
import test from "node:test";
import { createChannelState, mergeChannelMessages } from "../src/api/channelMessages.js";

function message(id, overrides = {}) {
  return { id, content: "original", created_at: "2026-10-13T12:00:00.123Z", edited_at: null, ...overrides };
}

test("out-of-order live messages at the same millisecond retain the correct oldest cursor", () => {
  const messages = mergeChannelMessages([message("0003")], [message("0001"), message("0002")]);
  assert.deepEqual(messages.map((m) => m.id), ["0001", "0002", "0003"]);
  assert.equal(messages[0].id, "0001");
});

test("overlapping older pages and live messages merge without duplicates", () => {
  const current = [message("0002"), message("0003")];
  const older = [message("0001"), message("0002")];
  const merged = mergeChannelMessages(current, older);
  assert.deepEqual(merged.map((m) => m.id), ["0001", "0002", "0003"]);
  assert.deepEqual(current.map((m) => m.id), ["0002", "0003"]);
});

test("creation time takes precedence over message IDs across milliseconds", () => {
  const merged = mergeChannelMessages([message("0001", { created_at: "2026-10-13T12:00:00.124Z" })],
    [message("ffff"), message("0002")]);
  assert.deepEqual(merged.map((m) => m.id), ["0002", "ffff", "0001"]);
});

test("a stale page or send echo cannot overwrite a newer live edit", () => {
  const edited = message("0002", { content: "edited", edited_at: "2026-10-13T12:01:00.000Z" });
  const staleEdit = message("0002", { content: "stale edit", edited_at: "2026-10-13T12:00:30.000Z" });
  const merged = mergeChannelMessages([edited], [message("0001"), message("0002"), staleEdit]);
  assert.equal(merged[1].content, "edited");
  assert.equal(merged[1].edited_at, edited.edited_at);
});

test("an edit made in the creation millisecond survives an unedited echo", () => {
  const edited = message("0001", { content: "edited", edited_at: "2026-10-13T12:00:00.123Z" });
  assert.equal(mergeChannelMessages([edited], [message("0001")])[0].content, "edited");
});

const channelMessage = (id, channel = "channel-a", overrides = {}) => message(id, { channel_id: channel, ...overrides });

for (const operation of ["history", "page", "send", "edit", "delete"]) {
  test(`a delayed ${operation} response from a previous channel is ignored`, async () => {
    const previous = createChannelState("channel-a");
    previous.replaceHistory([channelMessage("old")]);
    const version = previous.historyVersion;
    let resolve;
    const pending = new Promise((done) => { resolve = done; });
    const reply = pending.then(() => {
      switch (operation) {
        case "history": return previous.replaceHistory([channelMessage("late")]);
        case "page": return previous.prependPage([channelMessage("late")], version);
        case "send": return previous.merge([channelMessage("late")]);
        case "edit": return previous.applyEvent({ type: "message_edit", data: channelMessage("old", "channel-a", { content: "late" }) });
        case "delete": return previous.applyEvent({ type: "message_delete", data: { id: "old" } });
      }
    });
    previous.close();
    const selected = createChannelState("channel-b");
    selected.replaceHistory([channelMessage("selected", "channel-b")]);
    resolve();
    assert.equal(await reply, null);
    assert.deepEqual(selected.merge([]).map((m) => m.id), ["selected"]);
  });
}

test("switching away and back cannot revive requests from the first visit", () => {
  const previous = createChannelState("channel-a");
  previous.close();
  const reopened = createChannelState("channel-a");
  assert.equal(previous.merge([channelMessage("late")]), null);
  assert.deepEqual(reopened.merge([]), []);
});

test("a page begun before a newer history snapshot cannot change that snapshot", () => {
  const scope = createChannelState("channel-a");
  scope.replaceHistory([channelMessage("original")]);
  const version = scope.historyVersion;
  scope.replaceHistory([channelMessage("current")]);
  assert.equal(scope.prependPage([channelMessage("old-page")], version), null);
  assert.deepEqual(scope.merge([]).map((m) => m.id), ["current"]);
});

test("deleted messages cannot reappear through pages, snapshots, or delayed send echoes", () => {
  const scope = createChannelState("channel-a");
  const removed = channelMessage("removed");
  scope.replaceHistory([removed]);
  scope.applyEvent({ type: "message_delete", data: { id: removed.id } });
  assert.deepEqual(scope.prependPage([removed], scope.historyVersion), []);
  assert.deepEqual(scope.replaceHistory([removed]), []);
  assert.deepEqual(scope.merge([removed]), []);
});

test("a stale HTTP edit cannot overwrite a newer live edit", () => {
  const scope = createChannelState("channel-a");
  scope.replaceHistory([channelMessage("edited")]);
  scope.applyEvent({ type: "message_edit", data: channelMessage("edited", "channel-a", {
    content: "new", edited_at: "2026-10-13T12:02:00.000Z",
  }) });
  const merged = scope.applyEvent({ type: "message_edit", data: channelMessage("edited", "channel-a", {
    content: "old", edited_at: "2026-10-13T12:01:00.000Z",
  }) });
  assert.equal(merged[0].content, "new");
});

test("a history snapshot preserves successful sends and edits made while it was pending", () => {
  const scope = createChannelState("channel-a");
  scope.replaceHistory([channelMessage("original")]);
  const version = scope.mutationVersion;
  scope.merge([channelMessage("sent")]);
  scope.applyEvent({ type: "message_edit", data: channelMessage("original", "channel-a", {
    content: "edited", edited_at: "2026-10-13T12:02:00.000Z",
  }) });
  const updated = scope.replaceHistory([channelMessage("original")], version);
  assert.deepEqual(updated.map((m) => m.id), ["original", "sent"]);
  assert.equal(updated[0].content, "edited");
});

test("responses belonging to another channel cannot be merged", () => {
  const scope = createChannelState("channel-a");
  assert.deepEqual(scope.merge([channelMessage("foreign", "channel-b")]), []);
  assert.deepEqual(scope.applyEvent({ type: "message", data: channelMessage("foreign", "channel-b") }), []);
});

test("editing an unloaded message does not append it to the visible history", () => {
  const scope = createChannelState("channel-a");
  assert.deepEqual(scope.applyEvent({ type: "message_edit", data: channelMessage("unloaded") }), []);
});
