import assert from "node:assert/strict";
import { after, afterEach, beforeEach, test } from "node:test";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { build } from "esbuild";
import { JSDOM } from "jsdom";

const dom = new JSDOM("<div id='root'></div>", { url: "https://synthapp.io/" });
for (const [key, value] of Object.entries({ window: dom.window, document: dom.window.document, navigator: dom.window.navigator, IS_REACT_ACT_ENVIRONMENT: true })) Object.defineProperty(globalThis, key, { configurable: true, value });
const bundle = await build({
  entryPoints: [fileURLToPath(new URL("../src/components/VoicePanel.jsx", import.meta.url))], bundle: true, write: false, format: "cjs", platform: "node", packages: "external", jsx: "automatic",
  plugins: [{ name: "voice-ui-fixtures", setup(builder) {
    builder.onLoad({ filter: /[\\/]api[\\/]client\.js$/ }, () => ({ contents: 'export const voice = { join: (...args) => globalThis.voiceFixture.join(...args), leave: (...args) => globalThis.voiceFixture.leave(...args), participants: async () => ({ participants: [] }) }; export const presence = { heartbeat: async () => ({}) };', loader: "js" }));
    builder.onLoad({ filter: /[\\/]context[\\/]ServerPresenceContext\.jsx$/ }, () => ({ contents: 'export function useServerPresence() { return { voiceChannels: {}, members: [] }; }', loader: "jsx" }));
    builder.onResolve({ filter: /^@livekit\/components-react$/ }, () => ({ path: "livekit-fixture", namespace: "fixture" }));
    builder.onResolve({ filter: /^livekit-client$/ }, () => ({ path: "livekit-client-fixture", namespace: "client-fixture" }));
    builder.onLoad({ filter: /.*/, namespace: "client-fixture" }, () => ({ loader: "js", contents: `
      export const Track = { Source: { Camera: "camera", ScreenShare: "screen_share" } };
      export const Room = { getLocalDevices: (...args) => globalThis.voiceFixture.devices(...args) };
      export const createLocalVideoTrack = (...args) => globalThis.voiceFixture.createTrack(...args);
    ` }));
    builder.onLoad({ filter: /.*/, namespace: "fixture" }, () => ({ loader: "jsx", resolveDir: fileURLToPath(new URL("../", import.meta.url)), contents: `
      export function LiveKitRoom({ className, children }) { return <section className={className}>{children}</section>; }
      export function RoomAudioRenderer() { return null; }
      export function VideoTrack() { return null; }
      export function useParticipants() { return []; }
      export function useTracks() { return []; }
      export function useLocalParticipant() { return { localParticipant: globalThis.voiceFixture.participant }; }
    ` }));
  } }],
});
const module = { exports: {} };
new Function("require", "module", "exports", bundle.outputFiles[0].text)(createRequire(import.meta.url), module, module.exports);
const VoicePanel = module.exports.default;
const { act, createElement, createRef } = await import("react");
const { createRoot } = await import("react-dom/client");
let root, calls, tracks, captures, published;
function makeTrack(deviceId = "built-in") {
  const mediaStreamTrack = new dom.window.EventTarget();
  mediaStreamTrack.getSettings = () => ({ deviceId });
  const track = { mediaStreamTrack, deviceId, stopped: 0, attached: [], detached: [], attach(element) { this.attached.push(element); }, detach(element) { this.detached.push(element); }, stop() { this.stopped += 1; } };
  tracks.push(track);
  return track;
}
beforeEach(() => {
  calls = []; tracks = []; captures = []; published = null;
  Object.defineProperty(navigator, "mediaDevices", { configurable: true, value: new dom.window.EventTarget() });
  globalThis.voiceFixture = {
    join: async (...args) => { calls.push(["join", ...args]); return { token: "fixture-token", url: "ws://fixture.invalid" }; },
    leave: async (...args) => { calls.push(["leave", ...args]); },
    createTrack: async (options) => { captures.push(options); return makeTrack(options.deviceId?.exact); },
    devices: async () => [{ deviceId: "built-in", label: "Built-in camera" }, { deviceId: "usb", label: "USB camera" }, { deviceId: "virtual", label: "Virtual camera" }],
    participant: {
      identity: "self", isMicrophoneEnabled: true, setMicrophoneEnabled: async () => {},
      getTrackPublication: () => published ? { track: published } : undefined,
      publishTrack: async (track, options) => { calls.push(["publish", track, options]); published = track; },
      unpublishTrack: async (track, stop) => { calls.push(["unpublish", track, stop]); if (stop) track.stop(); published = null; },
    },
  };
});
afterEach(async () => { if (root) await act(async () => root.unmount()); root = null; delete globalThis.voiceFixture; });
after(() => dom.window.close());

