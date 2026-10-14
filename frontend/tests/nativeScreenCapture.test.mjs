import assert from "node:assert/strict";
import { after, afterEach, beforeEach, test } from "node:test";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { build } from "esbuild";
import { JSDOM } from "jsdom";

const dom = new JSDOM("", { url: "http://localhost:5173/" });
Object.defineProperty(globalThis, "window", { configurable: true, value: dom.window });
Object.defineProperty(globalThis, "document", { configurable: true, value: dom.window.document });
Object.defineProperty(globalThis, "Event", { configurable: true, value: dom.window.Event });
Object.defineProperty(globalThis, "ImageData", { configurable: true, value: class { constructor(pixels, width, height) { Object.assign(this, { pixels, width, height }); } } });
const bundle = await build({ entryPoints: [fileURLToPath(new URL("../src/utils/nativeScreenCapture.js", import.meta.url))], bundle: true, write: false, format: "cjs", platform: "node", packages: "external", plugins: [{ name: "native-sdk-fixture", setup(builder) {
  builder.onResolve({ filter: /^livekit-client$/ }, () => ({ path: "client", namespace: "fixture" }));
  builder.onLoad({ filter: /.*/, namespace: "fixture" }, () => ({ contents: 'export const Track = { Source: { ScreenShare: "screen_share" } }; export class LocalVideoTrack { constructor(raw) { this.mediaStreamTrack = raw; } stop() { this.mediaStreamTrack.stop(); } }' }));
} }] });
const module = { exports: {} };
new Function("require", "module", "exports", bundle.outputFiles[0].text)(createRequire(import.meta.url), module, module.exports);
const { decodeNativeFrame, createNativeScreenTrack, isNativeScreenCaptureSupported } = module.exports;
let calls, raw, controller;
function packet() {
  const bytes = new Uint8Array(32 + 2 * 2 * 4), header = new DataView(bytes.buffer);
  header.setUint32(0, 0x50434e53, true); header.setUint32(4, 2, true); header.setUint32(8, 2, true); header.setUint32(12, 1, true); header.setFloat64(16, 3.5, true);
  bytes.set([1,2,3,255,4,5,6,255,7,8,9,255,10,11,12,255],32);
  return bytes.buffer;
}
beforeEach(() => {
  calls = []; controller = null; window.__TAURI_INTERNALS__ = {};
  Object.defineProperty(window.navigator, "userAgent", { configurable: true, value: "Mozilla/5.0 (Windows NT 10.0; Win64; x64)" });
  raw = new dom.window.EventTarget(); raw.stopped = 0; raw.requested = 0; raw.stop = () => { raw.stopped += 1; }; raw.requestFrame = () => { raw.requested += 1; };
  dom.window.HTMLCanvasElement.prototype.getContext = () => ({ putImageData: (data) => calls.push(["paint", data.width, data.height]) });
  dom.window.HTMLCanvasElement.prototype.captureStream = () => ({ getVideoTracks: () => [raw], getTracks: () => [raw] });
});
afterEach(() => { controller?.abort(); });
after(() => dom.window.close());
function fixtureInvoke() {
  let sent = false;
  return async (command, args) => {
    calls.push([command, args]);
    if (command === "native_capture_start") return { session_id: "sample", label: "Sample window" };
    if (command === "native_capture_frame") { if (sent) return new ArrayBuffer(0); sent = true; return packet(); }
  };
}
test("native screen capture is available in Windows desktop builds, with browser and other-desktop fallbacks", () => {
  assert.equal(isNativeScreenCaptureSupported(), true);
  delete window.__TAURI_INTERNALS__; assert.equal(isNativeScreenCaptureSupported(), false);
  window.__TAURI_INTERNALS__ = {};
  Object.defineProperty(window.navigator, "userAgent", { configurable: true, value: "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)" });
  assert.equal(isNativeScreenCaptureSupported(), false);
  Object.defineProperty(window.navigator, "userAgent", { configurable: true, value: "Mozilla/5.0 (X11; Linux x86_64)" });
  assert.equal(isNativeScreenCaptureSupported(), false);
});
test("binary native packets decode without changing RGBA color order", () => {
  const frame = decodeNativeFrame(packet());
  assert.equal(frame.nativeMs, 3.5); assert.equal(frame.sequence, 1);
  assert.deepEqual([...frame.pixels], [1,2,3,255,4,5,6,255,7,8,9,255,10,11,12,255]);
  assert.equal(decodeNativeFrame(new ArrayBuffer(0)), null);
  const aligned = new Uint8Array(8 + packet().byteLength); aligned.set(new Uint8Array(packet()), 8);
  assert.equal(decodeNativeFrame(aligned.subarray(8)).width, 2);
});
test("malformed and oversized frames are rejected before allocating image data", () => {
  assert.throws(() => decodeNativeFrame(new Uint8Array(3)), /Incomplete/);
  const bytes = packet(); new DataView(bytes).setUint32(4, 50000, true);
  assert.throws(() => decodeNativeFrame(bytes), /Invalid/);
  assert.throws(() => decodeNativeFrame(new Uint8Array(32)), /Unknown/);
});
test("native frames become a LiveKit screen track and stopping releases native capture once", async () => {
  const invoke = fixtureInvoke(); controller = new AbortController();
  const track = await createNativeScreenTrack("window-1", { invoke, signal: controller.signal });
  assert.equal(track.source, "screen_share"); assert.equal(track.nativeCaptureLabel, "Sample window");
  assert.equal(track.mediaStreamTrack, raw); assert.equal(raw.requested, 1);
  assert.ok(calls.some(([kind]) => kind === "paint"));
  track.stop(); track.stop(); controller.abort();
  assert.equal(raw.stopped, 1);
  assert.equal(calls.filter(([kind]) => kind === "native_capture_stop").length, 1);
});
test("closing the selected window ends the screen track and its native session", async () => {
  let count = 0; const invokeBase = fixtureInvoke();
  const invoke = (command, args) => command === "native_capture_frame" && count++ > 0 ? Promise.reject(new Error("Window closed")) : invokeBase(command, args);
  controller = new AbortController();
  const track = await createNativeScreenTrack("window-1", { invoke, signal: controller.signal });
  await new Promise((resolve) => raw.addEventListener("ended", resolve, { once: true }));
  assert.equal(raw.stopped, 1);
  assert.ok(calls.some(([kind]) => kind === "native_capture_stop"));
  track.stop(); assert.equal(raw.stopped, 1);
});
test("cancelling before the first frame stops capture even while a frame request is pending", async () => {
  let resolveFrame; const invokeBase = fixtureInvoke();
  const invoke = (command, args) => command === "native_capture_frame" ? new Promise((resolve) => { resolveFrame = resolve; }) : invokeBase(command, args);
  controller = new AbortController();
  const result = createNativeScreenTrack("window-1", { invoke, signal: controller.signal });
  await new Promise((resolve) => setTimeout(resolve, 0)); controller.abort();
  await assert.rejects(result, /stopped/);
  resolveFrame(packet()); await new Promise((resolve) => setTimeout(resolve, 0));
  assert.equal(raw.stopped, 1); assert.equal(raw.requested, 0);
});
test("cancelling while native start is pending releases the late native session", async () => {
  let resolveStart; const invokeBase = fixtureInvoke();
  const invoke = (command, args) => command === "native_capture_start" ? new Promise((resolve) => { resolveStart = resolve; }) : invokeBase(command, args);
  controller = new AbortController();
  const result = createNativeScreenTrack("window-1", { invoke, signal: controller.signal }); controller.abort();
  resolveStart({ session_id: "sample", label: "Sample window" });
  await assert.rejects(result, /cancelled/);
  assert.ok(calls.some(([kind]) => kind === "native_capture_stop")); assert.equal(raw.requested, 0);
});
