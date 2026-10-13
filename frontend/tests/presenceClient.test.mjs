import assert from "node:assert/strict";
import test from "node:test";
import { build } from "esbuild";
import { fileURLToPath } from "node:url";

// Load the production client with Vite's environment constant substituted.
const bundle = await build({
  entryPoints: [fileURLToPath(new URL("../src/api/client.js", import.meta.url))],
  bundle: true, write: false, format: "esm", platform: "node",
  define: { "import.meta.env.VITE_API_URL": '"/api"' },
});
const { presence } = await import(`data:text/javascript;base64,${Buffer.from(bundle.outputFiles[0].text).toString("base64")}`);

function setup(t, token) {
  const values = new Map([["synth_token", token]]);
  const calls = [];
  const storage = { getItem: (key) => values.get(key) ?? null, removeItem: (key) => values.delete(key) };
  t.mock.method(globalThis, "fetch", async (url, options) => {
    calls.push({ url, options });
    return { ok: true, json: async () => ({ message: "ok" }) };
  });
  for (const [name, value] of [["localStorage", storage], ["window", new EventTarget()]]) {
    const original = Object.getOwnPropertyDescriptor(globalThis, name);
    Object.defineProperty(globalThis, name, { configurable: true, value });
    t.after(() => {
      if (original) Object.defineProperty(globalThis, name, original);
      else Reflect.deleteProperty(globalThis, name);
    });
  }
  return { values, calls, storage };
}

test("offline retains outgoing credentials when local storage is cleared immediately", async (t) => {
  const s = setup(t, "old-token");
  const pending = presence.offline("old-token", "lease-a");
  s.storage.removeItem("synth_token");
  await pending;
  assert.equal(s.calls[0].url, "/api/presence/offline");
  assert.equal(s.calls[0].options.headers.Authorization, "Bearer old-token");
  assert.equal(s.calls[0].options.keepalive, true);
  assert.deepEqual(JSON.parse(s.calls[0].options.body), { session_id: "lease-a" });
  assert.equal("token" in s.calls[0].options, false);
});

test("cleanup cannot accidentally send a newer login's token", async (t) => {
  const s = setup(t, "new-token");
  await presence.offline("old-token", "old-lease");
  assert.equal(s.calls[0].options.headers.Authorization, "Bearer old-token");
  assert.equal(s.storage.getItem("synth_token"), "new-token");
});

test("a rejected old offline request does not expire a newer login", async (t) => {
  const s = setup(t, "new-token");
  t.mock.method(globalThis, "fetch", async () => ({ ok: false, status: 401, json: async () => ({ error: "expired" }) }));
  await assert.rejects(presence.offline("old-token", "old-lease"), /expired/);
  assert.equal(s.storage.getItem("synth_token"), "new-token");
});
