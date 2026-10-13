import assert from "node:assert/strict";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { build } from "esbuild";
import { loadEnv } from "vite";

const production = loadEnv("production", fileURLToPath(new URL("../", import.meta.url)), "VITE_");
const bundle = await build({
  entryPoints: [fileURLToPath(new URL("../src/api/client.js", import.meta.url))],
  bundle: true, write: false, format: "esm", platform: "node",
  define: { "import.meta.env": JSON.stringify(production) },
});
const { servers, messages, dms } = await import(`data:text/javascript;base64,${Buffer.from(bundle.outputFiles[0].text).toString("base64")}`);

function storage(t) {
  const original = Object.getOwnPropertyDescriptor(globalThis, "localStorage");
  Object.defineProperty(globalThis, "localStorage", { configurable: true, value: {
    getItem: () => "isolated-test-token",
  } });
  t.after(() => {
    if (original) Object.defineProperty(globalThis, "localStorage", original);
    else Reflect.deleteProperty(globalThis, "localStorage");
  });
}

test("the production client sends authenticated API requests to the new domain", async (t) => {
  storage(t);
  const requests = [];
  t.mock.method(globalThis, "fetch", async (url, options) => {
    requests.push({ url, options });
    return { ok: true, json: async () => ({ servers: [] }) };
  });
  await servers.list();
  assert.equal(requests[0].url, "https://synthapp.io/api/servers");
  assert.equal(requests[0].options.headers.Authorization, "Bearer isolated-test-token");
});

test("member, channel, and DM realtime URLs use the same new API domain", (t) => {
  storage(t);
  for (const link of [servers.membersStreamUrl("server"), messages.eventsUrl("channel"), dms.eventsUrl("friend")]) {
    const url = new URL(link);
    assert.equal(url.origin, "https://synthapp.io");
    assert.equal(url.pathname.startsWith("/api/"), true);
    assert.equal(url.searchParams.get("token"), "isolated-test-token");
  }
});
