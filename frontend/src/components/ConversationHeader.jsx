import { Hash, Search, Users, X } from "lucide-react";
import Avatar from "./Avatar";

export default function ConversationHeader({ title, friend, query, onQueryChange, onToggleMembers, membersOpen, children }) {
  return (
    <header className="conversation-header">
      <div className="conversation-title">
        {friend ? <Avatar username={friend.username} avatar={friend.avatar} online={friend.is_online} /> : <Hash aria-hidden="true" />}
        <h1>{title}</h1>
      </div>
      <div className="conversation-tools">
        <label className="conversation-search"><Search size={21} aria-hidden="true" /><input aria-label="Search messages" placeholder={`Search in ${friend ? "conversation" : `#${title}`}`} value={query} onChange={(event) => onQueryChange(event.target.value)} />
          {query && <button aria-label="Clear search" onClick={() => onQueryChange("")}><X size={17} /></button>}
        </label>
        {onToggleMembers && <button className="icon-button" aria-label="Toggle members" aria-expanded={membersOpen} onClick={onToggleMembers}><Users size={25} /></button>}
        {children}
      </div>
    </header>
  );
}
