import { rejectSession } from "./session";
import { getToken, setToken, clearToken } from "./tokenStore";
import { createDesktopSession } from "./desktopSession";
import { nativeSessionStorage } from "./nativeSessionStorage";
import { isTauriRuntime } from "../utils/runtime";
export { getToken, setToken, clearToken } from "./tokenStore";

const API_BASE = import.meta.env.VITE_API_URL || "/api";

export const desktopSession = createDesktopSession({
  storage: nativeSessionStorage,
  request: (path, body) => rawRequest(path, { method: "POST", token: null, body: JSON.stringify(body) }),
  tokens: { get: getToken, set: setToken, clear: clearToken },
  expired: () => window.dispatchEvent(new Event("synth-session-expired")),
});

function withAuthQuery(url) {
  const token = getToken();
  if (!token) return url;
  const separator = url.includes("?") ? "&" : "?";
  return `${url}${separator}token=${encodeURIComponent(token)}`;
}

function sseUrl(path) {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  return withAuthQuery(`${API_BASE}${normalizedPath}`);
}

async function rawRequest(path, options = {}) {
  const { token = getToken(), ...fetchOptions } = options;
  const headers = { "Content-Type": "application/json", ...fetchOptions.headers };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const res = await fetch(`${API_BASE}${path}`, { signal: AbortSignal.timeout(15000), ...fetchOptions, headers });

  const data = await res.json();
  if (!res.ok) {
    const error = new Error(data.message || data.error || data.msg || "Request failed");
    error.status = res.status;
    error.code = data.code;
    throw error;
  }
  return data;
}

async function request(path, options = {}) {
  let token = options.token === undefined ? getToken() : options.token;
  try {
    return await rawRequest(path, { ...options, token });
  } catch (error) {
    let failure = error;
    if (error.status !== 401 || (path.startsWith("/auth/") && path !== "/auth/me")) throw error;
    if (isTauriRuntime() && options.token === undefined && desktopSession.hasSession() &&
        error.code === "token_expired" && token === getToken()) {
      token = await desktopSession.renew();
      try { return await rawRequest(path, { ...options, token }); }
      catch (retryError) { if (retryError.status !== 401) throw retryError; failure = retryError; }
    }
    if (isTauriRuntime() && desktopSession.hasSession()) {
      if (token === getToken()) await desktopSession.invalidate(token);
    } else rejectSession(token);
    throw failure;
  }
}

// Auth
export const auth = {
  register: (username, email, password) =>
    request("/auth/register", {
      method: "POST",
      body: JSON.stringify({ username, email, password }),
    }),
  login: (email, password) => {
    const send = () => request("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password, ...(isTauriRuntime() ? { persistent: true } : {}) }),
    });
    return isTauriRuntime() ? desktopSession.login(send) : send();
  },
  me: () => request("/auth/me"),
  forgotPassword: (email) =>
    request("/auth/forgot-password", {
      method: "POST",
      body: JSON.stringify({ email }),
    }),
  resetPassword: (token, new_password) =>
    request("/auth/reset-password", {
      method: "POST",
      body: JSON.stringify({ token, new_password }),
    }),
};

// Servers
export const servers = {
  list: () => request("/servers"),
  get: (id) => request(`/servers/${id}`),
  create: (name) =>
    request("/servers", { method: "POST", body: JSON.stringify({ name }) }),
  join: (id) => request(`/servers/${id}/join`, { method: "POST" }),
  leave: (id) => request(`/servers/${id}/leave`, { method: "POST" }),
  members: (id) => request(`/servers/${id}/members`),
  membersStreamUrl: (id) => sseUrl(`/servers/${id}/members/stream`),
};

// Channels
export const channels = {
  list: (serverId) => request(`/servers/${serverId}/channels`),
  create: (serverId, name, channelType = "voice") =>
    request(`/servers/${serverId}/channels`, {
      method: "POST",
      body: JSON.stringify({ name, type: channelType }),
    }),
};

