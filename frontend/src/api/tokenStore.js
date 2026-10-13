import { isTauriRuntime } from "../utils/runtime.js";

export const TOKEN_CHANGED_EVENT = "synth-token-changed";
let desktopToken = null;

export function getToken() {
  const token = isTauriRuntime() ? desktopToken || localStorage.getItem("synth_token") : localStorage.getItem("synth_token");
  return !token || token === "undefined" ? null : token;
}

export function setToken(token) {
  if (isTauriRuntime()) {
    desktopToken = token;
    localStorage.removeItem("synth_token");
  } else localStorage.setItem("synth_token", token);
  window.dispatchEvent(new Event(TOKEN_CHANGED_EVENT));
}

export function clearToken() {
  desktopToken = null;
  localStorage.removeItem("synth_token");
  window.dispatchEvent(new Event(TOKEN_CHANGED_EVENT));
}

export const tokenStorage = {
  getItem: () => getToken(),
  removeItem: () => clearToken(),
};
