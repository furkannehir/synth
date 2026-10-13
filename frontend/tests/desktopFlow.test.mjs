import assert from "node:assert/strict";
import { after, afterEach, beforeEach, test } from "node:test";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { build } from "esbuild";
import { JSDOM } from "jsdom";

const dom = new JSDOM("<div id='root'></div>", { url: "http://tauri.localhost/" });
for (const [key, value] of Object.entries({
  window: dom.window, document: dom.window.document, navigator: dom.window.navigator,
  localStorage: dom.window.localStorage, sessionStorage: dom.window.sessionStorage,
  Event: dom.window.Event, IS_REACT_ACT_ENVIRONMENT: true,
})) Object.defineProperty(globalThis, key, { configurable: true, value });
const { act, createElement } = await import("react");
const { createRoot } = await import("react-dom/client");
const sid = "a".repeat(32);
const session = { refresh_token: `${sid}.${"r".repeat(43)}`, revocation_token: `${sid}.${"v".repeat(43)}`, next_refresh_token: null };
const frontendRoot = fileURLToPath(new URL("../", import.meta.url));
const bundle = await build({
  stdin: { contents: 'export { default as App } from "./src/App.jsx"; export { desktopSession, servers } from "./src/api/client.js";', resolveDir: frontendRoot },
  bundle: true, write: false, format: "cjs", platform: "node", packages: "external", jsx: "automatic",
  define: { "import.meta.env": "{}" },
  plugins: [{ name: "desktop-fixtures", setup(builder) {
    builder.onLoad({ filter: /[\\/]pages[\\/]HomePage\.jsx$/ }, () => ({
      contents: 'import MessageContent from "../components/MessageContent.jsx"; export default function HomePage() { return <><p>HOME SCREEN</p><p><MessageContent content={globalThis.__testMessage || ""} /></p></>; }',
      loader: "jsx", resolveDir: fileURLToPath(new URL("../src/pages", import.meta.url)),
    }));
    builder.onLoad({ filter: /[\\/]hooks[\\/]usePresence\.js$/ }, () => ({ contents: "export function usePresence() {}", loader: "js" }));
  } }],
});
let root, App, desktopSession, servers, saved, requests, nativeCalls, currentLinks, callbacks, deepLinkHandler, failRefresh, openerFails, protectedFailure, storageWriteFails;
const originalFetch = globalThis.fetch;
const reply = (data, status = 200) => ({ ok: status < 400, status, json: async () => data });

beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
  saved = { session: null, pending_revocations: [] };
  requests = [];
  nativeCalls = [];
  currentLinks = [];
  callbacks = new Map();
  deepLinkHandler = null;
  failRefresh = false;
  openerFails = false;
  protectedFailure = null;
  storageWriteFails = false;
  globalThis.__testMessage = "";
  window.__TAURI_EVENT_PLUGIN_INTERNALS__ = { unregisterListener() {} };
  window.__TAURI_INTERNALS__ = {
    transformCallback(callback) { const id = callbacks.size + 1; callbacks.set(id, callback); return id; },
    unregisterCallback(id) { callbacks.delete(id); },
    async invoke(command, args) {
      nativeCalls.push({ command, args });
      if (command === "read_desktop_session") return structuredClone(saved);
      if (command === "write_desktop_session") {
        if (storageWriteFails) throw "Unlock your keychain and retry.";
        saved = structuredClone(args.credentials); return;
      }
      if (command === "plugin:event|listen") { deepLinkHandler = callbacks.get(args.handler); return 1; }
      if (command === "plugin:event|unlisten") return;
      if (command === "plugin:deep-link|get_current") return currentLinks;
      if (command === "plugin:opener|open_url") { if (openerFails) throw new Error("blocked"); return; }
      throw new Error(`Unexpected native command ${command}`);
    },
  };
  globalThis.fetch = async (url, options = {}) => {
    requests.push({ url, options });
    if (url === "/api/auth/refresh") {
      if (failRefresh) throw new Error("Connection unavailable");
      const body = JSON.parse(options.body);
      return reply({ access_token: "renewed-token", refresh_token: body.next_refresh_token, expires_in: 900 });
    }
    if (url === "/api/auth/login") return reply({ access_token: "logged-in-token", ...session, expires_in: 900 });
    if (url === "/api/auth/logout") return reply({});
    if (url === "/api/auth/me") return reply({ user: { id: "user-1", username: "tester" } });
    if (url === "/api/servers") {
      if (protectedFailure) { const code = protectedFailure; protectedFailure = null; return reply({ error: "unauthorized", code }, 401); }
      return reply({ servers: [] });
    }
    if (url.startsWith("/api/invites/")) return reply({ invite: { server_name: "Example Server", member_count: 3 } });
    throw new Error(`Unexpected API request ${url}`);
  };
  const module = { exports: {} };
  new Function("require", "module", "exports", bundle.outputFiles[0].text)(createRequire(import.meta.url), module, module.exports);
  ({ App, desktopSession, servers } = module.exports);
});
afterEach(async () => {
  if (root) await act(async () => root.unmount());
  root = null;
  storageWriteFails = false;
  await desktopSession.logout();
  globalThis.fetch = originalFetch;
  delete window.__TAURI_INTERNALS__;
});
after(() => dom.window.close());

