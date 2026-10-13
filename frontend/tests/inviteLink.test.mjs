import assert from "node:assert/strict";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { build } from "esbuild";
import { loadEnv } from "vite";

const frontendRoot = fileURLToPath(new URL("../", import.meta.url));
const production = loadEnv("production", frontendRoot, "VITE_");
const bundle = await build({
  entryPoints: [fileURLToPath(new URL("../src/utils/inviteLink.js", import.meta.url))],
  bundle: true, write: false, format: "esm", platform: "node",
  define: { "import.meta.env": JSON.stringify(production) },
});
const { buildInviteLink } = await import(`data:text/javascript;base64,${Buffer.from(bundle.outputFiles[0].text).toString("base64")}`);

for (const origin of ["http://tauri.localhost", "https://tauri.localhost", "tauri://localhost", "http://localhost:5173"]) {
  test(`production desktop invites ignore the local origin ${origin}`, () => {
    const link = buildInviteLink("cached-code_123", { desktop: true, origin });
    assert.equal(link, "https://synthapp.io/invite/cached-code_123");
    assert.equal(new URL(link).hostname, new URL(production.VITE_WEB_URL).hostname);
    assert.equal(link.includes("localhost"), false);
  });
}

test("the production default detects the desktop runtime and uses the public website", (t) => {
  const original = Object.getOwnPropertyDescriptor(globalThis, "window");
  Object.defineProperty(globalThis, "window", { configurable: true, value: {
    __TAURI_INTERNALS__: {}, location: { origin: "http://tauri.localhost" },
  } });
  t.after(() => {
    if (original) Object.defineProperty(globalThis, "window", original);
    else Reflect.deleteProperty(globalThis, "window");
  });
  assert.equal(buildInviteLink("fresh-code"), "https://synthapp.io/invite/fresh-code");
});

test("browser development falls back to the current web origin", () => {
  assert.equal(buildInviteLink("code", { publicUrl: "", desktop: false, origin: "http://localhost:5173" }),
    "http://localhost:5173/invite/code");
});

test("browser deployments can explicitly choose their canonical public website", () => {
  assert.equal(buildInviteLink("code", { publicUrl: "https://chat.example.com", desktop: false, origin: "https://preview.example.com" }),
    "https://chat.example.com/invite/code");
});

test("a missing desktop website setting reports an error instead of sharing localhost", () => {
  assert.throws(() => buildInviteLink("code", { publicUrl: "", desktop: true, origin: "http://tauri.localhost" }),
    /Invite links are unavailable/);
});

test("public URLs handle trailing slashes and deployments under a path", () => {
  assert.equal(buildInviteLink("code", { publicUrl: " https://chat.example.com/synth/// ", desktop: true }),
    "https://chat.example.com/synth/invite/code");
});

test("base URL queries and fragments never leak into shared invites", () => {
  assert.equal(buildInviteLink("code", { publicUrl: "https://chat.example.com/?preview=1#settings", desktop: true }),
    "https://chat.example.com/invite/code");
});

test("invite codes cannot add another route, query, or fragment to the URL", () => {
  assert.equal(buildInviteLink("code/other?x=1#fragment", { publicUrl: "https://chat.example.com", desktop: true }),
    "https://chat.example.com/invite/code%2Fother%3Fx%3D1%23fragment");
});

for (const publicUrl of ["not-a-url", "/relative", "tauri://localhost", "javascript:alert(1)", "https://name:password@chat.example.com"]) {
  test(`unshareable website configurations are rejected: ${publicUrl.split("@").at(-1)}`, () => {
    assert.throws(() => buildInviteLink("code", { publicUrl, desktop: true }), /Invite links are unavailable/);
  });
}
