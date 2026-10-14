import assert from "node:assert/strict";
import { after, afterEach, beforeEach, test } from "node:test";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { build } from "esbuild";
import { JSDOM } from "jsdom";

const dom = new JSDOM("<div id='root'></div>", { url: "http://localhost:5173/" });
for (const [key, value] of Object.entries({ window: dom.window, document: dom.window.document, IS_REACT_ACT_ENVIRONMENT: true })) Object.defineProperty(globalThis, key, { configurable: true, value });
const bundle = await build({ stdin: { contents: 'export * from "./src/utils/mediaFullscreen.js"; export { default as FullscreenVideo } from "./src/components/FullscreenVideo.jsx"; export { default as Modal } from "./src/components/Modal.jsx";', resolveDir: fileURLToPath(new URL("../",import.meta.url)) }, bundle:true,write:false,format:"cjs",platform:"node",packages:"external",jsx:"automatic",define:{"import.meta.env":"{}"},plugins:[{name:"window-fixture",setup(builder){
  builder.onResolve({filter:/^@tauri-apps\/api\/window$/},()=>({path:"window",namespace:"fixture"}));
  builder.onLoad({filter:/.*/,namespace:"fixture"},()=>({contents:'export const getCurrentWindow = () => globalThis.fullscreenFixture.window;'}));
}}] });
const module = {exports:{}};
new Function("require","module","exports",bundle.outputFiles[0].text)(createRequire(import.meta.url),module,module.exports);
const { toggleMediaFullscreen, exitMediaFullscreen, FullscreenVideo, Modal } = module.exports;
const { act, createElement } = await import("react");
const { createRoot } = await import("react-dom/client");
let fullscreen, nativeFullscreen, calls, root;
Object.defineProperty(document,"fullscreenElement",{configurable:true,get:()=>fullscreen});
dom.window.HTMLElement.prototype.requestFullscreen = async function(){fullscreen=this;document.dispatchEvent(new dom.window.Event("fullscreenchange"));};
document.exitFullscreen = async () => {fullscreen=null;document.dispatchEvent(new dom.window.Event("fullscreenchange"));};
beforeEach(()=>{
  fullscreen=null;nativeFullscreen=false;calls=[];delete window.__TAURI_INTERNALS__;
  globalThis.fullscreenFixture={window:{isFullscreen:async()=>nativeFullscreen,setFullscreen:async(value)=>{calls.push(value);nativeFullscreen=value;}}};
});
afterEach(async()=>{if(root)await act(async()=>root.unmount());root=null;await exitMediaFullscreen(fullscreen);delete globalThis.fullscreenFixture;});
after(()=>dom.window.close());

test("browser video expands the chosen element and exits without native window commands",async()=>{
  const video=document.createElement("div");await toggleMediaFullscreen(video);
  assert.equal(document.fullscreenElement,video);
  await exitMediaFullscreen(video);assert.equal(document.fullscreenElement,null);assert.deepEqual(calls,[]);
});
test("desktop video fullscreen promotes the window and restores it after exit",async()=>{
  window.__TAURI_INTERNALS__={};const video=document.createElement("div");
  await toggleMediaFullscreen(video);assert.equal(nativeFullscreen,true);
  await exitMediaFullscreen(video);assert.equal(nativeFullscreen,false);assert.deepEqual(calls,[true,false]);
});
test("leaving video fullscreen preserves a desktop window that was already fullscreen",async()=>{
  window.__TAURI_INTERNALS__={};nativeFullscreen=true;
  const video=document.createElement("div");await toggleMediaFullscreen(video);await exitMediaFullscreen(video);
  assert.equal(nativeFullscreen,true);
});
test("exiting while a native window query is pending cannot leave the window fullscreen",async()=>{
  window.__TAURI_INTERNALS__={};let resolve;
  fullscreenFixture.window.isFullscreen=()=>new Promise((yes)=>{resolve=yes;});
  const video=document.createElement("div");const opening=toggleMediaFullscreen(video);
  await new Promise((yes)=>setTimeout(yes,0));const exiting=exitMediaFullscreen(video);resolve(false);
  await Promise.all([opening,exiting]);assert.equal(nativeFullscreen,false);assert.equal(document.fullscreenElement,null);
});
test("a denied desktop fullscreen request exits the DOM fullscreen view",async()=>{
  window.__TAURI_INTERNALS__={};fullscreenFixture.window.setFullscreen=async(value)=>{if(value)throw new Error("Fullscreen unavailable");nativeFullscreen=false;};
  const video=document.createElement("div");await assert.rejects(toggleMediaFullscreen(video),/unavailable/);
  assert.equal(document.fullscreenElement,null);
});
test("Escape exits fullscreen inside the publish dialog and a second Escape closes the dialog",async()=>{
  let closed=0;root=createRoot(document.getElementById("root"));
  await act(async()=>root.render(createElement(Modal,{title:"Preview",id:"preview-title",onClose:()=>{closed++;}},createElement(FullscreenVideo,{label:"preview"},createElement("video")))));
  await act(async()=>document.querySelector('[aria-label="Expand preview to fullscreen"]').click());
  assert.ok(document.fullscreenElement);
  await act(async()=>document.querySelector('[aria-label="Exit fullscreen"]').dispatchEvent(new dom.window.KeyboardEvent("keydown",{key:"Escape",bubbles:true})));
  assert.equal(document.fullscreenElement,null);assert.equal(closed,0);
  await act(async()=>document.querySelector('[aria-label="Expand preview to fullscreen"]').dispatchEvent(new dom.window.KeyboardEvent("keydown",{key:"Escape",bubbles:true})));
  assert.equal(closed,1);
});
test("removing a fullscreen video restores the desktop window",async()=>{
  window.__TAURI_INTERNALS__={};root=createRoot(document.getElementById("root"));
  await act(async()=>root.render(createElement(FullscreenVideo,{label:"video"},createElement("video"))));
  await act(async()=>document.querySelector('[aria-label="Expand video to fullscreen"]').click());
  assert.equal(nativeFullscreen,true);
  await act(async()=>root.unmount());root=null;await exitMediaFullscreen(null);
  assert.equal(nativeFullscreen,false);
});
test("Escape exits a fullscreen video when focus remains outside the video",async()=>{
  root=createRoot(document.getElementById("root"));
  await act(async()=>root.render(createElement(FullscreenVideo,{label:"video"},createElement("video"))));
  await act(async()=>document.querySelector('[aria-label="Expand video to fullscreen"]').click());
  assert.ok(document.fullscreenElement);
  await act(async()=>document.body.dispatchEvent(new dom.window.KeyboardEvent("keydown",{key:"Escape",bubbles:true})));
  assert.equal(document.fullscreenElement,null);
});
test("desktop window state is recorded before the host reacts to DOM fullscreen",async()=>{
  window.__TAURI_INTERNALS__={};const video=document.createElement("div");
  video.requestFullscreen=async()=>{nativeFullscreen=true;fullscreen=video;document.dispatchEvent(new dom.window.Event("fullscreenchange"));};
  await toggleMediaFullscreen(video);
  await exitMediaFullscreen(video);
  assert.equal(nativeFullscreen,false);
});
