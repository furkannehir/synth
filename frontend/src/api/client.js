const API_BASE = "/api";

export function getToken() {
  const t = localStorage.getItem("synth_token");
  if (!t || t === "undefined") return null;
  return t;
}

export function setToken(token) {
  localStorage.setItem("synth_token", token);
}

export function clearToken() {
  localStorage.removeItem("synth_token");
}

async function request(path, options = {}) {
  const headers = { "Content-Type": "application/json", ...options.headers };
  const token = getToken();
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });

  const data = await res.json();
  if (!res.ok) {
    if (res.status === 401 && !path.startsWith("/auth/")) {
      clearToken();
    }
    throw new Error(data.message || data.error || "Request failed");
  }
  return data;
}

// Auth
export const auth = {
  register: (username, email, password) =>
    request("/auth/register", {
      method: "POST",
      body: JSON.stringify({ username, email, password }),
    }),
  login: (email, password) =>
    request("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
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
};

// Channels
export const channels = {
  list: (serverId) => request(`/servers/${serverId}/channels`),
  create: (serverId, name, channelType = "voice") =>
    request(`/servers/${serverId}/channels`, {
      method: "POST",
      body: JSON.stringify({ name, channel_type: channelType }),
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
  heartbeat: () => request("/presence/heartbeat", { method: "POST" }),
  offline: () => request("/presence/offline", { method: "POST" }),
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
  eventsUrl: (channelId) => {
    const token = getToken();
    return `${API_BASE}/channels/${channelId}/messages/events?token=${token}`;
  },
};

