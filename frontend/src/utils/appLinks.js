const CODE = /^[A-Za-z0-9_-]{1,128}$/;

export function buildDesktopInviteLink(code) {
  return typeof code === "string" && CODE.test(code) ? `synthapp://invite/${code}` : null;
}

export function parseInviteLink(value) {
  if (typeof value !== "string" || value.length > 2048 || /[\\\s]/.test(value)) return null;
  if (!/^synthapp:\/\/invite\/[A-Za-z0-9_-]{1,128}$/i.test(value) &&
      !/^https:\/\/synthapp\.io\/invite\/[A-Za-z0-9_-]{1,128}\/?(?:[?#].*)?$/i.test(value)) return null;
  try {
    const url = new URL(value);
    if (url.username || url.password || url.port) return null;
    const desktop = url.protocol === "synthapp:" && url.hostname === "invite";
    const web = url.protocol === "https:" && url.hostname === "synthapp.io";
    if (!desktop && !web) return null;
    if (desktop && (url.search || url.hash)) return null;
    const match = (desktop ? /^\/([^/]+)$/ : /^\/invite\/([^/]+)\/?$/).exec(url.pathname);
    if (!match || !CODE.test(match[1])) return null;
    return `/invite/${match[1]}${web ? url.search + url.hash : ""}`;
  } catch { return null; }
}

export function browserInviteChoice(code, storage) {
  try { (storage || window.sessionStorage).setItem(`synth-invite-browser:${code}`, "1"); } catch { /* Storage may be disabled. */ }
}

export function attemptDesktopInvite(code, { storage, launch = (url) => window.location.assign(url) } = {}) {
  const url = buildDesktopInviteLink(code);
  if (!url) return false;
  try {
    storage ||= window.sessionStorage;
    if (storage.getItem(`synth-invite-browser:${code}`) || storage.getItem(`synth-invite-attempt:${code}`)) return false;
    storage.setItem(`synth-invite-attempt:${code}`, "1");
  } catch { return false; } // Do not repeatedly launch when visit state cannot be saved.
  try { launch(url); } catch { /* The browser preview remains available. */ }
  return true;
}
