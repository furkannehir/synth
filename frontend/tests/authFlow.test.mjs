import assert from "node:assert/strict";
import { after, afterEach, beforeEach, test } from "node:test";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { build } from "esbuild";
import { JSDOM } from "jsdom";

const dom = new JSDOM("<div id='root'></div>", { url: "https://synthapp.io/" });
for (const [key, value] of Object.entries({
  window: dom.window, document: dom.window.document, navigator: dom.window.navigator,
  localStorage: dom.window.localStorage, IS_REACT_ACT_ENVIRONMENT: true,
  sessionStorage: dom.window.sessionStorage,
  Event: dom.window.Event,
})) Object.defineProperty(globalThis, key, { configurable: true, value });

// Keep the real router, pages, AuthProvider and API client. Only the unrelated
// home UI and periodic presence work are replaced for these DOM regressions.
const bundle = await build({
  entryPoints: [fileURLToPath(new URL("../src/App.jsx", import.meta.url))],
  bundle: true, write: false, format: "cjs", platform: "node", packages: "external", jsx: "automatic",
  define: { "import.meta.env": "{}" },
  plugins: [{ name: "auth-flow-fixtures", setup(builder) {
    builder.onLoad({ filter: /[\\/]pages[\\/]HomePage\.jsx$/ }, () => ({
      contents: 'export default function HomePage() { return <p>HOME SCREEN</p>; }', loader: "jsx",
    }));
    builder.onLoad({ filter: /[\\/]hooks[\\/]usePresence\.js$/ }, () => ({
      contents: "export function usePresence() {}", loader: "js",
    }));
  } }],
});
const module = { exports: {} };
new Function("require", "module", "exports", bundle.outputFiles[0].text)(
  createRequire(import.meta.url), module, module.exports,
);
const App = module.exports.default;
const { act, createElement } = await import("react");
const { createRoot } = await import("react-dom/client");

let root;
let calls;
let loginFails;
let meResult;
const originalFetch = globalThis.fetch;
const response = (data, status = 200) => ({ ok: status < 400, status, json: async () => data });

beforeEach(() => {
  localStorage.clear();
  calls = [];
  loginFails = false;
  meResult = async () => response({ user: { id: "user-1", username: "tester" } });
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url, options });
    if (url === "/api/auth/login") return loginFails ?
      response({ error: "Invalid credentials" }, 401) : response({ access_token: "test-token" });
    if (url === "/api/auth/register") return response({ message: "registered" });
    if (url === "/api/auth/me") return meResult();
    if (url === "/api/invites/sample-code") return response({
      invite: { server_name: "Example Server", member_count: 3 },
    });
    throw new Error(`Unexpected request: ${url}`);
  };
});

afterEach(async () => {
  if (root) await act(async () => root.unmount());
  root = null;
  globalThis.fetch = originalFetch;
});
after(() => dom.window.close());

const fullPath = () => `${window.location.pathname}${window.location.search}${window.location.hash}`;
async function mount(path) {
  window.history.replaceState(null, "", path);
  root = createRoot(document.getElementById("root"));
  await act(async () => root.render(createElement(App)));
}
async function click(text) {
  const element = [...document.querySelectorAll("a, button")].find((el) => el.textContent.trim() === text);
  assert.ok(element, `Missing action: ${text}`);
  await act(async () => element.click());
}
async function submit() {
  await act(async () => {
    for (const input of document.querySelectorAll("input")) {
      const value = input.type === "email" ? "test@example.com" : "test-password";
      Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set.call(input, value);
      input.dispatchEvent(new window.Event("input", { bubbles: true }));
    }
  });
  await act(async () => document.querySelector("form").dispatchEvent(
    new window.Event("submit", { bubbles: true, cancelable: true }),
  ));
}

test("invite login returns to the preview with query and fragment, without joining", async () => {
  const invitePath = "/invite/sample-code?src=shared&label=a%26b#details";
  await mount(invitePath);
  await click("Log in to Join");
  assert.equal(window.location.pathname, "/login");
  assert.equal(new URLSearchParams(window.location.search).get("redirect"), invitePath);
  await submit();
  assert.equal(fullPath(), invitePath);
  assert.match(document.body.textContent, /Accept Invite/);
  assert.equal(calls.some(({ url }) => url.endsWith("/accept")), false);
  assert.equal(calls.filter(({ url }) => url === "/api/auth/login").length, 1);
});

test("switching from login to registration preserves the invite after sign-up", async () => {
  await mount("/invite/sample-code");
  await click("Log in to Join");
  await click("Register");
  assert.equal(window.location.pathname, "/register");
  assert.equal(new URLSearchParams(window.location.search).get("redirect"), "/invite/sample-code");
  await submit();
  assert.equal(fullPath(), "/invite/sample-code");
  assert.match(document.body.textContent, /Accept Invite/);
  assert.equal(calls.filter(({ url }) => url === "/api/auth/register").length, 1);
});

test("registration, login and password-recovery links retain the destination", async () => {
  await mount("/login?redirect=%2Finvite%2Fsample-code");
  await click("Register");
  await click("Log in");
  await click("Forgot password?");
  assert.equal(window.location.pathname, "/forgot-password");
  await click("Log In");
  await submit();
  assert.equal(fullPath(), "/invite/sample-code");
});

test("failed login keeps the destination for a successful retry", async () => {
  await mount("/login?redirect=%2Finvite%2Fsample-code");
  loginFails = true;
  await submit();
  assert.equal(window.location.pathname, "/login");
  assert.match(document.body.textContent, /Invalid credentials/);
  assert.equal(new URLSearchParams(window.location.search).get("redirect"), "/invite/sample-code");
  loginFails = false;
  await submit();
  assert.equal(fullPath(), "/invite/sample-code");
});

test("the guest guard honors the destination when a saved session becomes ready", async () => {
  localStorage.setItem("synth_token", "existing-token");
  let resolveMe;
  meResult = () => new Promise((resolve) => { resolveMe = resolve; });
  await mount("/login?redirect=%2Finvite%2Fsample-code");
  assert.equal(window.location.pathname, "/login");
  assert.equal(document.querySelector("form"), null);
  await act(() => resolveMe(response({ user: { id: "user-1" } })));
  assert.equal(fullPath(), "/invite/sample-code");
  assert.match(document.body.textContent, /Accept Invite/);
});

test("protected routes retain their complete location through login", async () => {
  const path = "/?server=123#chat";
  await mount(path);
  assert.equal(new URLSearchParams(window.location.search).get("redirect"), path);
  await submit();
  assert.equal(fullPath(), path);
  assert.match(document.body.textContent, /HOME SCREEN/);
});

test("login without a destination falls back home", async () => {
  await mount("/login");
  await submit();
  assert.equal(fullPath(), "/");
});

test("unsafe redirects fall back home in the actual login flow", async () => {
  await mount("/login?redirect=https%3A%2F%2Fevil.example");
  await submit();
  assert.equal(window.location.origin, "https://synthapp.io");
  assert.equal(fullPath(), "/");
});

test("reset-password back links keep the destination without carrying the reset token", async () => {
  await mount("/reset-password?token=reset-secret&redirect=%2Finvite%2Fsample-code");
  await click("← Back to Login");
  assert.equal(fullPath(), "/login?redirect=%2Finvite%2Fsample-code");
  await submit();
  assert.equal(fullPath(), "/invite/sample-code");
});
