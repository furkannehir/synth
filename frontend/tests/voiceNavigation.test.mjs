import assert from "node:assert/strict";
import { after, afterEach, beforeEach, test } from "node:test";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { build } from "esbuild";
import { JSDOM } from "jsdom";

const dom = new JSDOM("<div id='root'></div>", { url: "https://synthapp.io/" });
const defaultUserAgent = dom.window.navigator.userAgent;
for (const [key, value] of Object.entries({ window: dom.window, document: dom.window.document, navigator: dom.window.navigator, IS_REACT_ACT_ENVIRONMENT: true })) Object.defineProperty(globalThis, key, { configurable: true, value });
const bundle = await build({
  entryPoints: [fileURLToPath(new URL("../src/components/VoicePanel.jsx", import.meta.url))], bundle: true, write: false, format: "cjs", platform: "node", packages: "external", jsx: "automatic", define: { "import.meta.env": "globalThis.voiceFixture.env" },
  plugins: [{ name: "voice-ui-fixtures", setup(builder) {
    builder.onLoad({ filter: /[\\/]api[\\/]client\.js$/ }, () => ({ contents: 'export const voice = { join: (...args) => globalThis.voiceFixture.join(...args), leave: (...args) => globalThis.voiceFixture.leave(...args), participants: async () => ({ participants: [] }) }; export const presence = { heartbeat: async () => ({}) };', loader: "js" }));
    builder.onLoad({ filter: /[\\/]context[\\/]ServerPresenceContext\.jsx$/ }, () => ({ contents: 'export function useServerPresence() { return { voiceChannels: {}, members: [] }; }', loader: "jsx" }));
    builder.onResolve({ filter: /^@livekit\/components-react$/ }, () => ({ path: "livekit-fixture", namespace: "fixture" }));
    builder.onResolve({ filter: /^livekit-client$/ }, () => ({ path: "livekit-client-fixture", namespace: "client-fixture" }));
    builder.onResolve({ filter: /^@tauri-apps\/api\/core$/ }, () => ({ path: "tauri-fixture", namespace: "tauri-fixture" }));
    builder.onLoad({ filter: /.*/, namespace: "tauri-fixture" }, () => ({ loader: "js", contents: 'export const invoke = (...args) => window.__TAURI_INTERNALS__.invoke(...args);' }));
    builder.onLoad({ filter: /.*/, namespace: "client-fixture" }, () => ({ loader: "js", contents: `
      export const Track = { Source: { Camera: "camera", ScreenShare: "screen_share" } };
      export const Room = { getLocalDevices: (...args) => globalThis.voiceFixture.devices(...args) };
      export const createLocalVideoTrack = (...args) => globalThis.voiceFixture.createTrack(...args);
      export const createLocalScreenTracks = (...args) => globalThis.voiceFixture.createScreenTracks(...args);
      export class LocalVideoTrack { constructor(raw) { return globalThis.voiceFixture.wrapNative(raw); } }
    ` }));
    builder.onLoad({ filter: /.*/, namespace: "fixture" }, () => ({ loader: "jsx", resolveDir: fileURLToPath(new URL("../", import.meta.url)), contents: `
      export function LiveKitRoom({ className, children }) { return <section className={className}>{children}</section>; }
      export function RoomAudioRenderer() { return null; }
      export function VideoTrack() { return null; }
      export function useParticipants() { return []; }
      export function useTracks() { return []; }
      import { useSyncExternalStore } from "react";
      export function useLocalParticipant() {
        useSyncExternalStore(globalThis.voiceFixture.subscribe, () => globalThis.voiceFixture.version);
        return { localParticipant: globalThis.voiceFixture.participant, isScreenShareEnabled: globalThis.voiceFixture.participant.isScreenShareEnabled };
      }
    ` }));
  } }],
});
const module = { exports: {} };
new Function("require", "module", "exports", bundle.outputFiles[0].text)(createRequire(import.meta.url), module, module.exports);
const VoicePanel = module.exports.default;
const { act, createElement, createRef } = await import("react");
const { createRoot } = await import("react-dom/client");
let root, calls, tracks, captures, published;
function makeTrack(deviceId = "built-in", source = "camera") {
  const mediaStreamTrack = new dom.window.EventTarget();
  mediaStreamTrack.getSettings = () => ({ deviceId });
  const track = { mediaStreamTrack, deviceId, source, stopped: 0, attached: [], detached: [], attach(element) { this.attached.push(element); }, detach(element) { this.detached.push(element); }, stop() { this.stopped += 1; } };
  tracks.push(track);
  return track;
}
beforeEach(() => {
  calls = []; tracks = []; captures = []; published = null;
  delete window.__TAURI_INTERNALS__;
  Object.defineProperty(navigator, "userAgent", { configurable: true, value: defaultUserAgent });
  Object.defineProperty(navigator, "mediaDevices", { configurable: true, value: new dom.window.EventTarget() });
  const listeners = new Set();
  const notify = () => { globalThis.voiceFixture.version += 1; listeners.forEach((listener) => listener()); };
  globalThis.voiceFixture = {
    env: {},
    version: 0, notify, subscribe: (listener) => { listeners.add(listener); return () => listeners.delete(listener); },
    join: async (...args) => { calls.push(["join", ...args]); return { token: "fixture-token", url: "ws://fixture.invalid" }; },
    leave: async (...args) => { calls.push(["leave", ...args]); },
    createTrack: async (options) => { captures.push(options); return makeTrack(options.deviceId?.exact); },
    createScreenTracks: async (options) => { captures.push(options); return [makeTrack("screen", "screen_share")]; },
    devices: async () => [{ deviceId: "built-in", label: "Built-in camera" }, { deviceId: "usb", label: "USB camera" }, { deviceId: "virtual", label: "Virtual camera" }],
    participant: {
      identity: "self", isMicrophoneEnabled: true, setMicrophoneEnabled: async () => {},
      get isScreenShareEnabled() { return published?.source === "screen_share"; },
      getTrackPublication: (source) => published?.source === source ? { track: published } : undefined,
      publishTrack: async (track, options) => { calls.push(["publish", track, options]); published = track; notify(); },
      unpublishTrack: async (track, stop) => { calls.push(["unpublish", track, stop]); if (stop) track.stop(); published = null; notify(); },
      setScreenShareEnabled: async (enabled) => {
        calls.push(["screen-enabled", enabled]);
        if (enabled) { const [track] = await globalThis.voiceFixture.createScreenTracks({ audio: false }); await globalThis.voiceFixture.participant.publishTrack(track, { source: "screen_share" }); }
        else if (published?.source === "screen_share") { published.stop(); published = null; notify(); }
      },
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

async function openPreview(action, floating = true) {
  const ref = createRef();
  const room = { id: "voice-room", server_id: "server", type: "voice", name: "Lounge" };
  root = createRoot(document.getElementById("root"));
  await act(async () => root.render(createElement(VoicePanel, { ref, activeChannel: floating ? { id: "text-room", type: "text" } : room, onNavigate() {} })));
  await act(async () => ref.current.join(room));
  await act(async () => { const button = document.querySelector(`[aria-label="${action}"]`); button.focus(); button.click(); });
}
async function openCamera(floating = true) { await openPreview("Turn camera on", floating); }
async function openScreen(floating = true) { window.__TAURI_INTERNALS__ ||= {}; await openPreview("Share screen", floating); }
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

test("screen preview opens outside the floating panel and waits for a source and confirmation", async () => {
  await openScreen();
  const dialog = document.querySelector('[role="dialog"]');
  assert.equal(dialog.closest(".floating-voice-room"), null);
  assert.equal(dialog.parentElement.parentElement, document.body);
  assert.equal(captures.length, 0, "Opening the dialog must not open the native picker without a click");
  assert.equal([...dialog.querySelectorAll("button")].find((button) => button.textContent === "Publish screen").disabled, true);
  await press("Choose source");
  assert.deepEqual(captures, [{ audio: false }]);
  assert.equal(published, null, "Capture is private until Publish screen is clicked");
  assert.equal(tracks[0].attached[0], document.querySelector('[aria-label="Screen share preview"]'));
  await press("Cancel");
  assert.equal(tracks[0].stopped, 1);
  assert.equal(document.querySelector('[role="dialog"]'), null);
  assert.ok(document.querySelector(".floating-voice-room"));
});

test("screen preview publishes the exact chosen track and Stop sharing releases it", async () => {
  await openScreen(false); await press("Choose source");
  const selected = tracks[0];
  await press("Publish screen");
  assert.equal(published, selected);
  assert.deepEqual(calls.find(([kind]) => kind === "publish"), ["publish", selected, { source: "screen_share" }]);
  assert.equal(selected.stopped, 0);
  assert.equal(selected.detached.length, 1);
  assert.equal(document.querySelector('[role="dialog"]'), null);
  await act(async () => document.querySelector('[aria-label="Stop screen share"]').click());
  assert.equal(selected.stopped, 1);
  assert.equal(published, null);
  assert.ok(document.querySelector('[aria-label="Share screen"]'));
});

test("changing the screen source releases the old preview, while cancelling the picker keeps it", async () => {
  await openScreen(); await press("Choose source"); await press("Change source");
  assert.equal(tracks[0].stopped, 1);
  const selected = tracks[1];
  globalThis.voiceFixture.createScreenTracks = async () => { throw Object.assign(new Error("Cancelled"), { name: "NotAllowedError" }); };
  await press("Change source");
  assert.equal(selected.stopped, 0);
  assert.match(document.querySelector('[role="alert"]').textContent, /previous source is still selected/);
  await press("Publish screen");
  assert.equal(published, selected);
});

test("screen picker cancellation allows another attempt and never publishes", async () => {
  const capture = globalThis.voiceFixture.createScreenTracks;
  globalThis.voiceFixture.createScreenTracks = async () => { throw Object.assign(new Error("Cancelled"), { name: "AbortError" }); };
  await openScreen(); await press("Choose source");
  assert.match(document.querySelector('[role="alert"]').textContent, /No screen selected/);
  assert.equal([...document.querySelectorAll("button")].find((button) => button.textContent === "Publish screen").disabled, true);
  assert.equal(published, null);
  globalThis.voiceFixture.createScreenTracks = capture;
  await press("Choose source"); await press("Cancel");
  assert.equal(tracks[0].stopped, 1);
});

test("screen publication failure keeps the preview alive for retry", async () => {
  await openScreen(); await press("Choose source");
  const publish = globalThis.voiceFixture.participant.publishTrack;
  globalThis.voiceFixture.participant.publishTrack = async () => { throw new Error("Screen publication failed"); };
  await press("Publish screen");
  assert.equal(document.querySelector('[role="alert"]').textContent, "Screen publication failed");
  assert.equal(tracks[0].stopped, 0);
  globalThis.voiceFixture.participant.publishTrack = publish;
  await press("Publish screen"); assert.equal(published, tracks[0]);
});

test("a late screen picker result after dismissal is stopped without attaching", async () => {
  const request = deferred(); globalThis.voiceFixture.createScreenTracks = () => request.promise;
  await openScreen(); await press("Choose source"); await press("Cancel");
  const track = makeTrack("screen", "screen_share");
  await act(async () => request.resolve([track]));
  assert.equal(track.stopped, 1);
  assert.equal(track.attached.length, 0);
  assert.equal(published, null);
});

test("cancelling an in-flight screen publication removes the late published track", async () => {
  const request = deferred();
  globalThis.voiceFixture.participant.publishTrack = async (track) => { await request.promise; published = track; globalThis.voiceFixture.notify(); };
  await openScreen(); await press("Choose source"); await press("Publish screen"); await press("Cancel");
  assert.equal(tracks[0].stopped, 0);
  await act(async () => request.resolve());
  assert.equal(published, null);
  assert.ok(tracks[0].stopped > 0);
  assert.ok(document.querySelector('[aria-label="Share screen"]'));
});

test("an ended screen preview disables publishing and can choose a new source", async () => {
  await openScreen(); await press("Choose source");
  await act(async () => tracks[0].mediaStreamTrack.dispatchEvent(new dom.window.Event("ended")));
  assert.match(document.querySelector('[role="alert"]').textContent, /screen share ended/);
  assert.equal([...document.querySelectorAll("button")].find((button) => button.textContent === "Publish screen").disabled, true);
  await press("Choose source"); await press("Publish screen");
  assert.equal(published, tracks[1]);
});

test("screen controls follow SDK state when sharing is stopped outside the app", async () => {
  await openScreen(); await press("Choose source"); await press("Publish screen");
  assert.ok(document.querySelector('[aria-label="Stop screen share"]'));
  await act(async () => { published.stop(); published = null; globalThis.voiceFixture.notify(); });
  assert.ok(document.querySelector('[aria-label="Share screen"]'));
});

test("Escape cancels screen preview and restores focus to the floating share control", async () => {
  await openScreen(); await press("Choose source");
  await act(async () => document.querySelector('[aria-label="Close dialog"]').dispatchEvent(new dom.window.KeyboardEvent("keydown", { key: "Escape", bubbles: true })));
  assert.equal(document.querySelector('[role="dialog"]'), null);
  assert.equal(tracks[0].stopped, 1);
  assert.equal(document.activeElement.getAttribute("aria-label"), "Share screen");
});

test("web screen sharing opens the native capture flow and publishes without an app dialog", async () => {
  await openPreview("Share screen");
  assert.equal(document.querySelector('[role="dialog"]'), null);
  assert.deepEqual(calls.find(([kind]) => kind === "screen-enabled"), ["screen-enabled", true]);
  assert.equal(published, tracks[0]);
  assert.ok(document.querySelector('[aria-label="Stop screen share"]'));
  await act(async () => document.querySelector('[aria-label="Stop screen share"]').click());
  assert.equal(tracks[0].stopped, 1);
  assert.equal(published, null);
});

test("cancelling the native web picker leaves sharing off and permits another attempt", async () => {
  const capture = globalThis.voiceFixture.createScreenTracks;
  globalThis.voiceFixture.createScreenTracks = async () => { throw Object.assign(new Error("Cancelled"), { name: "NotAllowedError" }); };
  await openPreview("Share screen", false);
  assert.equal(document.querySelector('[role="dialog"]'), null);
  assert.equal(document.querySelector('[role="alert"]'), null);
  assert.equal(document.querySelector('[aria-label="Share screen"]').disabled, false);
  globalThis.voiceFixture.createScreenTracks = capture;
  await act(async () => document.querySelector('[aria-label="Share screen"]').click());
  assert.equal(published, tracks[0]);
});

test("web capture failure is visible and can be retried", async () => {
  const capture = globalThis.voiceFixture.createScreenTracks;
  globalThis.voiceFixture.createScreenTracks = async () => { throw new Error("Capture unavailable"); };
  await openPreview("Share screen");
  assert.equal(document.querySelector('[role="alert"]').textContent, "Capture unavailable");
  assert.equal(document.querySelector('[aria-label="Share screen"]').disabled, false);
  globalThis.voiceFixture.createScreenTracks = capture;
  await act(async () => document.querySelector('[aria-label="Share screen"]').click());
  assert.equal(document.querySelector('[role="alert"]'), null);
  assert.equal(published, tracks[0]);
});

test("web sharing prevents repeated capture requests while the native picker is pending", async () => {
  const request = deferred(); globalThis.voiceFixture.createScreenTracks = () => request.promise;
  await openPreview("Share screen");
  const button = document.querySelector('[aria-label="Share screen"]');
  assert.equal(button.disabled, true);
  await act(async () => button.click());
  assert.equal(calls.filter(([kind]) => kind === "screen-enabled").length, 1);
  const track = makeTrack("screen", "screen_share");
  await act(async () => request.resolve([track]));
  assert.equal(published, track);
});

test("leaving while the native web picker is pending stops a late screen publication", async () => {
  const request = deferred(); globalThis.voiceFixture.createScreenTracks = () => request.promise;
  await openPreview("Share screen");
  await act(async () => document.querySelector('[title="Disconnect"]').click());
  const track = makeTrack("screen", "screen_share");
  await act(async () => request.resolve([track]));
  assert.equal(published, null);
  assert.equal(track.stopped, 1);
});

function enableNativeCapture() {
  Object.defineProperty(navigator, "userAgent", { configurable: true, value: "Mozilla/5.0 (Windows NT 10.0; Win64; x64)" });
  const nativeCalls = [];
  const raw = new dom.window.EventTarget();
  raw.getSettings = () => ({}); raw.requestFrame = () => {}; raw.stop = () => {};
  Object.defineProperty(globalThis, "ImageData", { configurable: true, value: class {} });
  dom.window.HTMLCanvasElement.prototype.getContext = () => ({ putImageData() {} });
  dom.window.HTMLCanvasElement.prototype.captureStream = () => ({ getVideoTracks: () => [raw], getTracks: () => [raw] });
  voiceFixture.wrapNative = (raw) => { const track = makeTrack("native", "screen_share"); track.mediaStreamTrack = raw; return track; };
  window.__TAURI_INTERNALS__ = { invoke: async (command, args) => {
    nativeCalls.push([command, args]);
    if (command === "native_capture_list_sources") return voiceFixture.nativeSources || [{ id: "window-1", label: "Sample native window", kind: "window" }, { id: "screen-1", label: "Screen 1 · 1920 × 1080", kind: "screen" }];
    if (command === "native_capture_start") return { session_id: `native-session-${nativeCalls.filter(([kind]) => kind === "native_capture_start").length}`, label: args.sourceId === "screen-1" ? "Screen 1" : "Sample native window" };
    if (command === "native_capture_frame") {
      const bytes = new Uint8Array(48), header = new DataView(bytes.buffer);
      header.setUint32(0, 0x50434e53, true); header.setUint32(4, 2, true); header.setUint32(8, 2, true); header.setUint32(12, 1, true);
      return bytes.buffer;
    }
  } };
  return nativeCalls;
}
async function chooseNativeWindow() {
  await act(async () => { const select = document.querySelector('select'); select.value = 'window-1'; select.dispatchEvent(new dom.window.Event('change', { bubbles: true })); });
}
test("the native Windows picker publishes the selected track through the existing room", async () => {
  const nativeCalls = enableNativeCapture();
  await openScreen();
  assert.ok(document.querySelector('option[value="window-1"]'));
  assert.equal(document.querySelector('.screen-preview-source-row'), null, "The source dropdown replaces the extra choose-source step");
  assert.equal(nativeCalls.some(([kind]) => kind === "native_capture_start"), false);
  await chooseNativeWindow();
  assert.equal(document.querySelector('.media-preview-footer .primary-button').disabled, false);
  assert.equal(published, null, "Selecting previews without publishing");
  assert.equal(captures.length, 0, "The Windows source picker must never open getDisplayMedia");
  assert.deepEqual(nativeCalls.find(([kind]) => kind === "native_capture_start"), ["native_capture_start", { sourceId: "window-1" }]);
  await press("Publish screen");
  assert.equal(published, tracks[0]); assert.equal(tracks[0].stopped, 0);
  assert.equal(nativeCalls.some(([kind]) => kind === "native_capture_stop"), false);
  await act(async () => document.querySelector('[aria-label="Stop screen share"]').click());
  assert.ok(nativeCalls.some(([kind]) => kind === "native_capture_stop"));
});
test("cancelling the native Windows preview releases its capture session", async () => {
  const nativeCalls = enableNativeCapture();
  await openScreen(); await chooseNativeWindow(); await press("Cancel");
  assert.equal(published, null);
  assert.equal(tracks[0].stopped, 1);
  assert.ok(nativeCalls.some(([kind]) => kind === "native_capture_stop"));
});

test("the native picker offers full monitors and publishes the chosen screen through the same room", async () => {
  const nativeCalls = enableNativeCapture(); await openScreen();
  assert.ok(document.querySelector('optgroup[label="Entire screens"] option[value="screen-1"]'));
  await act(async () => { const select = document.querySelector('select'); select.value = 'screen-1'; select.dispatchEvent(new dom.window.Event('change', { bubbles: true })); });
  await press("Publish screen");
  assert.deepEqual(nativeCalls.find(([kind]) => kind === "native_capture_start"), ["native_capture_start", { sourceId: "screen-1" }]);
  assert.equal(published, tracks[0]);
  await act(async () => document.querySelector('[aria-label="Stop screen share"]').click());
});

test("refreshing removes a closed native source and prevents selecting its stale ID", async () => {
  enableNativeCapture(); await openScreen();
  await act(async () => { const select = document.querySelector('select'); select.value = 'window-1'; select.dispatchEvent(new dom.window.Event('change', { bubbles: true })); });
  voiceFixture.nativeSources = [{ id: "screen-1", label: "Screen 1", kind: "screen" }];
  await press("Refresh sources");
  assert.equal(document.querySelector('option[value="window-1"]'), null);
  assert.equal(document.querySelector('select').value, "");
  assert.equal(document.querySelector('.media-preview-footer .primary-button').disabled, true);
});

test("selecting another native source replaces its preview and waits for a frame before publication", async () => {
  const nativeCalls = enableNativeCapture(); await openScreen(); await chooseNativeWindow();
  const previous = tracks[0], frame = deferred();
  const invoke = window.__TAURI_INTERNALS__.invoke;
  window.__TAURI_INTERNALS__.invoke = (command, args) => command === "native_capture_frame" && args.sessionId === "native-session-2" ? frame.promise : invoke(command, args);
  await selectCamera("screen-1");
  assert.equal(previous.stopped, 1);
  assert.deepEqual(nativeCalls.find(([kind]) => kind === "native_capture_stop"), ["native_capture_stop", { sessionId: "native-session-1" }]);
  assert.equal(document.querySelector('.media-preview-footer .primary-button').disabled, true);
  assert.match(document.querySelector('.media-preview-status').textContent, /Starting preview/);
  await press("Publish screen"); assert.equal(published, null);
  await act(async () => frame.resolve(await invoke("native_capture_frame", { sessionId: "native-session-2" })));
  assert.equal(document.querySelector('.media-preview-footer .primary-button').disabled, false);
  await press("Publish screen"); assert.equal(published, tracks[1]);
  assert.deepEqual(nativeCalls.filter(([kind]) => kind === "native_capture_start").map(([, args]) => args.sourceId), ["window-1", "screen-1"]);
  await act(async () => document.querySelector('[aria-label="Stop screen share"]').click());
});

test("a failed automatic source change disables the old preview and can retry the selected source", async () => {
  enableNativeCapture(); await openScreen(); await chooseNativeWindow();
  const invoke = window.__TAURI_INTERNALS__.invoke;
  window.__TAURI_INTERNALS__.invoke = (command, args) => command === "native_capture_start" && args.sourceId === "screen-1" ? Promise.reject(new Error("Screen unavailable")) : invoke(command, args);
  await selectCamera("screen-1");
  assert.equal(tracks[0].stopped, 1);
  assert.equal(document.querySelector('select').value, "screen-1");
  assert.match(document.querySelector('[role="alert"]').textContent, /Screen unavailable/);
  await press("Publish screen"); assert.equal(published, null);
  window.__TAURI_INTERNALS__.invoke = invoke;
  await press("Retry preview"); await press("Publish screen");
  assert.equal(published, tracks[1]);
  await act(async () => document.querySelector('[aria-label="Stop screen share"]').click());
});

test("clearing the native source selection releases the preview and disables publication", async () => {
  const nativeCalls = enableNativeCapture(); await openScreen(); await chooseNativeWindow();
  await selectCamera("");
  assert.equal(tracks[0].stopped, 1);
  assert.ok(nativeCalls.some(([kind]) => kind === "native_capture_stop"));
  assert.equal(document.querySelector('.media-preview-footer .primary-button').disabled, true);
  await press("Publish screen"); assert.equal(published, null);
});

test("cancelling while selection starts native capture releases the late session without publishing", async () => {
  const nativeCalls = enableNativeCapture(), starting = deferred();
  const invoke = window.__TAURI_INTERNALS__.invoke;
  window.__TAURI_INTERNALS__.invoke = (command, args) => command === "native_capture_start" ? starting.promise : invoke(command, args);
  await openScreen(); await chooseNativeWindow();
  assert.equal(document.querySelector('.media-preview-footer .primary-button').disabled, true);
  await press("Cancel");
  await act(async () => starting.resolve({ session_id: "late-session", label: "Sample window" }));
  assert.equal(document.querySelector('[role="dialog"]'), null);
  assert.equal(tracks.length, 0); assert.equal(published, null);
  assert.deepEqual(nativeCalls.find(([kind]) => kind === "native_capture_stop"), ["native_capture_stop", { sessionId: "late-session" }]);
});
