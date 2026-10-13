import assert from "node:assert/strict";
import { after, afterEach, beforeEach, test } from "node:test";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { build } from "esbuild";
import { JSDOM } from "jsdom";

const dom = new JSDOM("<div id='root'></div>", { url: "https://synthapp.io/" });
for (const [key, value] of Object.entries({ window: dom.window, document: dom.window.document, navigator: dom.window.navigator, localStorage: dom.window.localStorage, IS_REACT_ACT_ENVIRONMENT: true })) Object.defineProperty(globalThis, key, { configurable: true, value });
const bundle = await build({ entryPoints: [fileURLToPath(new URL("../src/context/ThemeContext.jsx", import.meta.url))], bundle: true, write: false, format: "cjs", platform: "node", packages: "external", jsx: "automatic" });
const module = { exports: {} };
new Function("require", "module", "exports", bundle.outputFiles[0].text)(createRequire(import.meta.url), module, module.exports);
const { ThemeProvider, useTheme } = module.exports;
const { act, createElement } = await import("react");
const { createRoot } = await import("react-dom/client");
let root;
function Choices() { const { theme, setTheme, availableThemes } = useTheme(); return createElement("div", { "data-theme": theme }, availableThemes.map((option) => createElement("button", { key: option.id, onClick: () => setTheme(option.id) }, option.name))); }
async function mount() { root = createRoot(document.getElementById("root")); await act(async () => root.render(createElement(ThemeProvider, null, createElement(Choices)))); }
async function select(name) { await act(async () => [...document.querySelectorAll("button")].find((button) => button.textContent === name).click()); }
beforeEach(() => { Object.defineProperty(globalThis, "localStorage", { configurable: true, value: dom.window.localStorage }); localStorage.clear(); document.body.className = ""; });
afterEach(async () => { if (root) await act(async () => root.unmount()); root = null; });
after(() => dom.window.close());

test("the picker exposes the three selected appearances", async () => {
  await mount();
  assert.deepEqual([...document.querySelectorAll("button")].map((button) => button.textContent), ["Dusk", "Daylight", "Midnight"]);
  assert.ok(document.body.classList.contains("theme-dusk"));
});

test("saved legacy preferences migrate to the matching light or dark appearance", async () => {
  localStorage.setItem("synth-theme", "theme-light-mode"); document.body.classList.add("theme-light-mode", "theme-vaporwave", "unrelated-class");
  await mount();
  assert.ok(document.body.classList.contains("theme-daylight"));
  assert.equal(document.body.classList.contains("theme-light-mode"), false);
  assert.equal(document.body.classList.contains("theme-vaporwave"), false);
  assert.ok(document.body.classList.contains("unrelated-class"));
  assert.equal(localStorage.getItem("synth-theme"), "theme-daylight");
});

test("theme changes replace the previous appearance immediately and survive remount", async () => {
  await mount(); await select("Midnight");
  assert.ok(document.body.classList.contains("theme-midnight"));
  assert.equal(document.body.classList.contains("theme-dusk"), false);
  assert.equal(document.documentElement.style.colorScheme, "dark");
  await act(async () => root.unmount()); root = null; await mount();
  assert.equal(document.querySelector("[data-theme]").dataset.theme, "theme-midnight");
  await select("Daylight"); assert.equal(document.documentElement.style.colorScheme, "light");
});

test("unknown and prototype-like saved values fall back safely", async () => {
  localStorage.setItem("synth-theme", "__proto__"); await mount();
  assert.ok(document.body.classList.contains("theme-dusk"));
  assert.equal(localStorage.getItem("synth-theme"), "theme-dusk");
});

test("unavailable storage does not block appearance changes", async () => {
  Object.defineProperty(globalThis, "localStorage", { configurable: true, value: { getItem() { throw new Error("Blocked"); }, setItem() { throw new Error("Blocked"); } } });
  await mount(); await select("Daylight");
  assert.ok(document.body.classList.contains("theme-daylight"));
});