async function mount(path = "/") {
  window.history.replaceState(null, "", path);
  root = createRoot(document.getElementById("root"));
  await act(async () => {
    root.render(createElement(App));
    await new Promise((resolve) => setTimeout(resolve, 10));
  });
  // Native bindings are lazy-loaded and their initial event subscription can
  // complete on a subsequent Node task, as it does in the desktop WebView.
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 10)); });
}
async function click(text) {
  const element = [...document.querySelectorAll("a, button")].find((el) => el.textContent.trim() === text);
  assert.ok(element, `Missing action ${text}`);
  await act(async () => element.click());
}

test("cold-start invite renews the saved app login without browser credentials", async () => {
  saved.session = { ...session };
  currentLinks = ["synthapp://invite/cold-code"];
  await mount();
  assert.equal(window.location.pathname, "/invite/cold-code");
  assert.match(document.body.textContent, /Accept Invite/);
  assert.equal(document.querySelector("form"), null);
  assert.equal(requests.some(({ url }) => url === "/api/auth/login"), false);
  assert.equal(localStorage.getItem("synth_token"), null);
  assert.notEqual(saved.session.refresh_token, session.refresh_token);
});

test("signed-out deep link returns to its invite after desktop login", async () => {
  currentLinks = ["synthapp://invite/cold-code"];
  await mount();
  assert.equal(window.location.pathname, "/login");
  assert.equal(new URLSearchParams(window.location.search).get("redirect"), "/invite/cold-code");
  await act(async () => {
    for (const input of document.querySelectorAll("input")) {
      Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set.call(input, input.type === "email" ? "test@example.com" : "test-password");
      input.dispatchEvent(new window.Event("input", { bubbles: true }));
    }
  });
  await act(async () => document.querySelector("form").dispatchEvent(new window.Event("submit", { bubbles: true, cancelable: true })));
  assert.equal(window.location.pathname, "/invite/cold-code");
  assert.match(document.body.textContent, /Accept Invite/);
  const login = requests.find(({ url }) => url === "/api/auth/login");
  assert.equal(JSON.parse(login.options.body).persistent, true);
  assert.equal(localStorage.getItem("synth_token"), null);
  assert.ok(saved.session);
});

test("warm deep links navigate the open app and malformed links are ignored", async () => {
  saved.session = { ...session };
  await mount();
  await act(async () => deepLinkHandler({ payload: ["synthapp://invite/warm-code"] }));
  assert.equal(window.location.pathname, "/invite/warm-code");
  await act(async () => deepLinkHandler({ payload: ["synthapp://login/evil", "synthapp://invite/warm-code?token=secret"] }));
  assert.equal(window.location.pathname, "/invite/warm-code");
});

