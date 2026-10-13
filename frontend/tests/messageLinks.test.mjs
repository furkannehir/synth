import assert from "node:assert/strict";
import test from "node:test";
import { tokenizeMessage, safeWebUrl } from "../src/utils/messageLinks.js";

test("multiple URLs are linkified while retaining exact text and whitespace", () => {
  const text = "Hi 🙂\nhttps://example.com/path?a=1&b=2 and www.example.org.\nDone.";
  const parts = tokenizeMessage(text);
  assert.equal(parts.map((part) => part.text).join(""), text);
  assert.deepEqual(parts.filter((part) => part.href).map((part) => part.href), [
    "https://example.com/path?a=1&b=2", "https://www.example.org/",
  ]);
});

test("balanced URL parentheses are kept and surrounding punctuation is plain text", () => {
  const parts = tokenizeMessage("See (https://en.wikipedia.org/wiki/Function_(mathematics)).");
  assert.equal(parts.find((part) => part.href).text, "https://en.wikipedia.org/wiki/Function_(mathematics)");
  assert.equal(parts.at(-1).text, ").");
});

test("non-web schemes and bare domains remain plain text", () => {
  for (const text of ["javascript:alert(1)", "data:text/html,hello", "file:///tmp/file", "mailto:user@example.com", "synthapp://invite/code", "example.com"]) {
    assert.equal(tokenizeMessage(text).some((part) => part.href), false, text);
  }
});

test("links with embedded credentials and malformed URLs are rejected", () => {
  for (const value of ["javascript:alert(1)", "data:text/html,test", "https://user:secret@example.com/", "https://example.com\\@evil.example", "//example.com", "http://"]) {
    assert.equal(safeWebUrl(value), null, value);
  }
});

test("HTML and script syntax remain message text", () => {
  const text = '<script>alert(1)</script> <img onerror="alert(2)">';
  assert.deepEqual(tokenizeMessage(text), [{ text }]);
});
