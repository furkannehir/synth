import assert from "node:assert/strict";
import { after, afterEach, beforeEach, test } from "node:test";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { build } from "esbuild";
import { JSDOM } from "jsdom";

const dom = new JSDOM("<div id='root'></div>", { url: "https://synthapp.io/" });
for (const [key, value] of Object.entries({ window: dom.window, document: dom.window.document, navigator: dom.window.navigator, IS_REACT_ACT_ENVIRONMENT: true })) Object.defineProperty(globalThis, key, { configurable: true, value });
const bundle = await build({
  entryPoints: [fileURLToPath(new URL("../src/pages/HomePage.jsx", import.meta.url))], bundle: true, write: false, format: "cjs", platform: "node", packages: "external", jsx: "automatic", define: { "import.meta.env": "{}" },
  plugins: [{ name: "channel-flow-fixtures", setup(builder) {
    builder.onLoad({ filter: /[\\/]api[\\/]client\.js$/ }, () => ({ loader: "js", contents: `
      export const channels = { list: async () => ({ channels: globalThis.channelFixture.channels }) };
      export const invites = {};
      export const dms = { unreadCount: async () => ({ unread_count: 0 }) };
      export const voice = { join: (...args) => globalThis.channelFixture.join(...args), leave: async () => ({}) };
      export const presence = { heartbeat: async () => ({}) };
    ` }));
    builder.onLoad({ filter: /[\\/]context[\\/]AuthContext\.jsx$/ }, () => ({ loader: "js", contents: 'export function useAuth() { return { user: { id: "self" } }; }' }));
    builder.onLoad({ filter: /[\\/]context[\\/]ServerPresenceContext\.jsx$/ }, () => ({ loader: "jsx", contents: 'export function ServerPresenceProvider({ children }) { return children; } export function useServerPresence() { return { voiceChannels: {}, members: [] }; }' }));
    builder.onLoad({ filter: /[\\/]components[\\/]ServerSidebar\.jsx$/ }, () => ({ loader: "jsx", contents: `
      export default function ServerSidebar({ children, onSelect }) { return <aside><button onClick={() => onSelect({ id: "server", name: "Sample server" })}>Open sample server</button>{children}</aside>; }
    ` }));
    builder.onLoad({ filter: /[\\/]components[\\/](FriendsPanel|DMPanel|MembersPanel|VoiceRoomBanner)\.jsx$/ }, () => ({ loader: "jsx", contents: 'export default function Fixture() { return null; }' }));
    builder.onLoad({ filter: /[\\/]components[\\/]TextPanel\.jsx$/ }, () => ({ loader: "jsx", contents: 'export default function TextPanel({ channel }) { return <section aria-label="Text conversation">{channel.name}</section>; }' }));
    builder.onResolve({ filter: /^@livekit\/components-react$/ }, () => ({ path: "livekit-fixture", namespace: "fixture" }));
    builder.onResolve({ filter: /^livekit-client$/ }, () => ({ path: "client-fixture", namespace: "client-fixture" }));
    builder.onLoad({ filter: /.*/, namespace: "fixture" }, () => ({ loader: "jsx", resolveDir: fileURLToPath(new URL("../", import.meta.url)), contents: `
      export function LiveKitRoom({ className, children }) { return <section data-testid="connected-room" className={className}>{children}</section>; }
      export function RoomAudioRenderer() { return null; } export function VideoTrack() { return null; }
      export function useParticipants() { return []; } export function useTracks() { return []; }
      export function useLocalParticipant() { return { localParticipant: { isMicrophoneEnabled: true } }; }
    ` }));
    builder.onLoad({ filter: /.*/, namespace: "client-fixture" }, () => ({ loader: "js", contents: 'export const Track = { Source: { Camera: "camera", ScreenShare: "screen_share" } }; export const Room = {}; export const createLocalVideoTrack = () => {}; export const createLocalScreenTracks = () => {}; export class LocalVideoTrack {}' }));
  } }],
});
const module = { exports: {} };
new Function("require", "module", "exports", bundle.outputFiles[0].text)(createRequire(import.meta.url), module, module.exports);
const HomePage = module.exports.default;
const { act, createElement } = await import("react");
const { createRoot } = await import("react-dom/client");
let root, joins;
beforeEach(() => {
  joins = [];
  globalThis.channelFixture = {
    channels: [
      { id: "text", server_id: "server", name: "General chat", type: "text" },
      { id: "voice", server_id: "server", name: "Lounge", type: "voice", user_limit: 0 },
    ],
    join: async (...args) => { joins.push(args); return { token: "fixture-token", url: "ws://fixture.invalid" }; },
  };
});
afterEach(async () => { if (root) await act(async () => root.unmount()); root = null; delete globalThis.channelFixture; });
after(() => dom.window.close());

