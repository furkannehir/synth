function formatDate(iso) {
  if (!iso) return "";
  const date = new Date(iso);
  const today = new Date();
  const yesterday = new Date(today);
  yesterday.setDate(today.getDate() - 1);
  if (date.toDateString() === today.toDateString()) return `Today — ${date.toLocaleDateString([], { weekday: "long", month: "long", day: "numeric", year: "numeric" })}`;
  if (date.toDateString() === yesterday.toDateString()) return "Yesterday";
  return date.toLocaleDateString([], { month: "short", day: "numeric", year: "numeric" });
}

export function groupByDate(messages) {
  const groups = [];
  let currentDate = null;
  for (const message of messages) {
    const date = message.created_at ? new Date(message.created_at).toDateString() : "Unknown";
    if (date !== currentDate) {
      currentDate = date;
      groups.push({ type: "separator", label: formatDate(message.created_at) });
    }
    groups.push({ type: "message", ...message });
  }
  return groups;
}
