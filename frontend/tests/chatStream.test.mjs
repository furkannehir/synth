import assert from "node:assert/strict";
import test from "node:test";
import { connectChatStream } from "../src/api/chatStream.js";
import { TOKEN_CHANGED_EVENT } from "../src/api/tokenStore.js";

const flush = () => new Promise((resolve) => setTimeout(resolve, 0));

test("renewed credentials reopen the stream and ignore frames from the old connection", async () => {
  const sources = [], received = [], events = new EventTarget();
  let token = "old-token";
  class Source {
    constructor(url) { this.url = url; sources.push(this); }
    close() { this.closed = true; }
  }
  const disconnect = connectChatStream({
    url: () => `/events?token=${token}`, EventSourceImpl: Source, events,
    loadHistory: async () => [], onHistory() {}, onError() {}, onEvent: (event) => received.push(event),
  });
  await flush();
  token = "new-token";
  events.dispatchEvent(new Event(TOKEN_CHANGED_EVENT));
  assert.equal(sources[0].closed, true);
  assert.equal(sources[1].url, "/events?token=new-token");
  sources[0].onmessage({ data: JSON.stringify({ type: "message", data: "stale" }) });
  sources[1].onmessage({ data: JSON.stringify({ type: "message", data: "fresh" }) });
  assert.deepEqual(received, [{ type: "message", data: "fresh" }]);
  disconnect();
  events.dispatchEvent(new Event(TOKEN_CHANGED_EVENT));
  assert.equal(sources.length, 2);
});

function setup() {
  const requests = [], histories = [], events = [], errors = [];
  let source;
  class FakeEventSource {
    constructor(url) {
      this.url = url;
      source = this;
    }
    open() { this.onopen(); }
    emit(event, id = "") {
      this.onmessage({ data: JSON.stringify(event), lastEventId: String(id) });
    }
    close() { this.closed = true; }
  }
  const disconnect = connectChatStream({
    url: "/chat/events",
    EventSourceImpl: FakeEventSource,
    loadHistory: () => new Promise((resolve, reject) => requests.push({ resolve, reject })),
    onHistory: (history) => histories.push(history),
    onEvent: (event) => events.push(event),
    onError: (error) => errors.push(error.message),
  });
  return { source, disconnect, requests, histories, events, errors };
}

test("loads history even if streaming is unavailable", async () => {
  const s = setup();
  assert.equal(s.source.url, "/chat/events");
  s.requests[0].resolve({ messages: [{ id: "initial" }] });
  await flush();
  assert.equal(s.histories[0].messages[0].id, "initial");
  s.disconnect();
});

test("orders new messages, edits and deletes after an in-flight snapshot", async () => {
  const s = setup();
  const updates = [
    { type: "message", data: { id: "new", content: "first" } },
    { type: "message_edit", data: { id: "new", content: "edited" } },
    { type: "message_delete", data: { id: "old" } },
  ];
  updates.forEach((event) => s.source.emit(event));
  assert.deepEqual(s.events, []);
  s.requests[0].resolve({ messages: [{ id: "old", content: "old" }] });
  await flush();
  let messages = s.histories[0].messages;
  for (const event of s.events) {
    if (event.type === "message") messages.push(event.data);
    if (event.type === "message_edit") {
      messages = messages.map((m) => m.id === event.data.id ? event.data : m);
    }
    if (event.type === "message_delete") messages = messages.filter((m) => m.id !== event.data.id);
  }
  assert.deepEqual(messages, [{ id: "new", content: "edited" }]);
  s.disconnect();
});

test("reloads on opening and reconnecting without closing the source on errors", async () => {
  const s = setup();
  s.requests[0].resolve({ messages: [] });
  await flush();
  s.source.open();
  s.source.emit({ type: "connected", data: { revision: 3 } }, 0);
  s.requests[1].resolve({ messages: [{ id: "before-reconnect" }] });
  await flush();
  s.source.onerror();
  assert.equal(s.source.closed, undefined);
  s.source.open();
  s.source.emit({ type: "connected", data: { revision: 5 } }, 3);
  s.requests[2].resolve({ messages: [{ id: "missed-while-offline" }] });
  await flush();
  assert.equal(s.histories.at(-1).messages[0].id, "missed-while-offline");
  s.disconnect();
});