async function openServer() {
  root = createRoot(document.getElementById("root"));
  await act(async () => root.render(createElement(HomePage)));
  await act(async () => [...document.querySelectorAll("button")].find((button) => button.textContent === "Open sample server").click());
}
async function clickJoin() { await act(async () => document.querySelector('[aria-label="Join Lounge"]').click()); }

test("the sidebar green button joins voice directly and selects the full voice view", async () => {
  await openServer();
  assert.ok(document.querySelector('[aria-label="Text conversation"]'));
  await clickJoin();
  assert.deepEqual(joins, [["server", "voice"]]);
  const room = document.querySelector('[data-testid="connected-room"]');
  assert.ok(room);
  assert.equal(room.classList.contains("floating-voice-room"), false);
  assert.equal(document.querySelector('[aria-label="Text conversation"]'), null);
  assert.equal(document.querySelector('[aria-label="Join Lounge"]').closest(".channel-nav-row").classList.contains("is-active"), true);
  await clickJoin();
  assert.equal(joins.length, 1, "Opening the room again must reuse the connection");
});

test("selecting the voice channel label leaves the green join action available", async () => {
  await openServer();
  await act(async () => [...document.querySelectorAll(".channel-nav-row > button")].find((button) => button.textContent === "Lounge").click());
  assert.equal(joins.length, 0);
  assert.ok(document.querySelector(".voice-ready"));
  await clickJoin();
  assert.deepEqual(joins, [["server", "voice"]]);
  assert.ok(document.querySelector('[data-testid="connected-room"]'));
});

test("a failed direct join leaves feedback visible and allows retry", async () => {
  const join = globalThis.channelFixture.join;
  globalThis.channelFixture.join = async () => { throw new Error("Room unavailable"); };
  await openServer(); await clickJoin();
  assert.match(document.querySelector(".voice-ready").textContent, /Room unavailable/);
  assert.equal(document.querySelector('[data-testid="connected-room"]'), null);
  assert.equal(document.querySelector('[aria-label="Join Lounge"]').disabled, false);
  globalThis.channelFixture.join = join;
  await clickJoin();
  assert.ok(document.querySelector('[data-testid="connected-room"]'));
});

test("repeated clicks while joining cannot create duplicate voice requests", async () => {
  let resolveJoin;
  globalThis.channelFixture.join = (...args) => { joins.push(args); return new Promise((resolve) => { resolveJoin = resolve; }); };
  await openServer();
  await act(async () => { const button = document.querySelector('[aria-label="Join Lounge"]'); button.click(); button.click(); });
  assert.equal(document.querySelector('[aria-label="Join Lounge"]').disabled, true);
  assert.equal(joins.length, 1);
  await act(async () => resolveJoin({ token: "fixture-token", url: "ws://fixture.invalid" }));
  assert.equal(document.querySelector('[aria-label="Join Lounge"]').disabled, false);
  assert.ok(document.querySelector('[data-testid="connected-room"]'));
});