test("joining from a text conversation targets the voice room and uses the floating controls", async () => {
  const ref = createRef();
  const room = { id: "voice-room", server_id: "server", type: "voice", name: "Lounge" };
  const navigation = [];
  root = createRoot(document.getElementById("root"));
  await act(async () => root.render(createElement(VoicePanel, { ref, activeChannel: { id: "text-room", server_id: "server", type: "text" }, onNavigate: (channel) => navigation.push(channel.id) })));
  await act(async () => ref.current.join(room));
  assert.deepEqual(calls, [["join", "server", "voice-room"]]);
  assert.ok(document.querySelector(".floating-voice-room"));
  await act(async () => ref.current.join(room));
  assert.deepEqual(navigation, ["voice-room"]);
  assert.equal(calls.length, 1, "Reopening the joined room should not create another grant");
  await act(async () => document.querySelector('[title="Disconnect"]').click());
  assert.deepEqual(calls.at(-1), ["leave", "server", "voice-room"]);
  assert.equal(document.querySelector(".floating-voice-room"), null);
});

test("a voice join failure remains visible when the user is reading a text channel", async () => {
  globalThis.voiceFixture.join = async () => { throw new Error("Room unavailable"); };
  const ref = createRef(); root = createRoot(document.getElementById("root"));
  await act(async () => root.render(createElement(VoicePanel, { ref, activeChannel: { id: "text", type: "text" }, onNavigate() {} })));
  await act(async () => ref.current.join({ id: "voice", server_id: "server", type: "voice" }));
  assert.equal(document.querySelector('[role="alert"]').textContent, "Room unavailable");
  assert.equal(document.querySelector(".floating-voice-room"), null);
});

async function openCamera(floating = true) {
  const ref = createRef();
  const room = { id: "voice-room", server_id: "server", type: "voice", name: "Lounge" };
  root = createRoot(document.getElementById("root"));
  await act(async () => root.render(createElement(VoicePanel, { ref, activeChannel: floating ? { id: "text-room", type: "text" } : room, onNavigate() {} })));
  await act(async () => ref.current.join(room));
  await act(async () => { const button = document.querySelector('[aria-label="Turn camera on"]'); button.focus(); button.click(); });
}
async function press(text) { await act(async () => [...document.querySelectorAll("button")].find((button) => button.textContent === text).click()); }
async function selectCamera(value) { await act(async () => { const select = document.querySelector("select"); select.value = value; select.dispatchEvent(new dom.window.Event("change", { bubbles: true })); }); }
function deferred() { let resolve, reject; const promise = new Promise((yes, no) => { resolve = yes; reject = no; }); return { promise, resolve, reject }; }

test("floating camera preview opens outside the clipped panel and cancelling stops capture", async () => {
  await openCamera();
  const dialog = document.querySelector('[role="dialog"]');
  assert.equal(dialog.closest(".floating-voice-room"), null);
  assert.equal(dialog.parentElement.parentElement, document.body);
  assert.deepEqual([...dialog.querySelectorAll("option")].map((option) => option.textContent), ["Built-in camera", "USB camera", "Virtual camera"]);
  assert.equal(document.querySelector("select").value, "built-in");
  assert.equal(tracks[0].stopped, 0);
  await press("Cancel");
  assert.equal(tracks[0].stopped, 1);
  assert.equal(document.querySelector('[role="dialog"]'), null);
  assert.ok(document.querySelector(".floating-voice-room"));
  assert.equal(published, null);
});

test("full voice view publishes the selected preview track and camera off releases it", async () => {
  await openCamera(false); await selectCamera("virtual");
  assert.equal(tracks[0].stopped, 1);
  assert.deepEqual(captures[1].deviceId, { exact: "virtual" });
  const selectedTrack = tracks[1];
  await press("Publish camera");
  assert.equal(published, selectedTrack);
  assert.deepEqual(calls.find(([kind]) => kind === "publish"), ["publish", selectedTrack, { source: "camera" }]);
  assert.equal(selectedTrack.stopped, 0, "Closing a successful preview must not stop the room's track");
  assert.equal(selectedTrack.detached.length, 1);
  assert.equal(document.querySelector('[role="dialog"]'), null);
  await act(async () => document.querySelector('[aria-label="Turn camera off"]').click());
  assert.equal(selectedTrack.stopped, 1);
  assert.equal(published, null);
});