// Voice
export const voice = {
  join: (serverId, channelId) =>
    request(`/servers/${serverId}/channels/${channelId}/voice/join`, { method: "POST" }),
  leave: (serverId, channelId) =>
    request(`/servers/${serverId}/channels/${channelId}/voice/leave`, { method: "POST" }),
  participants: (serverId, channelId) =>
    request(`/servers/${serverId}/channels/${channelId}/voice/participants`),
};

// Presence
export const presence = {
  heartbeat: (token, sessionId) => request("/presence/heartbeat", {
    method: "POST", token, body: JSON.stringify({ session_id: sessionId }),
  }),
  offline: (token, sessionId) => request("/presence/offline", {
    method: "POST", token, keepalive: true, body: JSON.stringify({ session_id: sessionId }),
  }),
};

// Invites
export const invites = {
  create: (serverId, { max_uses = 0, expires_in_hours = null } = {}) =>
    request(`/servers/${serverId}/invites`, {
      method: "POST",
      body: JSON.stringify({ max_uses, expires_in_hours }),
    }),
  list: (serverId) => request(`/servers/${serverId}/invites`),
  preview: (code) => request(`/invites/${code}`),
  accept: (code) => request(`/invites/${code}/accept`, { method: "POST" }),
  delete: (code) => request(`/invites/${code}`, { method: "DELETE" }),
};

// Messages
export const messages = {
  list: (channelId, before = null) => {
    const qs = before ? `?before=${before}` : "";
    return request(`/channels/${channelId}/messages${qs}`);
  },
  send: (channelId, content) =>
    request(`/channels/${channelId}/messages`, {
      method: "POST",
      body: JSON.stringify({ content }),
    }),
  edit: (channelId, messageId, content) =>
    request(`/channels/${channelId}/messages/${messageId}`, {
      method: "PATCH",
      body: JSON.stringify({ content }),
    }),
  delete: (channelId, messageId) =>
    request(`/channels/${channelId}/messages/${messageId}`, {
      method: "DELETE",
    }),
  /** Returns the URL for the SSE event stream (token passed in query param). */
  eventsUrl: (channelId) => sseUrl(`/channels/${channelId}/messages/events`),
};

// Friends
export const friends = {
  list: () => request("/friends"),
  pending: () => request("/friends/pending"),
  sendRequest: (username) =>
    request("/friends/request", {
      method: "POST",
      body: JSON.stringify({ username }),
    }),
  accept: (requestId) =>
    request(`/friends/${requestId}/accept`, { method: "POST" }),
  reject: (requestId) =>
    request(`/friends/${requestId}/reject`, { method: "POST" }),
  cancel: (requestId) =>
    request(`/friends/${requestId}/cancel`, { method: "POST" }),
  remove: (friendId) =>
    request(`/friends/${friendId}`, { method: "DELETE" }),
};

// Direct Messages
export const dms = {
  unreadCount: () => request("/dms/unread_count"),
  conversations: (offset = 0, limit = 20) =>
    request(`/dms/conversations?offset=${offset}&limit=${limit}`),
  list: (friendId, before = null) => {
    const qs = before ? `?before=${before}` : "";
    return request(`/dms/${friendId}/messages${qs}`);
  },
  send: (friendId, content) =>
    request(`/dms/${friendId}/messages`, {
      method: "POST",
      body: JSON.stringify({ content }),
    }),
  edit: (friendId, dmId, content) =>
    request(`/dms/${friendId}/messages/${dmId}`, {
      method: "PATCH",
      body: JSON.stringify({ content }),
    }),
  delete: (friendId, dmId) =>
    request(`/dms/${friendId}/messages/${dmId}`, {
      method: "DELETE",
    }),
  markRead: (friendId) =>
    request(`/dms/${friendId}/messages/read`, { method: "POST" }),
  eventsUrl: (friendId) => sseUrl(`/dms/${friendId}/messages/events`),
};
