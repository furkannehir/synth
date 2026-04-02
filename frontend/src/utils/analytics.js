import { isTauriRuntime } from "./runtime";

const EVENT_BUFFER_KEY = "synthAnalyticsBuffer";
const MAX_BUFFERED_EVENTS = 200;

function getRuntimeLabel() {
  return isTauriRuntime() ? "desktop" : "browser";
}

function readBufferedEvents() {
  if (typeof window === "undefined") {
    return [];
  }

  try {
    const raw = window.localStorage.getItem(EVENT_BUFFER_KEY);
    if (!raw) {
      return [];
    }

    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function bufferEvent(payload) {
  if (typeof window === "undefined") {
    return;
  }

  try {
    const events = readBufferedEvents();
    events.push(payload);

    if (events.length > MAX_BUFFERED_EVENTS) {
      events.splice(0, events.length - MAX_BUFFERED_EVENTS);
    }

    window.localStorage.setItem(EVENT_BUFFER_KEY, JSON.stringify(events));
  } catch {
    // Intentionally ignore localStorage write failures.
  }
}

function sendToProvider(eventName, properties) {
  if (typeof window === "undefined") {
    return;
  }

  if (typeof window.gtag === "function") {
    window.gtag("event", eventName, properties);
  }

  if (typeof window.plausible === "function") {
    window.plausible(eventName, { props: properties });
  }
}

function sendToEndpoint(payload) {
  if (typeof window === "undefined") {
    return;
  }

  const endpoint = import.meta.env.VITE_ANALYTICS_ENDPOINT;
  if (!endpoint) {
    return;
  }

  const body = JSON.stringify(payload);

  if (typeof navigator !== "undefined" && typeof navigator.sendBeacon === "function") {
    const blob = new Blob([body], { type: "application/json" });
    navigator.sendBeacon(endpoint, blob);
    return;
  }

  void fetch(endpoint, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body,
    keepalive: true,
    credentials: "omit",
  }).catch(() => {});
}

export function trackEvent(eventName, properties = {}) {
  if (typeof window === "undefined") {
    return null;
  }

  const payload = {
    event: eventName,
    ts: new Date().toISOString(),
    runtime: getRuntimeLabel(),
    path: window.location.pathname,
    search: window.location.search,
    properties,
  };

  bufferEvent(payload);
  sendToProvider(eventName, {
    ...properties,
    runtime: payload.runtime,
    path: payload.path,
  });
  sendToEndpoint(payload);

  if (import.meta.env.DEV) {
    console.debug("[analytics]", payload);
  }

  return payload;
}