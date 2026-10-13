import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { tokenizeMessage } from "../utils/messageLinks";
import { parseInviteLink } from "../utils/appLinks";
import { isTauriRuntime } from "../utils/runtime";

export default function MessageContent({ content }) {
  const navigate = useNavigate();
  const [error, setError] = useState("");
  const activate = async (event, href) => {
    const internal = parseInviteLink(href);
    if (isTauriRuntime()) {
      event.preventDefault();
      setError("");
      if (internal) { navigate(internal); return; }
      try {
        const { openUrl } = await import("@tauri-apps/plugin-opener");
        await openUrl(href);
      } catch { setError("Couldn't open this link. Copy it and open it in your browser."); }
    } else if (internal && !event.ctrlKey && !event.metaKey && !event.shiftKey && !event.altKey) {
      event.preventDefault();
      navigate(internal);
    }
  };
  return <>
    {tokenizeMessage(content).map((part, index) => part.href ? (
      <a key={index} href={part.href} target="_blank" rel="noopener noreferrer"
        onClick={(event) => activate(event, part.href)}
        onAuxClick={(event) => { if (isTauriRuntime() && event.button === 1) activate(event, part.href); }}
        className="text-neon-cyan underline decoration-neon-cyan/40 hover:decoration-neon-cyan break-all rounded-sm focus-visible:outline-2 focus-visible:outline-neon-cyan focus-visible:outline-offset-2">
        {part.text}
      </a>
    ) : part.text)}
    {error && <span role="alert" className="block text-xs text-neon-red mt-1">{error}</span>}
  </>;
}
