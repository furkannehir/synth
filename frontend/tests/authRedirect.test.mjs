import assert from "node:assert/strict";
import test from "node:test";
import {
  buildAuthLink, getAuthRedirect, getLocationPath, safeRedirectPath,
} from "../src/utils/authRedirect.js";

test("local destinations retain their query and fragment", () => {
  for (const path of ["/invite/code", "/invite/code?src=shared&next=1#details", "/?server=123#chat", "/download"]) {
    assert.equal(safeRedirectPath(path), path);
  }
});

test("redirect parameters round-trip embedded URL punctuation", () => {
  const path = "/invite/code?src=chat&label=a%26b#details";
  const link = buildAuthLink("/login", path);
  assert.equal(new URLSearchParams(link.split("?")[1]).get("redirect"), path);
  assert.equal(getAuthRedirect(link.slice(link.indexOf("?"))), path);
});

test("absent and malformed destinations fall back home", () => {
  for (const path of [null, undefined, "", 123, "invite/code", "/invite/%ZZ"]) {
    assert.equal(safeRedirectPath(path), "/");
  }
  assert.equal(getAuthRedirect(""), "/");
  assert.equal(buildAuthLink("/register", "/"), "/register");
});

test("external and encoded protocol-relative redirects are rejected", () => {
  for (const path of [
    "https://evil.example/", "//evil.example/", "javascript:alert(1)",
    "/\\evil.example/", "/%2fevil.example/", "/%5cevil.example/", "/x/..//evil.example/",
    "/invite/code\n", "/invite/%00code", "/invite/%0d%0acode",
  ]) assert.equal(safeRedirectPath(path), "/", path);
});

test("authentication destinations cannot create redirect loops", () => {
  for (const path of [
    "/login", "/register?redirect=/invite/code", "/forgot-password#form", "/reset-password?token=secret",
    "/LOGIN/", "/%6cogin", "/invite/../login", "/%2e%2e/login", "/login%2f", "/login%3fredirect=x",
  ]) assert.equal(safeRedirectPath(path), "/", path);
});

test("a full router location becomes the return destination", () => {
  assert.equal(getLocationPath({ pathname: "/invite/code", search: "?src=dm", hash: "#details" }),
    "/invite/code?src=dm#details");
});