test("a warm invite beats a delayed startup URL and is not reopened after leaving", async () => {
  saved.session = { ...session };
  let finishStartup;
  currentLinks = new Promise((resolve) => { finishStartup = resolve; });
  await mount();
  await act(async () => deepLinkHandler({ payload: ["synthapp://invite/newer-code"] }));
  await act(async () => finishStartup(["synthapp://invite/older-code"]));
  assert.equal(window.location.pathname, "/invite/newer-code");
  await click("No thanks");
  assert.equal(window.location.pathname, "/");
  assert.equal(nativeCalls.filter(({ command }) => command === "plugin:event|listen").length, 1);
});

test("startup outage retains the saved session and invite until retry succeeds", async () => {
  saved.session = { ...session };
  currentLinks = ["synthapp://invite/retry-code"];
  failRefresh = true;
  await mount();
  assert.match(document.body.textContent, /Reconnect to Synth/);
  assert.equal(document.querySelector("form"), null);
  assert.ok(saved.session.next_refresh_token);
  const firstPair = JSON.parse(requests.find(({ url }) => url === "/api/auth/refresh").options.body);
  failRefresh = false;
  await click("Retry");
  assert.equal(window.location.pathname, "/invite/retry-code");
  const lastPair = JSON.parse(requests.filter(({ url }) => url === "/api/auth/refresh").at(-1).options.body);
  assert.deepEqual(lastPair, firstPair);
});

test("message URLs open the native browser and invite URLs stay in Synth", async () => {
  saved.session = { ...session };
  globalThis.__testMessage = "External https://example.com/test and https://synthapp.io/invite/internal-code";
  await mount();
  await click("https://example.com/test");
  const opened = nativeCalls.find(({ command }) => command === "plugin:opener|open_url");
  assert.equal(opened.args.url, "https://example.com/test");
  assert.equal(window.location.pathname, "/");
  await click("https://synthapp.io/invite/internal-code");
  assert.equal(window.location.pathname, "/invite/internal-code");
});

test("failed native URL opening shows a usable error without navigating the app", async () => {
  saved.session = { ...session };
  globalThis.__testMessage = "https://example.com/test";
  openerFails = true;
  await mount();
  await click("https://example.com/test");
  assert.match(document.querySelector('[role="alert"]').textContent, /Copy it/);
  assert.equal(window.location.pathname, "/");
});

test("expired API access renews once and retries the request without logging out", async () => {
  saved.session = { ...session };
  await mount();
  const earlierRefreshCount = requests.filter(({ url }) => url === "/api/auth/refresh").length;
  protectedFailure = "token_expired";
  await act(async () => assert.deepEqual(await servers.list(), { servers: [] }));
  assert.equal(requests.filter(({ url }) => url === "/api/servers").length, 2);
  assert.equal(requests.filter(({ url }) => url === "/api/auth/refresh").length, earlierRefreshCount + 1);
  assert.match(document.body.textContent, /HOME SCREEN/);
  assert.ok(saved.session);
});

test("a revoked session returns to login and clears native credentials without renewal", async () => {
  saved.session = { ...session };
  await mount();
  const earlierRefreshCount = requests.filter(({ url }) => url === "/api/auth/refresh").length;
  protectedFailure = "session_revoked";
  await act(async () => assert.rejects(servers.list(), /unauthorized/));
  assert.equal(requests.filter(({ url }) => url === "/api/auth/refresh").length, earlierRefreshCount);
  assert.equal(window.location.pathname, "/login");
  assert.equal(saved.session, null);
});

test("native secure-storage errors remain visible on the desktop login form", async () => {
  await mount("/login");
  storageWriteFails = true;
  await act(async () => document.querySelector("form").dispatchEvent(new window.Event("submit", { bubbles: true, cancelable: true })));
  assert.match(document.body.textContent, /Unlock your keychain and retry/);
  assert.equal(window.location.pathname, "/login");
  assert.equal(saved.session, null);
});

test("message HTML remains escaped text in the actual renderer", async () => {
  saved.session = { ...session };
  globalThis.__testMessage = '<img src=x onerror="alert(1)"> https://example.com/';
  await mount();
  assert.equal(document.querySelector("img"), null);
  assert.match(document.body.textContent, /<img src=x/);
  const link = [...document.querySelectorAll("a")].find((anchor) => anchor.textContent === "https://example.com/");
  assert.equal(link.target, "_blank");
  assert.equal(link.rel, "noopener noreferrer");
});