test("does not replay an old receipt or edit over a newer history snapshot", async () => {
  const s = setup();
  s.source.open();
  s.source.emit({ type: "connected", data: { revision: 5 } }, 1);
  s.source.emit({ type: "dm_read", data: { by: "friend" } }, 2);
  s.source.emit({ type: "dm_edit", data: { id: "own", content: "stale" } }, 3);
  s.source.emit({ type: "dm", data: { id: "own", content: "old" } }, 4);
  s.source.emit({ type: "dm_delete", data: { id: "removed" } }, 6);
  const snapshot = { messages: [{ id: "own", content: "latest", is_read: false }] };
  s.requests[0].resolve(snapshot);
  await flush();
  assert.deepEqual(s.events, [{ type: "dm_delete", data: { id: "removed" } }]);
  // Opening during the initial request triggers a second snapshot after connection.
  s.requests[1].resolve(snapshot);
  await flush();
  s.source.emit({ type: "dm_read", data: { by: "friend" } }, 7);
  assert.equal(s.events.at(-1).type, "dm_read");
  assert.equal(s.histories.at(-1).messages[0].is_read, false);
  s.disconnect();
});

test("coalesces expired-history resyncs and keeps updates newer than the resync", async () => {
  const s = setup();
  s.requests[0].resolve({ messages: [] });
  await flush();
  s.source.emit({ type: "resync", data: {} }, 100);
  s.source.emit({ type: "dm", data: { id: "covered" } }, 101);
  s.source.emit({ type: "resync", data: {} }, 102);
  s.source.emit({ type: "resync", data: {} }, 103);
  s.source.emit({ type: "dm", data: { id: "after-resync" } }, 104);
  assert.equal(s.requests.length, 2);
  s.requests[1].resolve({ messages: [{ id: "latest" }] });
  await flush();
  assert.deepEqual(s.events, [{ type: "dm", data: { id: "after-resync" } }]);
  assert.equal(s.requests.length, 3);
  s.requests[2].resolve({ messages: [{ id: "latest" }, { id: "after-resync" }] });
  await flush();
  assert.equal(s.requests.length, 3);
  assert.equal(s.histories.at(-1).messages.length, 2);
  s.disconnect();
});

test("ignores late snapshots and events after switching chats", async () => {
  const s = setup();
  s.source.emit({ type: "message", data: { id: "old-chat" } });
  s.disconnect();
  s.requests[0].resolve({ messages: [{ id: "old-chat" }] });
  s.source.emit({ type: "message", data: { id: "late" } });
  s.source.open();
  await flush();
  assert.deepEqual(s.histories, []);
  assert.deepEqual(s.events, []);
  assert.equal(s.requests.length, 1);
  assert.equal(s.source.closed, true);
});

test("reports history errors while still delivering buffered updates", async () => {
  const s = setup();
  s.source.emit({ type: "message", data: { id: "live" } });
  s.requests[0].reject(new Error("History unavailable"));
  await flush();
  assert.deepEqual(s.errors, ["History unavailable"]);
  assert.equal(s.events[0].data.id, "live");
  s.source.open();
  s.requests[1].resolve({ messages: [{ id: "recovered" }] });
  await flush();
  assert.equal(s.histories[0].messages[0].id, "recovered");
  s.disconnect();
});

test("ignores malformed frames and connection metadata", async () => {
  const s = setup();
  for (const data of ["not json", "null", "{}", '"a string"']) {
    s.source.onmessage({ data, lastEventId: "" });
  }
  s.source.emit({ type: "connected", data: {} });
  s.requests[0].resolve({ messages: [] });
  await flush();
  assert.deepEqual(s.events, []);
  assert.deepEqual(s.errors, []);
  s.disconnect();
});
