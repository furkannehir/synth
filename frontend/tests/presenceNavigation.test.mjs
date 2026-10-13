import assert from "node:assert/strict";
import { after, afterEach, beforeEach, test } from "node:test";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { build } from "esbuild";
import { JSDOM } from "jsdom";

const dom = new JSDOM("<div id='root'></div>", { url: "https://synthapp.io/" });
for (const [key, value] of Object.entries({ window: dom.window, document: dom.window.document, navigator: dom.window.navigator, IS_REACT_ACT_ENVIRONMENT: true })) Object.defineProperty(globalThis, key, { configurable: true, value });
const sources = [];
class Source { constructor(url) { this.url = url; sources.push(this); } close() { this.closed = true; } }
globalThis.EventSource = Source;
const bundle = await build({
  entryPoints: [fileURLToPath(new URL("../src/context/ServerPresenceContext.jsx", import.meta.url))], bundle: true, write: false, format: "cjs", platform: "node", packages: "external", jsx: "automatic",
  plugins: [{ name: "presence-fixtures", setup(builder) {
    builder.onLoad({ filter: /[\\/]context[\\/]AuthContext\.jsx$/ }, () => ({ contents: 'export function useAuth() { return { accessToken: "fixture-token" }; }', loader: "jsx" }));
    builder.onLoad({ filter: /[\\/]api[\\/]client\.js$/ }, () => ({ contents: 'export const servers = { membersStreamUrl: (id) => "/members/" + id };', loader: "js" }));
  } }],
});
const module = { exports: {} };
new Function("require", "module", "exports", bundle.outputFiles[0].text)(createRequire(import.meta.url), module, module.exports);
const { ServerPresenceProvider, useServerPresence } = module.exports;
const { act, createElement } = await import("react");
const { createRoot } = await import("react-dom/client");
let root;
function Probe() { const snapshot = useServerPresence(); return createElement("output", null, JSON.stringify(snapshot)); }
async function render(server) { await act(async () => root.render(createElement(ServerPresenceProvider, { server }, createElement(Probe)))); }
async function message(source, name) { await act(async () => source.onmessage({ data: JSON.stringify({ members: [{ id: name, username: name }], voice_channels: { lounge: [{ name }] } }) })); }
const value = () => JSON.parse(document.querySelector("output").textContent);
beforeEach(() => { sources.length = 0; root = createRoot(document.getElementById("root")); });
afterEach(async () => { await act(async () => root.unmount()); });
after(() => { dom.window.close(); delete globalThis.EventSource; });

test("switching servers hides the previous roster and ignores delayed events", async () => {
  await render({ id: "first" }); const old = sources[0]; await message(old, "Mina");
  await render({ id: "second" });
  assert.ok(old.closed); assert.deepEqual(value().members, []); assert.deepEqual(value().voiceChannels, {});
  await message(old, "Old event"); assert.deepEqual(value().members, []);
  await message(sources[1], "Leo"); assert.equal(value().members[0].username, "Leo");
});

test("opening direct messages clears server presence and closes its stream", async () => {
  await render({ id: "server" }); const old = sources[0]; await message(old, "Mina");
  await render(null); assert.ok(old.closed);
  assert.deepEqual(value(), { members: [], voiceChannels: {}, connected: false });
  await message(old, "Late event"); assert.deepEqual(value().members, []);
});