test("publish failure keeps the preview and buttons available for retry", async () => {
  await openCamera();
  const publish = globalThis.voiceFixture.participant.publishTrack;
  globalThis.voiceFixture.participant.publishTrack = async () => { throw new Error("Publication failed"); };
  await press("Publish camera");
  assert.equal(document.querySelector('[role="alert"]').textContent, "Publication failed");
  assert.equal(tracks[0].stopped, 0);
  assert.equal([...document.querySelectorAll("button")].find((button) => button.textContent === "Publish camera").disabled, false);
  globalThis.voiceFixture.participant.publishTrack = publish;
  await press("Publish camera"); assert.equal(published, tracks[0]);
});

test("a camera permission failure can be retried without leaving the room", async () => {
  const create = globalThis.voiceFixture.createTrack;
  globalThis.voiceFixture.createTrack = async () => { throw Object.assign(new Error("Blocked"), { name: "NotAllowedError" }); };
  await openCamera();
  assert.match(document.querySelector('[role="alert"]').textContent, /Camera access was blocked/);
  assert.equal([...document.querySelectorAll("button")].find((button) => button.textContent === "Publish camera").disabled, true);
  globalThis.voiceFixture.createTrack = create;
  await press("Retry"); await press("Cancel");
  assert.equal(tracks[0].stopped, 1);
});

test("late camera capture after cancellation is stopped and never attached", async () => {
  const request = deferred(); globalThis.voiceFixture.createTrack = () => request.promise;
  await openCamera();
  assert.equal([...document.querySelectorAll("button")].find((button) => button.textContent === "Publish camera").disabled, true);
  await press("Cancel");
  const lateTrack = makeTrack();
  await act(async () => request.resolve(lateTrack));
  assert.equal(lateTrack.stopped, 1); assert.equal(lateTrack.attached.length, 0);
});

test("a slower previous camera cannot replace a newly selected source", async () => {
  const original = deferred(), replacement = deferred();
  globalThis.voiceFixture.createTrack = (options) => options.deviceId ? replacement.promise : original.promise;
  await openCamera(); await selectCamera("usb");
  const usbTrack = makeTrack("usb"), oldTrack = makeTrack();
  await act(async () => replacement.resolve(usbTrack));
  await act(async () => original.resolve(oldTrack));
  assert.equal(oldTrack.stopped, 1); assert.equal(oldTrack.attached.length, 0);
  assert.equal(document.querySelector("select").value, "usb");
  await press("Publish camera"); assert.equal(published, usbTrack);
});

test("cancelling an in-flight publication releases a late published track", async () => {
  const request = deferred();
  globalThis.voiceFixture.participant.publishTrack = async (track) => { await request.promise; published = track; };
  await openCamera(); await press("Publish camera");
  await press("Cancel");
  assert.equal(tracks[0].stopped, 0, "Capture stays alive until the SDK finishes the pending publication");
  await act(async () => request.resolve());
  assert.equal(published, null); assert.ok(tracks[0].stopped > 0);
  assert.ok(document.querySelector('[aria-label="Turn camera on"]'));
});

test("Escape closes the camera dialog and restores focus to the floating control", async () => {
  await openCamera();
  const close = document.querySelector('[aria-label="Close dialog"]');
  await act(async () => close.dispatchEvent(new dom.window.KeyboardEvent("keydown", { key: "Escape", bubbles: true })));
  assert.equal(document.querySelector('[role="dialog"]'), null);
  assert.equal(tracks[0].stopped, 1);
  assert.equal(document.activeElement.getAttribute("aria-label"), "Turn camera on");
});

test("cancelling while replacing an older camera never begins a new publication", async () => {
  const oldTrack = makeTrack(); published = oldTrack;
  const request = deferred();
  globalThis.voiceFixture.participant.unpublishTrack = async (track) => { await request.promise; track.stop(); published = null; };
  await openCamera(); await press("Publish camera"); await press("Cancel");
  await act(async () => request.resolve());
  assert.equal(calls.some(([kind]) => kind === "publish"), false);
  assert.equal(tracks[1].stopped, 1);
});

test("a disconnected preview camera disables publication and can be dismissed", async () => {
  await openCamera();
  await act(async () => tracks[0].mediaStreamTrack.dispatchEvent(new dom.window.Event("ended")));
  assert.match(document.querySelector('[role="alert"]').textContent, /camera disconnected/);
  assert.equal([...document.querySelectorAll("button")].find((button) => button.textContent === "Publish camera").disabled, true);
  await press("Cancel"); assert.equal(tracks[0].stopped, 1);
});
