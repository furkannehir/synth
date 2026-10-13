import LinkifyIt from "linkify-it";

const linkify = new LinkifyIt().set({ fuzzyEmail: false });

export function safeWebUrl(value) {
  if (typeof value !== "string" || /[\\\s]/.test(value)) return null;
  try {
    const url = new URL(value);
    return ["http:", "https:"].includes(url.protocol) && !url.username && !url.password ? url.href : null;
  } catch { return null; }
}

export function tokenizeMessage(content) {
  const text = String(content ?? "");
  const parts = [];
  let cursor = 0;
  for (const match of linkify.match(text) || []) {
    if (!/^(?:https?:\/\/|www\.)/i.test(match.text)) continue;
    // Avoid recognizing the tail of a non-web protocol as a standalone URL.
    if (match.index > 0 && /[:/@\\]/.test(text[match.index - 1])) continue;
    const href = safeWebUrl(match.schema ? match.url : `https://${match.text}`);
    if (!href) continue;
    if (match.index > cursor) parts.push({ text: text.slice(cursor, match.index) });
    parts.push({ text: match.text, href });
    cursor = match.lastIndex;
  }
  if (cursor < text.length) parts.push({ text: text.slice(cursor) });
  return parts;
}
