import { UserRound } from "lucide-react";
import { useState } from "react";

export default function Avatar({ username, avatar, size = "", online, className = "" }) {
  const [failedImage, setFailedImage] = useState(null);
  return (
    <span className={`app-avatar ${size} ${className}`} title={username}>
      {avatar && failedImage !== avatar ? <img src={avatar} alt={username || ""} onError={() => setFailedImage(avatar)} /> : <UserRound aria-hidden="true" />}
      {typeof online === "boolean" && <span className={`avatar-status ${online ? "is-online" : ""}`} />}
    </span>
  );
}
