import { useState } from "react";
import { CheckCheck, Pencil, Trash2 } from "lucide-react";
import Avatar from "./Avatar";
import MessageContent from "./MessageContent";
import { useServerPresence } from "../context/ServerPresenceContext";

export function DateSeparator({ label }) {
  return <div className="date-separator">{label}</div>;
}

export default function ChatMessage({ msg, isOwn, onEdit, onDelete, editingId, onCancelEdit, onSubmitEdit }) {
  const [editContent, setEditContent] = useState(msg.content);
  const { members } = useServerPresence();
  const isEditing = editingId === msg.id;
  const username = msg.author_username || msg.sender_username || "Unknown";
  const avatar = msg.author_avatar || msg.sender_avatar;
  const online = isOwn ? true : members.find(({ id }) => id === (msg.author_id || msg.sender_id))?.is_online;
  const time = msg.created_at ? new Date(msg.created_at).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }) : "";
  return (
    <article className={`message-row ${isOwn ? "is-own" : ""}`}>
      <Avatar username={username} avatar={avatar} online={online} />
      <div className="message-row-content">
        <div className="message-meta"><strong>{username}</strong><time dateTime={msg.created_at}>{time}</time>{msg.edited_at && <small>(edited)</small>}{isOwn && msg.is_read && <CheckCheck size={16} aria-label="Seen" />}</div>
        {isEditing ? <div className="message-edit">
          <textarea aria-label="Edit message" autoFocus value={editContent} rows={2} onChange={(event) => setEditContent(event.target.value)} onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); onSubmitEdit(msg.id, editContent); }
            if (event.key === "Escape") onCancelEdit();
          }} />
          <div><button onClick={onCancelEdit}>Cancel</button><button onClick={() => onSubmitEdit(msg.id, editContent)}>Save</button></div>
        </div> : <p className="message-body"><MessageContent content={msg.content} /></p>}
        {isOwn && !isEditing && <div className="message-actions">
        <button className="icon-button" title="Edit" aria-label="Edit message" onClick={() => { setEditContent(msg.content); onEdit(msg); }}><Pencil size={17} /></button>
        <button className="icon-button" title="Delete" aria-label="Delete message" onClick={() => onDelete(msg.id)}><Trash2 size={17} /></button>
        </div>}
      </div>
    </article>
  );
}
