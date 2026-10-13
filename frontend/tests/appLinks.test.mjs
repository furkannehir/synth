import assert from "node:assert/strict";
import test from "node:test";
import { buildDesktopInviteLink, parseInviteLink, attemptDesktopInvite, browserInviteChoice } from "../src/utils/appLinks.js";

test("desktop and website invites resolve to the same internal preview", () => {
  assert.equal(buildDesktopInviteLink("sample-code_1"), "synthapp://invite/sample-code_1");
  assert.equal(parseInviteLink("synthapp://invite/sample-code_1"), "/invite/sample-code_1");
  assert.equal(parseInviteLink("https://synthapp.io/invite/sample-code_1?src=dm#preview"), "/invite/sample-code_1?src=dm#preview");
});

test("deep links reject arbitrary routes, credentials, ports and encoded path tricks", () => {
  for (const value of [
    "synthapp://invite/code?token=secret", "synthapp://invite/code#part", "synthapp://invite/../code",
    "synthapp://invite/code/next", "synthapp://login/code", "synthapp://user:secret@invite/code",
    "synthapp://invite:123/code", "synthapp://invite/%2fcode", "https://evil.example/invite/code",
    "https://synthapp.io.evil.example/invite/code", "https://synthapp.io/path/../invite/code",
    "https://synthapp.io/invite/code%2fnext", "https://synthapp.io:443/invite/code", "synthapp://invite/" + "a".repeat(129),
  ]) assert.equal(parseInviteLink(value), null, value);
});

test("automatic launch happens once per invite visit and preserves the browser choice", () => {
  const values = new Map();
  const storage = { getItem: (key) => values.get(key), setItem: (key, value) => values.set(key, value) };
  const launched = [];
  const options = { storage, launch: (url) => launched.push(url) };
  assert.equal(attemptDesktopInvite("code", options), true);
  assert.equal(attemptDesktopInvite("code", options), false);
  browserInviteChoice("another-code", storage);
  assert.equal(attemptDesktopInvite("another-code", options), false);
  assert.deepEqual(launched, ["synthapp://invite/code"]);
});

test("blocked launch and unavailable storage keep the website usable", () => {
  assert.equal(attemptDesktopInvite("code", { storage: { getItem() { throw new Error("blocked"); } } }), false);
  assert.equal(buildDesktopInviteLink("../code"), null);
  assert.doesNotThrow(() => browserInviteChoice("code", { setItem() { throw new Error("blocked"); } }));
});
