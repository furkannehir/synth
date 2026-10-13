/** Merge pages and live messages in the same timestamp/ID order as the API. */
export function mergeChannelMessages(messages, incoming) {
  const byId = new Map(messages.map((message) => [message.id, message]));
  for (const message of incoming) {
    const current = byId.get(message.id);
    if (!current) {
      byId.set(message.id, message);
      continue;
    }
    const currentTime = Date.parse(current.edited_at || current.created_at) || 0;
    const incomingTime = Date.parse(message.edited_at || message.created_at) || 0;
    // A page fetched before a live edit must not replace its newer content.
    if (incomingTime < currentTime || (current.edited_at && !message.edited_at)) continue;
    byId.set(message.id, { ...current, ...message });
  }
  return [...byId.values()].sort((a, b) => {
    const timeOrder = (Date.parse(a.created_at) || 0) - (Date.parse(b.created_at) || 0);
    return timeOrder || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0);
  });
}

/** State belonging to a single mounted channel; closed scopes ignore replies. */
export function createChannelState(channelId) {
  let active = true;
  let messages = [];
  let historyVersion = 0;
  let mutationVersion = 0;
  const changedAt = new Map();
  const deleted = new Set();

  function merge(incoming) {
    if (!active) return null;
    const accepted = incoming.filter((message) => message.channel_id === channelId && !deleted.has(message.id));
    mutationVersion += 1;
    for (const message of accepted) changedAt.set(message.id, mutationVersion);
    messages = mergeChannelMessages(messages, accepted);
    return messages;
  }

  function applyEvent(event) {
    if (!active) return null;
    const data = event?.data;
    if (!data || (data.channel_id && data.channel_id !== channelId)) return messages;
    if (event.type === "message_delete") {
      deleted.add(data.id);
      changedAt.delete(data.id);
      messages = messages.filter((message) => message.id !== data.id);
    } else if (event.type === "message") {
      return merge([data]);
    } else if (event.type === "message_edit" && messages.some((message) => message.id === data.id)) {
      return merge([data]);
    }
    return messages;
  }

  return {
    get active() { return active; },
    get historyVersion() { return historyVersion; },
    get mutationVersion() { return mutationVersion; },
    close() { active = false; },
    merge,
    applyEvent,
    replaceHistory(incoming, since = mutationVersion) {
      if (!active) return null;
      historyVersion += 1;
      const recent = messages.filter((message) => (changedAt.get(message.id) || 0) > since);
      messages = mergeChannelMessages(incoming.filter((message) =>
        message.channel_id === channelId && !deleted.has(message.id)), recent);
      return messages;
    },
    prependPage(incoming, version) {
      if (version !== historyVersion) return null;
      return merge(incoming);
    },
  };
}
