function mergeMessage(current, incoming) {
  const currentTime = Date.parse(current.edited_at || current.created_at) || 0;
  const incomingTime = Date.parse(incoming.edited_at || incoming.created_at) || 0;
  const isOlder = incomingTime < currentTime || (current.edited_at && !incoming.edited_at);
  return {
    ...current,
    ...(isOlder ? {} : incoming),
    // A delayed send/edit response must not undo a read receipt.
    is_read: Boolean(current.is_read || incoming.is_read),
  };
}

export function mergeDMMessages(messages, incoming) {
  const byId = new Map(messages.map((message) => [message.id, message]));
  for (const message of incoming) {
    const current = byId.get(message.id);
    byId.set(message.id, current ? mergeMessage(current, message) : message);
  }
  return [...byId.values()].sort((a, b) => {
    const timeOrder = (Date.parse(a.created_at) || 0) - (Date.parse(b.created_at) || 0);
    return timeOrder || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0);
  });
}

export function applyDMEvent(messages, event, currentUserId) {
  const data = event?.data;
  if (!data) return messages;
  switch (event.type) {
    case "dm":
      return mergeDMMessages(messages, [data]);
    case "dm_edit":
      return messages.map((message) => message.id === data.id ? mergeMessage(message, data) : message);
    case "dm_delete":
      return messages.filter((message) => message.id !== data.id);
    case "dm_read": {
      if (data.by === currentUserId || !Array.isArray(data.message_ids)) return messages;
      const readIds = new Set(data.message_ids);
      return messages.map((message) =>
        message.sender_id === currentUserId && message.recipient_id === data.by && readIds.has(message.id)
          ? { ...message, is_read: true }
          : message,
      );
    }
    default:
      return messages;
  }
}
